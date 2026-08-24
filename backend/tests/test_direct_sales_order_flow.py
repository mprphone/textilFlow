import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.routes.production import release_sales_order, save_sales_order
from backend.app.db import Base
from backend.app.models import Company, Customer, ProductionOrder, SalesOrderLine, Style, User, UserCompany


class DirectSalesOrderFlowTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.user = User(username="admin", full_name="Admin", password_hash="x")
        self.db.add_all([self.company, self.user])
        self.db.flush()
        self.db.add(UserCompany(user_id=self.user.id, company_id=self.company.id, role="admin", permissions=[]))
        self.customer = Customer(company_id=self.company.id, code="C", name="Cliente")
        self.style = Style(company_id=self.company.id, reference="ST", description="Tee")
        self.db.add_all([self.customer, self.style])
        self.db.commit()

    def payload(self):
        return {
            "company_id": self.company.id,
            "header": {
                "customer_id": self.customer.id, "order_no": "ENC-1", "status": "confirmed",
                "currency": "EUR", "delivery_date": "2026-09-15",
                "custom_data": {
                    "payment_terms": "30 dias", "incoterm": "DAP", "transport": "customer",
                    "delivery_address": "Rua da Fábrica, Porto", "vat_rate": 0, "vat_label": "Exportação",
                },
            },
            "items": [
                {"style_id": self.style.id, "color": "Preto", "size": "S", "quantity": 30, "unit_price": 8},
                {"style_id": self.style.id, "color": "Preto", "size": "M", "quantity": 20, "unit_price": 8},
            ],
        }

    def test_atomic_grade_save_and_idempotent_release(self):
        saved = save_sales_order(self.payload(), db=self.db, user=self.user)
        self.assertEqual(len(saved["lines"]), 2)
        self.assertEqual(saved["order"]["custom_data"]["incoterm"], "DAP")
        self.assertEqual(saved["order"]["custom_data"]["delivery_address"], "Rua da Fábrica, Porto")
        order_id = saved["order"]["id"]
        first = release_sales_order(order_id, db=self.db, user=self.user)
        self.assertEqual(len(first["created"]), 2)
        self.assertEqual(self.db.query(ProductionOrder).count(), 2)
        second = release_sales_order(order_id, db=self.db, user=self.user)
        self.assertEqual(len(second["created"]), 0)
        self.assertEqual(len(second["existing"]), 2)

        changed = self.payload()
        changed["id"] = order_id
        with self.assertRaises(HTTPException):
            save_sales_order(changed, db=self.db, user=self.user)
        self.assertEqual(self.db.query(SalesOrderLine).count(), 2)


if __name__ == "__main__":
    unittest.main()
