import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    Company, Customer, Employee, Machine, Operation, ProductionBatch, ProductionOrder,
    SalesOrder, SalesOrderLine, Style, WorkAssignment,
)
from backend.app.services.production import record_daily_output, register_output


class _Payload:
    def __init__(self, good=0, rejected=0, minutes=60, allow_overage=False):
        self.quantity_good = good
        self.quantity_rejected = rejected
        self.duration_minutes = minutes
        self.event_type = "output"
        self.notes = None
        self.source = "manual"
        self.allow_overage = allow_overage


class ProductionSyncTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.flush()
        self.style = Style(company_id=self.company.id, reference="ST", description="Tee")
        self.customer = Customer(company_id=self.company.id, code="C", name="Cliente")
        self.employee = Employee(company_id=self.company.id, code="E1", name="Ana", hourly_cost=6)
        self.operation = Operation(company_id=self.company.id, code="OP1", name="Costura", standard_time_min=2, cost_per_minute=0.1)
        self.machine = Machine(company_id=self.company.id, code="M1", name="Máquina 1", machine_type="lockstitch", hourly_cost=3)
        self.db.add_all([self.style, self.customer, self.employee, self.operation, self.machine])
        self.db.flush()
        self.order = ProductionOrder(company_id=self.company.id, style_id=self.style.id, order_no="OF-1", quantity=100, status="planned")
        self.db.add(self.order)
        self.db.flush()

    def test_batch_completed_quantity_is_tracked(self):
        batch = ProductionBatch(company_id=self.company.id, production_order_id=self.order.id, batch_no="B1", quantity=100, status="waiting")
        self.db.add(batch)
        self.db.flush()
        assignment = WorkAssignment(
            company_id=self.company.id, production_order_id=self.order.id, batch_id=batch.id,
            operation_id=self.operation.id, employee_id=self.employee.id, machine_id=self.machine.id,
            planned_quantity=100, status="queued",
        )
        self.db.add(assignment)
        self.db.flush()
        register_output(self.db, assignment, _Payload(good=40))
        self.db.commit()
        self.assertEqual(batch.completed_quantity, 40)
        self.assertEqual(batch.status, "in_progress")
        register_output(self.db, assignment, _Payload(good=60))
        self.db.commit()
        self.assertEqual(batch.completed_quantity, 100)
        self.assertEqual(batch.status, "completed")

    def test_overage_is_rejected_unless_explicitly_allowed(self):
        assignment = WorkAssignment(
            company_id=self.company.id, production_order_id=self.order.id,
            operation_id=self.operation.id, employee_id=self.employee.id,
            planned_quantity=10, status="queued",
        )
        self.db.add(assignment)
        self.db.flush()
        with self.assertRaises(Exception):
            register_output(self.db, assignment, _Payload(good=15))
        # com allow_overage, o mesmo registo tem de ser aceite
        register_output(self.db, assignment, _Payload(good=15, allow_overage=True))
        self.db.commit()
        self.assertEqual(assignment.completed_quantity, 15)

    def test_multiple_assignments_same_operation_sum_before_min(self):
        a1 = WorkAssignment(company_id=self.company.id, production_order_id=self.order.id, operation_id=self.operation.id, employee_id=self.employee.id, planned_quantity=50, status="queued")
        a2 = WorkAssignment(company_id=self.company.id, production_order_id=self.order.id, operation_id=self.operation.id, employee_id=self.employee.id, planned_quantity=50, status="queued")
        self.db.add_all([a1, a2])
        self.db.flush()
        register_output(self.db, a1, _Payload(good=50))
        register_output(self.db, a2, _Payload(good=50))
        self.db.commit()
        # As duas atribuicoes da MESMA operacao, juntas, cobrem os 100 da OF -
        # o progresso deve ser 100%, nao ficar preso por comparar cada uma
        # isoladamente contra o total da ordem.
        self.assertEqual(self.order.completed_quantity, 100)
        self.assertEqual(self.order.status, "completed")

    def test_sales_order_flips_to_ready_when_production_covers_the_line(self):
        sales = SalesOrder(company_id=self.company.id, customer_id=self.customer.id, order_no="EC-1", delivery_date=date.today() + timedelta(days=5), status="confirmed")
        self.db.add(sales)
        self.db.flush()
        line = SalesOrderLine(company_id=self.company.id, sales_order_id=sales.id, style_id=self.style.id, quantity=100, unit_price=10)
        self.db.add(line)
        self.db.flush()
        self.order.sales_order_line_id = line.id
        assignment = WorkAssignment(company_id=self.company.id, production_order_id=self.order.id, operation_id=self.operation.id, employee_id=self.employee.id, planned_quantity=100, status="queued")
        self.db.add(assignment)
        self.db.flush()
        register_output(self.db, assignment, _Payload(good=100))
        self.db.commit()
        self.db.refresh(sales)
        self.assertEqual(sales.status, "ready")

    def test_daily_output_gives_new_assignment_the_remaining_share(self):
        # Um funcionario ja tem 60 planeados nesta operacao; o segundo,
        # criado agora, deve ficar so com os 40 que restam da OF, nao com
        # os 100 inteiros outra vez.
        existing = WorkAssignment(company_id=self.company.id, production_order_id=self.order.id, operation_id=self.operation.id, employee_id=self.employee.id, planned_quantity=60, status="in_progress")
        self.db.add(existing)
        self.db.flush()
        second = Employee(company_id=self.company.id, code="E2", name="Bruno", hourly_cost=6)
        self.db.add(second)
        self.db.flush()
        record_daily_output(self.db, self.company.id, {
            "production_order_id": self.order.id, "employee_id": second.id,
            "hours": 8, "quantity_good": 10,
        })
        self.db.commit()
        created = self.db.query(WorkAssignment).filter_by(employee_id=second.id).first()
        self.assertEqual(created.planned_quantity, 40)


if __name__ == "__main__":
    unittest.main()
