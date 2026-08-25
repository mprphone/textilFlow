import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.routes.costing import approve_sheet
from backend.app.db import Base
from backend.app.models import (
    BOMItem, Company, CostLine, CostSheet, Customer, Material, Operation,
    ProductOperation, StockLot, Style, User, UserCompany,
)
from backend.app.services.cost_sheet_automation import (
    cost_sheet_completeness, ensure_required_cost_lines, pricing_summary,
)
from backend.app.services.costing import rebuild_product_cost, recalculate_sheet


class CostSheetAutomationTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test", settings={"costing": {"overhead_per_piece": 0}})
        self.customer = Customer(company_id=1, code="C1", name="Cliente")
        self.user = User(username="admin", full_name="Admin", password_hash="x")
        self.db.add_all([self.company, self.user])
        self.db.flush()
        self.customer.company_id = self.company.id
        self.db.add(self.customer)
        self.db.flush()
        self.db.add(UserCompany(user_id=self.user.id, company_id=self.company.id, role="admin", permissions=[]))
        self.style = Style(company_id=self.company.id, customer_id=self.customer.id, reference="TS-1", description="T-shirt")
        self.db.add(self.style)
        self.db.flush()

        self.fabric = Material(company_id=self.company.id, code="FAB", name="Jersey", category="fabric", unit="kg", unit_cost=7)
        self.thread = Material(company_id=self.company.id, code="LINHA", name="Linha poliéster", category="thread", unit="m", unit_cost=.003)
        self.label = Material(company_id=self.company.id, code="ETIQ", name="Etiqueta composição", category="trim", unit="un", unit_cost=.08)
        self.bag = Material(company_id=self.company.id, code="SACO", name="Saco reciclado", category="packaging", unit="un", unit_cost=.12)
        self.db.add_all([self.fabric, self.thread, self.label, self.bag])
        self.db.flush()
        self.db.add(BOMItem(
            company_id=self.company.id, style_id=self.style.id, material_id=self.fabric.id,
            quantity=.3, unit="kg", waste_pct=10, unit_cost=7,
        ))
        self.db.add_all([
            StockLot(company_id=self.company.id, material_id=self.fabric.id, lot_no="L1", quantity=10, reserved=0, unit_cost=4),
            StockLot(company_id=self.company.id, material_id=self.fabric.id, lot_no="L2", quantity=10, reserved=0, unit_cost=6),
        ])
        for index, (code, name, department, minutes, rate) in enumerate([
            ("CUT", "Corte", "Corte", 1, .15),
            ("SEW", "Confeção", "Confeção", 12, .15),
            ("PACK", "Embalagem", "Embalagem", 1, .15),
        ], 1):
            operation = Operation(
                company_id=self.company.id, code=code, name=name, department=department,
                standard_time_min=minutes, cost_per_minute=rate,
            )
            self.db.add(operation)
            self.db.flush()
            self.db.add(ProductOperation(
                company_id=self.company.id, style_id=self.style.id, operation_id=operation.id,
                sequence=index * 10, smv=minutes,
            ))
        self.sheet = CostSheet(
            company_id=self.company.id, style_id=self.style.id, status="draft",
            quantity_basis=500, selling_price=20,
            custom_data={
                "customer_id": self.customer.id, "quote_no": "PROP-TEST",
                "financial_cost_pct": 2, "markup_pct": 35, "commission_pct": 7,
            },
        )
        self.db.add(self.sheet)
        self.db.flush()

    def tearDown(self):
        self.db.close()

    def test_prefills_structure_and_uses_weighted_stock_cost(self):
        rebuild_product_cost(self.db, self.sheet)
        ensure_required_cost_lines(self.db, self.sheet)
        lines = self.db.query(CostLine).filter_by(cost_sheet_id=self.sheet.id).all()
        fabric = next(line for line in lines if line.source_type == "bom")
        self.assertAlmostEqual(fabric.quantity, .33, places=6)
        self.assertAlmostEqual(fabric.unit_cost, 5, places=4)
        self.assertTrue(any(line.source_type == "auto_accessory_label" for line in lines))
        self.assertTrue(any(line.source_type == "auto_accessory_packaging" for line in lines))
        self.assertTrue(any(line.source_type == "auto_accessory_thread" for line in lines))
        self.assertTrue(any(line.source_type == "required_overhead" for line in lines))

    def test_incomplete_until_all_baselines_are_confirmed(self):
        rebuild_product_cost(self.db, self.sheet)
        ensure_required_cost_lines(self.db, self.sheet)
        incomplete = cost_sheet_completeness(self.db, self.sheet)
        self.assertEqual(incomplete["status"], "incomplete")
        self.assertIn("Linha / fio de confeção", [item["label"] for item in incomplete["blockers"]])
        self.assertIn("Custos gerais / indiretos", [item["label"] for item in incomplete["blockers"]])

        for line in self.db.query(CostLine).filter_by(cost_sheet_id=self.sheet.id).all():
            if line.source_type == "auto_accessory_thread":
                line.quantity = 120
            if line.source_type == "required_overhead":
                line.unit_cost = .5
        recalculate_sheet(self.db, self.sheet)
        complete = cost_sheet_completeness(self.db, self.sheet)
        self.assertTrue(complete["can_accept"])

    def test_single_fabric_is_rejected_as_incomplete(self):
        self.db.add(CostLine(
            company_id=self.company.id, cost_sheet_id=self.sheet.id, category="material",
            description="Malha", quantity=.3, unit="kg", unit_cost=5,
            source_type="manual_fabric",
        ))
        recalculate_sheet(self.db, self.sheet)
        with self.assertRaises(HTTPException) as raised:
            approve_sheet(self.sheet.id, db=self.db, user=self.user)
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("Ficha de custo incompleta", str(raised.exception.detail))

    def test_pricing_matches_client_sheet_structure(self):
        self.sheet.total_cost = 10
        result = pricing_summary(self.db, self.sheet)
        self.assertAlmostEqual(result["financial_cost_amount"], .2, places=4)
        self.assertAlmostEqual(result["markup_amount"], 3.5, places=4)
        self.assertAlmostEqual(result["recommended_selling_price"], 13.7 / .93, places=4)


if __name__ == "__main__":
    unittest.main()
