import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    Company, Customer, Department, ProductionLine, ProductionOrder, SalesOrder, SalesOrderLine,
    SewingPlan, Style, SubcontractJob, SubcontractService, Supplier,
)
from backend.app.services.commercial_docs import from_distribution
from backend.app.services.production_split import distribute


class ProductionSplitTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.flush()
        self.customer = Customer(company_id=self.company.id, code="C", name="Cliente")
        self.style = Style(company_id=self.company.id, reference="ST", description="Sweat")
        self.department = Department(company_id=self.company.id, code="CONF", name="Confeção")
        self.supplier = Supplier(company_id=self.company.id, code="TIN", name="Tinturaria", supplier_type="dyeing")
        self.db.add_all([self.customer, self.style, self.department, self.supplier])
        self.db.flush()
        self.line = ProductionLine(company_id=self.company.id, code="L1", name="Linha 1", department_id=self.department.id)
        self.db.add(self.line)
        self.db.flush()
        self.service = SubcontractService(
            company_id=self.company.id, supplier_id=self.supplier.id, code="D", name="Tingir",
            category="dyeing", unit="un", lead_time_days=5,
        )
        self.db.add(self.service)
        sales = SalesOrder(company_id=self.company.id, customer_id=self.customer.id, order_no="EC-1")
        self.db.add(sales)
        self.db.flush()
        order_line = SalesOrderLine(company_id=self.company.id, sales_order_id=sales.id, style_id=self.style.id, quantity=100, unit_price=10)
        self.db.add(order_line)
        self.db.flush()
        self.order = ProductionOrder(
            company_id=self.company.id, sales_order_line_id=order_line.id, style_id=self.style.id,
            order_no="OF-1", quantity=100, status="planned",
        )
        self.db.add(self.order)
        self.db.flush()

    def test_distribute_internal_uses_planned_date(self):
        planned = date.today() + timedelta(days=3)
        distribute(self.db, self.order, {
            "quantity": 40, "source": "unassigned", "destination": "internal",
            "line_id": self.line.id, "planned_date": planned.isoformat(), "override": True,
        })
        plan = self.db.query(SewingPlan).filter_by(production_order_id=self.order.id).one()
        self.assertEqual(plan.start_date, planned)
        self.assertEqual(plan.quantity, 40)

    def test_distribute_subcontract_uses_planned_date_and_returns_job_id(self):
        planned = date.today() + timedelta(days=2)
        result = distribute(self.db, self.order, {
            "quantity": 25, "source": "unassigned", "destination": "subcontract",
            "subcontract_service_id": self.service.id, "planned_date": planned.isoformat(), "override": True,
        })
        self.assertIsNotNone(result["subcontract_job_id"])
        job = self.db.get(SubcontractJob, result["subcontract_job_id"])
        self.assertEqual(job.sent_date, planned)
        self.assertEqual(job.expected_date, planned + timedelta(days=5))
        self.assertEqual(job.quantity, 25)

    def test_distribute_internal_without_planned_date_defaults_to_today(self):
        result = distribute(self.db, self.order, {
            "quantity": 10, "source": "unassigned", "destination": "internal",
            "line_id": self.line.id, "override": True,
        })
        self.assertIsNone(result["subcontract_job_id"])
        plan = self.db.query(SewingPlan).filter_by(production_order_id=self.order.id).one()
        self.assertEqual(plan.start_date, date.today())

    def test_from_distribution_subcontract_tags_service_category(self):
        document = from_distribution(
            self.db, self.company.id, order_id=self.order.id, quantity=25, destination="subcontract",
            subcontract_service_id=self.service.id, subcontract_job_id=999,
        )
        self.db.commit()
        self.assertEqual(document.doc_type, "supplier_transport")
        self.assertEqual(document.supplier_id, self.supplier.id)
        self.assertEqual(document.extra["service_category"], "dyeing")
        self.assertEqual(document.extra["service_name"], "Tingir")
        self.assertEqual(document.extra["subcontract_job_id"], 999)
        self.assertEqual(document.lines[0]["style_id"], self.style.id)
        self.assertEqual(document.lines[0]["quantity"], 25)

    def test_from_distribution_internal_tags_department(self):
        document = from_distribution(
            self.db, self.company.id, order_id=self.order.id, quantity=40, destination="internal",
            line_id=self.line.id,
        )
        self.db.commit()
        self.assertEqual(document.doc_type, "internal_transfer")
        self.assertIsNone(document.supplier_id)
        self.assertEqual(document.extra["department"], "Confeção")
        self.assertEqual(document.extra["department_id"], self.department.id)
        self.assertEqual(document.extra["line_name"], "Linha 1")
        self.assertEqual(document.lines[0]["quantity"], 40)

    def test_from_distribution_invalid_destination_raises(self):
        with self.assertRaises(Exception):
            from_distribution(self.db, self.company.id, order_id=self.order.id, quantity=10, destination="shipped")


if __name__ == "__main__":
    unittest.main()
