import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    BOMItem, Company, CostLine, CostSheet, Customer, Material, ProductionOrder,
    SalesOrder, SalesOrderLine, StockLot, Style, SubcontractJob, SubcontractService, Supplier,
)
from backend.app.services.order_followup import assert_can_distribute, bom_material_needs, service_plan
from backend.app.services.production_cockpit import order_cockpit


class OrderFollowupTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.flush()
        self.customer = Customer(company_id=self.company.id, code="C", name="Cliente")
        self.style = Style(company_id=self.company.id, reference="ST", description="Sweat")
        self.fabric = Material(company_id=self.company.id, code="FAB", name="Fleece", category="fabric", unit="kg", unit_cost=4)
        self.trim = Material(company_id=self.company.id, code="LBL", name="Etiqueta", category="trim", unit="un", unit_cost=.1)
        self.db.add_all([self.customer, self.style, self.fabric, self.trim])
        self.db.flush()
        self.db.add_all([
            BOMItem(company_id=self.company.id, style_id=self.style.id, material_id=self.fabric.id, quantity=.5, unit="kg", waste_pct=10, unit_cost=4),
            BOMItem(company_id=self.company.id, style_id=self.style.id, material_id=self.trim.id, quantity=1, unit="un", waste_pct=0, unit_cost=.1),
            StockLot(company_id=self.company.id, material_id=self.fabric.id, lot_no="L1", quantity=8, reserved=0, unit_cost=4),
            StockLot(company_id=self.company.id, material_id=self.trim.id, lot_no="L2", quantity=5, reserved=0, unit_cost=.1),
        ])
        sales = SalesOrder(
            company_id=self.company.id, customer_id=self.customer.id, order_no="EC-1",
            delivery_date=date.today() + timedelta(days=5), custom_data={"commercial_name": "Ana Costa"},
        )
        self.db.add(sales)
        self.db.flush()
        line = SalesOrderLine(company_id=self.company.id, sales_order_id=sales.id, style_id=self.style.id, quantity=20, unit_price=10, delivery_date=sales.delivery_date)
        self.db.add(line)
        self.db.flush()
        self.order = ProductionOrder(
            company_id=self.company.id, sales_order_line_id=line.id, style_id=self.style.id,
            order_no="OF-1", quantity=20, status="planned",
        )
        self.db.add(self.order)
        self.db.flush()
        sheet = CostSheet(company_id=self.company.id, style_id=self.style.id, status="approved", selling_price=12)
        self.db.add(sheet)
        self.db.flush()
        self.db.add_all([
            CostLine(company_id=self.company.id, cost_sheet_id=sheet.id, category="subcontract", description="Tinturaria", quantity=1, unit="un", unit_cost=.6, amount=.6),
            CostLine(company_id=self.company.id, cost_sheet_id=sheet.id, category="subcontract", description="Estampagem", quantity=1, unit="un", unit_cost=.7, amount=.7),
        ])
        self.supplier = Supplier(company_id=self.company.id, code="TIN", name="Tinturaria", supplier_type="dyeing")
        self.db.add(self.supplier)
        self.db.flush()
        self.dye = SubcontractService(company_id=self.company.id, supplier_id=self.supplier.id, code="D", name="Tingir", category="dyeing", unit="un")
        self.print = SubcontractService(company_id=self.company.id, supplier_id=self.supplier.id, code="P", name="Estampar", category="printing", unit="un")
        self.db.add_all([self.dye, self.print])
        self.db.flush()
        self.order.custom_data = {"approved_cost_sheet_id": sheet.id, "commercial_name": "Ana Costa"}

    def test_bom_needs_and_cockpit(self):
        needs = bom_material_needs(self.db, self.order)
        fabric = next(row for row in needs if row["material_id"] == self.fabric.id)
        self.assertAlmostEqual(fabric["required_quantity"], 11)  # 20 * 0.5 * 1.10
        self.assertGreater(fabric["shortage_quantity"], 0)
        data = order_cockpit(self.db, self.order)
        self.assertEqual(data["order"]["commercial_name"], "Ana Costa")
        self.assertEqual(data["order"]["delivery_date"], (date.today() + timedelta(days=5)).isoformat())
        self.assertTrue(data["goods"])
        self.assertTrue(data["accessories"])
        self.assertEqual(data["services"][0]["key"], "dyeing")
        self.assertTrue(data["services"][1]["locked"])

    def test_locks_printing_until_dyeing_returns(self):
        with self.assertRaises(ValueError):
            assert_can_distribute(self.db, self.order, {
                "destination": "subcontract", "subcontract_service_id": self.print.id, "quantity": 10,
            })
        assert_can_distribute(self.db, self.order, {
            "destination": "subcontract", "subcontract_service_id": self.dye.id, "quantity": 10,
        })
        with self.assertRaises(ValueError):
            assert_can_distribute(self.db, self.order, {"destination": "internal", "line_id": 1, "quantity": 10})

    def test_unlock_after_received(self):
        job = SubcontractJob(
            company_id=self.company.id, production_order_id=self.order.id,
            subcontract_service_id=self.dye.id, supplier_id=self.supplier.id,
            reference="G-1", quantity=20, status="received",
        )
        self.db.add(job)
        self.db.flush()
        steps = service_plan(self.db, self.order, [job], 0)
        printing = next(step for step in steps if step["key"] == "printing")
        self.assertFalse(printing["locked"])
        assert_can_distribute(self.db, self.order, {
            "destination": "subcontract", "subcontract_service_id": self.print.id, "quantity": 10,
        })


if __name__ == "__main__":
    unittest.main()
