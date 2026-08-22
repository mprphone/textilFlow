import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import Company, Employee, Operation, ProductionOrder, Style, WorkAssignment
from backend.app.services.corrections import compensate_event
from backend.app.services.production import register_output


class _Payload:
    def __init__(self, good=0, rejected=0, minutes=60):
        self.quantity_good = good
        self.quantity_rejected = rejected
        self.duration_minutes = minutes
        self.event_type = "output"
        self.notes = None
        self.source = "manual"
        self.allow_overage = False


class CompensateEventTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.flush()
        self.style = Style(company_id=self.company.id, reference="ST", description="Tee")
        self.operation = Operation(company_id=self.company.id, code="OP1", name="Costura", standard_time_min=1, cost_per_minute=0.1)
        self.employee = Employee(company_id=self.company.id, code="E1", name="Ana", hourly_cost=6)
        self.db.add_all([self.style, self.operation, self.employee])
        self.db.flush()
        self.order = ProductionOrder(company_id=self.company.id, style_id=self.style.id, order_no="OF-1", quantity=100, status="planned")
        self.db.add(self.order)
        self.db.flush()
        self.assignment = WorkAssignment(company_id=self.company.id, production_order_id=self.order.id, operation_id=self.operation.id, employee_id=self.employee.id, planned_quantity=100, status="queued")
        self.db.add(self.assignment)
        self.db.flush()

    def test_compensation_fully_reverses_quantities_and_cost(self):
        original = register_output(self.db, self.assignment, _Payload(good=20, minutes=40))
        self.db.commit()
        self.assertEqual(self.assignment.completed_quantity, 20)
        self.assertGreater(original.labor_cost, 0)

        compensating = compensate_event(self.db, original.id, "peças contadas a mais por engano")
        self.db.commit()

        self.assertEqual(self.assignment.completed_quantity, 0)
        self.assertEqual(compensating.quantity_good, -20)
        self.assertAlmostEqual(compensating.labor_cost, -original.labor_cost, places=4)
        self.assertEqual(compensating.event_type, "correction")

    def test_cannot_compensate_a_compensation(self):
        original = register_output(self.db, self.assignment, _Payload(good=10, minutes=20))
        self.db.commit()
        compensate_event(self.db, original.id, "erro de contagem")
        self.db.commit()
        from backend.app.models import ProductionEvent
        correction = self.db.query(ProductionEvent).filter_by(event_type="correction").first()
        with self.assertRaises(Exception):
            compensate_event(self.db, correction.id, "tentativa de estornar o estorno")

    def test_reason_is_required(self):
        original = register_output(self.db, self.assignment, _Payload(good=5, minutes=10))
        self.db.commit()
        with self.assertRaises(Exception):
            compensate_event(self.db, original.id, "")


if __name__ == "__main__":
    unittest.main()
