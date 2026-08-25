import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.routes.costing import approve_sheet, reject_sheet, reopen_sheet
from backend.app.db import Base
from backend.app.models import Company, CostLine, CostSheet, Customer, ProductionOrder, Style, User, UserCompany
from backend.app.services.costing import recalculate_sheet


class ProposalLifecycleTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test Factory")
        self.user = User(username="admin", full_name="Admin", password_hash="x")
        self.db.add_all([self.company, self.user])
        self.db.flush()
        self.db.add(UserCompany(user_id=self.user.id, company_id=self.company.id, role="admin", permissions=[]))
        self.customer = Customer(company_id=self.company.id, code="C1", name="Customer")
        self.style = Style(company_id=self.company.id, reference="ST-1", description="T-shirt")
        self.db.add_all([self.customer, self.style])
        self.db.flush()
        self.sheet = CostSheet(
            company_id=self.company.id,
            style_id=self.style.id,
            status="draft",
            quantity_basis=100,
            selling_price=12,
            custom_data={"quote_no": "PROP-00001", "customer_id": self.customer.id},
        )
        self.db.add(self.sheet)
        self.db.flush()
        self.db.add(CostLine(
            company_id=self.company.id,
            cost_sheet_id=self.sheet.id,
            category="material",
            description="Malha",
            quantity=1,
            unit="kg",
            unit_cost=5,
            amount=5,
            source_type="manual_fabric",
        ))
        for category, description, quantity, unit, unit_cost, source_type in [
            ("material", "Linha de confeção", 100, "m", .003, "manual_accessory"),
            ("material", "Etiqueta de composição", 1, "un", .08, "manual_accessory"),
            ("material", "Saco de embalagem", 1, "un", .12, "manual_accessory"),
            ("labor", "Tempo de corte", 1, "min", .15, "required_labor_cutting"),
            ("labor", "Tempo de confeção", 12, "min", .15, "required_labor_sewing"),
            ("labor", "Tempo de embalagem", 1, "min", .15, "required_labor_packing"),
            ("overhead", "Custos gerais / indiretos", 1, "un", .5, "manual_overhead"),
        ]:
            self.db.add(CostLine(
                company_id=self.company.id, cost_sheet_id=self.sheet.id, category=category,
                description=description, quantity=quantity, unit=unit, unit_cost=unit_cost,
                amount=quantity * unit_cost, source_type=source_type,
            ))
        self.db.flush()
        recalculate_sheet(self.db, self.sheet)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_rejected_proposal_can_be_reopened_edited_and_accepted(self):
        reject_sheet(self.sheet.id, {"reason": "Preço"}, db=self.db, user=self.user)
        rejected = self.db.get(CostSheet, self.sheet.id)
        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(rejected.custom_data["rejection_reason"], "Preço")

        reopen_sheet(self.sheet.id, db=self.db, user=self.user)
        reopened = self.db.get(CostSheet, self.sheet.id)
        self.assertEqual(reopened.status, "draft")
        self.assertEqual([row["action"] for row in reopened.custom_data["decision_history"]], ["rejected", "reopened"])

        reject_sheet(self.sheet.id, {}, db=self.db, user=self.user)
        approve_sheet(self.sheet.id, db=self.db, user=self.user)
        accepted = self.db.get(CostSheet, self.sheet.id)
        self.assertEqual(accepted.status, "approved")
        self.assertEqual(accepted.custom_data["decision_history"][-1]["action"], "accepted")

    def test_proposal_linked_to_production_cannot_be_rejected(self):
        self.sheet.status = "approved"
        self.db.add(ProductionOrder(
            company_id=self.company.id,
            style_id=self.style.id,
            order_no="OF-1",
            quantity=100,
            custom_data={"approved_cost_sheet_id": self.sheet.id},
        ))
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            reject_sheet(self.sheet.id, {}, db=self.db, user=self.user)
        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
