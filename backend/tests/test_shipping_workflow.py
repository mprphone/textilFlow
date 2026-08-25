import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    Company, Customer, FinishedGoodsUnit, QualityInspection, SalesOrder, SalesOrderLine,
    Style,
)
from backend.app.services.commercial_docs import from_shipment
from backend.app.services.shipping import (
    close_packing_list, create_packing_list, dispatch_packing_list, dispatch_status,
)


class ShippingWorkflowTest(unittest.TestCase):
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
        order = SalesOrder(
            company_id=company.id, customer_id=customer.id, order_no="EC-1",
            customer_po="PO-CLIENTE", currency="EUR", status="confirmed",
        )
        self.db.add(order)
        self.db.flush()
        line = SalesOrderLine(
            company_id=company.id, sales_order_id=order.id, style_id=style.id,
            description="T-shirt", quantity=100, unit_price=12.5,
        )
        self.db.add(line)
        self.db.flush()
        from backend.app.models import ProductionOrder
        production = ProductionOrder(
            company_id=company.id, sales_order_line_id=line.id, style_id=style.id,
            order_no="OF-1", quantity=100, completed_quantity=100,
            custom_data={"packed_quantity": 100}, status="completed",
        )
        self.db.add(production)
        self.db.flush()
        self.db.add(QualityInspection(
            company_id=company.id, production_order_id=production.id,
            inspection_type="revista", inspected_quantity=100, result="passed",
        ))
        self.db.flush()
        self.company, self.order, self.production = company, order, production

    def payload(self, quantity):
        return {
            "allocations": [{"production_order_id": self.production.id, "quantity": quantity}],
            "package_count": 2,
            "packing_mode": "boxes",
            "packing_data": {"boxes": [{"code": "CX-01", "quantity": quantity / 2}, {"code": "CX-02", "quantity": quantity / 2}]},
        }

    def test_draft_close_documents_dispatch_and_invoice_are_separate(self):
        packing, lines, after_draft = create_packing_list(self.db, self.order, self.payload(40))
        self.assertEqual(packing.status, "preparing")
        self.assertEqual(sum(row.quantity for row in lines), 40)
        self.assertEqual(after_draft["available_quantity"], 100)
        self.assertEqual(after_draft["reserved_quantity"], 0)

        packing, _, after_close = close_packing_list(self.db, packing)
        self.assertEqual(packing.status, "closed")
        self.assertEqual(after_close["available_quantity"], 60)
        self.assertEqual(after_close["reserved_quantity"], 40)
        unit = self.db.query(FinishedGoodsUnit).one()
        self.assertEqual(unit.quantity, 100)
        self.assertEqual(unit.reserved_quantity, 40)

        guide = from_shipment(self.db, self.company.id, packing.id, "sales_delivery")
        self.assertEqual(guide.shipment_id, packing.id)
        self.assertEqual(sum(row["quantity"] for row in guide.lines), 40)
        self.assertEqual(packing.status, "ready")

        packing, _, after_dispatch = dispatch_packing_list(self.db, packing, {"carrier": "Transportes"})
        self.assertEqual(packing.status, "shipped")
        self.assertEqual(self.order.status, "partially_shipped")
        self.assertEqual(after_dispatch["remaining_quantity"], 60)
        self.assertEqual(unit.quantity, 60)
        self.assertEqual(unit.reserved_quantity, 0)

        invoice = from_shipment(self.db, self.company.id, packing.id, "sales_invoice")
        self.assertEqual(invoice.shipment_id, packing.id)
        self.assertEqual(sum(row["quantity"] for row in invoice.lines), 40)
        self.assertEqual(invoice.total, 500)
        self.assertEqual(packing.status, "invoiced")

    def test_closed_packing_list_prevents_over_reservation(self):
        first, _, _ = create_packing_list(self.db, self.order, self.payload(40))
        close_packing_list(self.db, first)
        with self.assertRaisesRegex(ValueError, "60"):
            create_packing_list(self.db, self.order, self.payload(61))
        status = dispatch_status(self.db, self.order)
        self.assertEqual(status["available_quantity"], 60)
        self.assertEqual(status["reserved_quantity"], 40)

    def test_box_totals_must_match_selected_quantities(self):
        payload = self.payload(40)
        payload["packing_data"]["boxes"][1]["quantity"] = 19
        with self.assertRaisesRegex(ValueError, "39"):
            create_packing_list(self.db, self.order, payload)


if __name__ == "__main__":
    unittest.main()
