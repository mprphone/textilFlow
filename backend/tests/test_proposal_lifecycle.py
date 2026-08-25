import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.routes.costing import approve_sheet, reject_sheet, reopen_sheet
from backend.app.db import Base
from backend.app.models import Company, CostLine, CostSheet, ProductionOrder, Style, User, UserCompany
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
        self.style = Style(company_id=self.company.id, reference="ST-1", description="T-shirt")
        self.db.add(self.style)
        self.db.flush()
        self.sheet = CostSheet(
            company_id=self.company.id,
            style_id=self.style.id,
            status="draft",
            quantity_basis=100,
            selling_price=12,
            custom_data={"quote_no": "PROP-00001"},
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
