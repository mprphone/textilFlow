import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    Company, Customer, Operation, ProductOperation, ProductionEvent, ProductionLine, ProductionOrder,
    ProductionOrderVariant, SalesOrder, SalesOrderLine, Style, StyleVariant, WorkAssignment,
)
from backend.app.services.production import daily_output_options, record_daily_output_bulk


class DailyOutputTabletTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        company = Company(code="TABLET", name="Tablet Test")
        self.db.add(company)
        self.db.flush()
        self.company_id = company.id

        customer = Customer(company_id=company.id, code="C1", name="Cliente Alegre")
        style = Style(company_id=company.id, reference="TSHIRT", description="T-shirt")
        line = ProductionLine(company_id=company.id, code="L1", name="Linha 1")
        operation = Operation(company_id=company.id, code="COS", name="Costura", standard_time_min=1)
        self.db.add_all([customer, style, line, operation])
        self.db.flush()
        self.line_id = line.id
        self.style_id = style.id

        size_s = StyleVariant(company_id=company.id, style_id=style.id, sku="TS-S", color="Azul", size="S")
        size_m = StyleVariant(company_id=company.id, style_id=style.id, sku="TS-M", color="Azul", size="M")
        sales_order = SalesOrder(
            company_id=company.id, customer_id=customer.id, order_no="ENC-1", order_date=date.today(),
            delivery_date=date.today(),
        )
        self.db.add_all([size_s, size_m, sales_order])
        self.db.flush()
        self.size_s_id = size_s.id
        self.size_m_id = size_m.id

        sales_line = SalesOrderLine(
            company_id=company.id, sales_order_id=sales_order.id, style_id=style.id,
            description="T-shirt azul", quantity=30,
        )
        self.db.add(sales_line)
        self.db.flush()
        order = ProductionOrder(
            company_id=company.id, sales_order_line_id=sales_line.id, style_id=style.id, line_id=line.id,
            order_no="OF-1", quantity=30, status="in_progress",
        )
        self.db.add(order)
        self.db.flush()
        self.order_id = order.id
        self.db.add_all([
            ProductionOrderVariant(company_id=company.id, production_order_id=order.id, variant_id=size_s.id, quantity=10),
            ProductionOrderVariant(company_id=company.id, production_order_id=order.id, variant_id=size_m.id, quantity=20),
            ProductOperation(company_id=company.id, style_id=style.id, operation_id=operation.id, sequence=10, smv=1),
        ])
        self.db.commit()

    def test_options_are_grouped_by_order_article_and_size(self):
        result = daily_output_options(self.db, self.company_id)
        self.assertEqual(len(result["orders"]), 1)
        self.assertEqual(result["orders"][0]["order_no"], "ENC-1")
        article = result["orders"][0]["articles"][0]
        self.assertEqual(article["reference"], "TSHIRT")
        self.assertEqual({row["size"] for row in article["variants"]}, {"S", "M"})

    def test_bulk_output_is_recorded_by_line_without_employee(self):
        production_date = date(2026, 9, 2)
        result = record_daily_output_bulk(self.db, self.company_id, {
            "work_date": production_date.isoformat(),
            "production_order_id": self.order_id,
            "line_id": self.line_id,
            "outputs": [
                {"variant_id": self.size_s_id, "quantity_good": 4},
                {"variant_id": self.size_m_id, "quantity_good": 7},
            ],
        })
        self.db.commit()

        self.assertTrue(result["ok"])
        self.assertEqual(result["totals"]["quantity_good"], 11)
        events = self.db.query(ProductionEvent).order_by(ProductionEvent.id).all()
        self.assertEqual([row.variant_id for row in events], [self.size_s_id, self.size_m_id])
        self.assertTrue(all(row.event_time.date() == production_date for row in events))
        self.assertTrue(all(row.employee_id is None for row in events))
        self.assertTrue(all(row.line_id == self.line_id for row in events))
        assignment = self.db.query(WorkAssignment).one()
        self.assertIsNone(assignment.employee_id)
        self.assertEqual(assignment.completed_quantity, 11)


if __name__ == "__main__":
    unittest.main()
