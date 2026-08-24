import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import Company, Customer, ProductionOrder, ProductionOrderVariant, QualityInspection, SalesOrder, SalesOrderLine, Shipment, ShipmentLine, Style, StyleVariant
from backend.app.services.shipping import create_partial_shipment, dispatch_status
from backend.app.services.production_split import holdings
from backend.app.services.production_stage import record_packing


class PartialShipmentTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        company = Company(code="T", name="Test")
        self.db.add(company)
        self.db.flush()
        customer = Customer(company_id=company.id, code="C", name="Cliente")
        style = Style(company_id=company.id, reference="ST", description="Tee")
        self.db.add_all([customer, style])
        self.db.flush()
        self.sales_order = SalesOrder(company_id=company.id, customer_id=customer.id, order_no="EC-1", status="ready")
        self.db.add(self.sales_order)
        self.db.flush()
        line = SalesOrderLine(company_id=company.id, sales_order_id=self.sales_order.id, style_id=style.id, quantity=100, unit_price=10)
        self.db.add(line)
        self.db.flush()
        self.production_order = ProductionOrder(
            company_id=company.id, sales_order_line_id=line.id, style_id=style.id,
            order_no="OF-1", quantity=100, completed_quantity=100,
            custom_data={"packed_quantity": 100}, status="completed",
        )
        self.db.add(self.production_order)
        self.db.flush()
        self.db.add(QualityInspection(
            company_id=company.id, production_order_id=self.production_order.id,
            inspection_type="revista", inspected_quantity=100, defect_quantity=0, result="passed",
        ))
        self.db.flush()

    @staticmethod
    def payload(number, quantity):
        return {
            "shipment_no": number, "carrier": "Transportes Teste", "quantity": quantity,
            "quantities_checked": True, "quality_checked": True,
            "documents_checked": True, "carrier_checked": True,
        }

    def test_order_can_be_shipped_in_two_independent_parts(self):
        first, first_lines, after_first = create_partial_shipment(self.db, self.sales_order, self.payload("EXP-1", 40))
        self.assertEqual(first.quantity, 40)
        self.assertEqual(sum(row.quantity for row in first_lines), 40)
        self.assertEqual(self.sales_order.status, "partially_shipped")
        self.assertEqual(after_first["remaining_quantity"], 60)
        self.assertEqual(after_first["available_quantity"], 60)
        self.assertEqual(holdings(self.db, self.production_order)["finished_goods"], 60)

        second, second_lines, after_second = create_partial_shipment(self.db, self.sales_order, self.payload("EXP-2", 60))
        self.assertEqual(second.quantity, 60)
        self.assertEqual(sum(row.quantity for row in second_lines), 60)
        self.assertEqual(self.sales_order.status, "shipped")
        self.assertEqual(after_second["remaining_quantity"], 0)
        self.assertEqual(after_second["available_quantity"], 0)
        self.assertEqual(self.db.query(Shipment).count(), 2)
        self.assertEqual(self.db.query(ShipmentLine).count(), 2)

    def test_cannot_ship_more_than_approved_and_packed_balance(self):
        self.production_order.custom_data = {"packed_quantity": 35}
        status = dispatch_status(self.db, self.sales_order)
        self.assertEqual(status["available_quantity"], 35)
        with self.assertRaisesRegex(ValueError, "35"):
            create_partial_shipment(self.db, self.sales_order, self.payload("EXP-1", 36))

    def test_pending_quality_does_not_release_stock(self):
        self.db.query(QualityInspection).delete()
        self.db.add(QualityInspection(
            company_id=self.sales_order.company_id, production_order_id=self.production_order.id,
            inspection_type="final", inspected_quantity=100, result="pending",
        ))
        self.db.flush()
        status = dispatch_status(self.db, self.sales_order)
        self.assertFalse(status["ready"])
        self.assertEqual(status["available_quantity"], 0)

    def test_quality_release_is_selective_by_variant(self):
        style_id = self.production_order.style_id
        first = StyleVariant(company_id=self.sales_order.company_id, style_id=style_id, sku="ST-A-S", color="Azul", size="S")
        second = StyleVariant(company_id=self.sales_order.company_id, style_id=style_id, sku="ST-B-M", color="Branco", size="M")
        self.db.add_all([first, second])
        self.db.flush()
        self.db.add_all([
            ProductionOrderVariant(company_id=self.sales_order.company_id, production_order_id=self.production_order.id, variant_id=first.id, quantity=50),
            ProductionOrderVariant(company_id=self.sales_order.company_id, production_order_id=self.production_order.id, variant_id=second.id, quantity=50),
        ])
        self.db.query(QualityInspection).delete()
        self.db.add_all([
            QualityInspection(company_id=self.sales_order.company_id, production_order_id=self.production_order.id, variant_id=first.id, inspection_type="revista", inspected_quantity=50, result="passed"),
            QualityInspection(company_id=self.sales_order.company_id, production_order_id=self.production_order.id, variant_id=second.id, inspection_type="revista", inspected_quantity=50, result="pending"),
        ])
        self.db.flush()
        self.production_order.custom_data = {"packed_quantity": 0, "revista_quantity": 100}
        record_packing(self.db, self.production_order, {"variant_id": first.id, "quantity": 50})
        status = dispatch_status(self.db, self.sales_order)
        self.assertEqual(status["available_quantity"], 50)
        self.assertEqual(len(status["allocations"]), 1)
        self.assertEqual(status["allocations"][0]["variant_id"], first.id)
        with self.assertRaisesRegex(ValueError, "0 peças"):
            record_packing(self.db, self.production_order, {"variant_id": second.id, "quantity": 1})


if __name__ == "__main__":
    unittest.main()
