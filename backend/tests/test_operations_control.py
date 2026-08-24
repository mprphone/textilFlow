import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    Company, Customer, CustomerReturnLine, FinishedGoodsUnit, ProductionBatch, ProductionMovement,
    ProductionOrder, QualityInspection, ReworkOrder, SalesOrder, SalesOrderLine,
    ShipmentAllocation, Style,
)
from backend.app.services.execution import movement_holdings, sync_quality_movement
from backend.app.services.operations_control import (
    complete_rework, create_customer_claim, dispose_customer_return, dispose_quality_hold,
    ensure_rework_for_inspection, scan_code,
)
from backend.app.services.production_stage import record_packing
from backend.app.services.shipping import create_partial_shipment


class OperationsControlTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        company = Company(code="T", name="Test")
        self.db.add(company)
        self.db.flush()
        self.company = company
        customer = Customer(company_id=company.id, code="C", name="Cliente")
        style = Style(company_id=company.id, reference="ST", description="Tee")
        self.db.add_all([customer, style])
        self.db.flush()
        sales = SalesOrder(company_id=company.id, customer_id=customer.id, order_no="EC-1", status="ready")
        self.db.add(sales)
        self.db.flush()
        line = SalesOrderLine(company_id=company.id, sales_order_id=sales.id, style_id=style.id, quantity=100, unit_price=10)
        self.db.add(line)
        self.db.flush()
        order = ProductionOrder(
            company_id=company.id, sales_order_line_id=line.id, style_id=style.id,
            order_no="OF-1", quantity=100, completed_quantity=100,
            custom_data={"revista_quantity": 100, "packed_quantity": 0}, status="completed",
        )
        self.db.add(order)
        self.db.flush()
        inspection = QualityInspection(
            company_id=company.id, production_order_id=order.id,
            inspection_type="revista", inspected_quantity=100, result="passed",
        )
        self.db.add(inspection)
        self.db.flush()
        self.sales, self.order = sales, order

    def shipment_payload(self, number, quantity):
        return {
            "shipment_no": number, "carrier": "Transportes", "quantity": quantity,
            "quantities_checked": True, "quality_checked": True,
            "documents_checked": True, "carrier_checked": True,
        }

    def test_finished_goods_is_allocated_across_partial_shipments(self):
        result = record_packing(self.db, self.order, {
            "quantity": 100, "package_code": "CX-1", "packaging_unit_cost": 0.10,
        })
        self.assertEqual(result["finished_goods_unit"]["package_code"], "CX-1")
        create_partial_shipment(self.db, self.sales, self.shipment_payload("EXP-1", 35))
        create_partial_shipment(self.db, self.sales, self.shipment_payload("EXP-2", 65))
        unit = self.db.query(FinishedGoodsUnit).one()
        self.assertEqual(unit.quantity, 0)
        self.assertEqual(unit.initial_quantity, 100)
        self.assertEqual(unit.status, "shipped")
        self.assertEqual(self.db.query(ShipmentAllocation).count(), 2)
        stock = movement_holdings(self.db, self.order)
        self.assertEqual(stock["finished_goods"], 0)
        self.assertEqual(stock["shipped"], 100)

    def test_quality_rework_has_immutable_physical_path_and_reinspection(self):
        inspection = QualityInspection(
            company_id=self.company.id, production_order_id=self.order.id,
            inspection_type="revista", inspected_quantity=10, defect_quantity=2,
            result="conditional",
        )
        self.db.add(inspection)
        self.db.flush()
        sync_quality_movement(self.db, inspection)
        rework = ensure_rework_for_inspection(self.db, inspection)
        self.assertIsInstance(rework, ReworkOrder)
        complete_rework(self.db, rework, {"completed_quantity": 1, "scrap_quantity": 1, "labor_cost": 3})
        self.assertEqual(rework.status, "completed")
        types = [row.movement_type for row in self.db.query(ProductionMovement).filter_by(rework_order_id=rework.id).all()]
        self.assertEqual(types, ["rework_start", "rework_complete", "scrap"])
        self.assertEqual(self.db.query(QualityInspection).filter_by(result="pending").count(), 1)

    def test_partial_rework_accumulates_only_the_increment(self):
        rework = ReworkOrder(
            company_id=self.company.id, production_order_id=self.order.id,
            reference="RW-PART", barcode="RW-PART", quantity=10, status="open",
        )
        self.db.add(rework)
        self.db.flush()
        complete_rework(self.db, rework, {"completed_quantity": 3, "scrap_quantity": 0})
        self.assertEqual(rework.completed_quantity, 3)
        self.assertEqual(rework.status, "in_progress")
        complete_rework(self.db, rework, {"completed_quantity": 5, "scrap_quantity": 2})
        self.assertEqual(rework.completed_quantity, 8)
        self.assertEqual(rework.scrap_quantity, 2)
        self.assertEqual(rework.status, "completed")
        recovered = self.db.query(ProductionMovement).filter_by(
            rework_order_id=rework.id, movement_type="rework_complete",
        ).all()
        self.assertEqual(sum(row.quantity for row in recovered), 8)
        self.assertEqual([row.inspected_quantity for row in self.db.query(QualityInspection).filter_by(result="pending").all()], [3, 5])

    def test_packing_requires_batch_when_more_than_one_is_available(self):
        self.db.add_all([
            ProductionBatch(company_id=self.company.id, production_order_id=self.order.id, batch_no="LT-1", quantity=50),
            ProductionBatch(company_id=self.company.id, production_order_id=self.order.id, batch_no="LT-2", quantity=50),
        ])
        self.db.flush()
        with self.assertRaisesRegex(ValueError, "Selecione o lote"):
            record_packing(self.db, self.order, {"quantity": 10, "package_code": "CX-SEM-LOTE"})

    def test_return_is_linked_to_original_package_and_can_be_restocked(self):
        record_packing(self.db, self.order, {"quantity": 100, "package_code": "CX-RET"})
        shipment, lines, _ = create_partial_shipment(self.db, self.sales, self.shipment_payload("EXP-RET", 20))
        allocation = self.db.query(ShipmentAllocation).one()
        result = create_customer_claim(self.db, self.company.id, {
            "sales_order_id": self.sales.id, "shipment_id": shipment.id,
            "reason": "Defeito", "lines": [{
                "shipment_line_id": lines[0].id,
                "shipment_allocation_id": allocation.id,
                "quantity": 5,
            }],
        })
        returned = self.db.get(CustomerReturnLine, result["lines"][0]["id"])
        self.assertEqual(returned.finished_goods_unit_id, allocation.finished_goods_unit_id)
        dispose_customer_return(self.db, returned, "restock")
        self.assertEqual(returned.status, "processed")
        self.assertEqual(scan_code(self.db, self.company.id, f"FG-RETURN-{returned.id}")["kind"], "finished_goods")

    def test_failed_quality_requires_explicit_disposition(self):
        inspection = QualityInspection(
            company_id=self.company.id, production_order_id=self.order.id,
            inspection_type="revista", inspected_quantity=4, defect_quantity=4, result="failed",
        )
        self.db.add(inspection)
        self.db.flush()
        sync_quality_movement(self.db, inspection)
        self.assertEqual(inspection.disposition, "quarantine")
        self.assertIsNone(ensure_rework_for_inspection(self.db, inspection))
        result = dispose_quality_hold(self.db, inspection, "rework")
        self.assertIsNotNone(result["rework_order_id"])
        self.assertEqual(inspection.disposition, "rework")


if __name__ == "__main__":
    unittest.main()
