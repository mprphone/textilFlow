import unittest
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    Company, CostSheet, Customer, Department, Employee, Material, Operation, OverheadCost,
    ProductOperation, ProductionEvent, ProductionLine, ProductionOrder, Style,
)
from backend.app.services.analytics import employee_performance, line_performance
from backend.app.services.cost_control import _overhead_allocation
from backend.app.services.costing import rebuild_product_cost


class EfficiencyUsesStyleSmvTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.flush()
        # Tempo generico da operacao (2 min) e bem diferente do SMV real do
        # artigo (0.5 min) - se o calculo usar o generico, a eficiencia sai
        # muito acima de 100%; usando o SMV certo, fica proximo de 100%.
        self.operation = Operation(company_id=self.company.id, code="OP1", name="Bainha", standard_time_min=2, cost_per_minute=0.1)
        self.style = Style(company_id=self.company.id, reference="ST", description="Tee")
        self.line = ProductionLine(company_id=self.company.id, code="L1", name="Linha 1", capacity_minutes_day=480)
        self.employee = Employee(company_id=self.company.id, code="E1", name="Ana", hourly_cost=6, line_id=None)
        self.db.add_all([self.operation, self.style, self.line, self.employee])
        self.db.flush()
        self.db.add(ProductOperation(company_id=self.company.id, style_id=self.style.id, operation_id=self.operation.id, sequence=10, smv=0.5))
        self.order = ProductionOrder(company_id=self.company.id, style_id=self.style.id, order_no="OF-1", quantity=100, status="in_progress")
        self.db.add(self.order)
        self.db.flush()
        # 60 pecas boas em 30 minutos: ao SMV certo (0.5 min/peca) da 30 min
        # ganhos / 30 min reais = 100% de eficiencia.
        self.db.add(ProductionEvent(
            company_id=self.company.id, production_order_id=self.order.id, operation_id=self.operation.id,
            employee_id=self.employee.id, line_id=self.line.id, quantity_good=60, duration_minutes=30,
            event_time=datetime.now(timezone.utc),
        ))
        self.db.commit()

    def test_line_performance_uses_style_smv_not_generic_operation_time(self):
        rows = line_performance(self.db, self.company.id)
        line_row = next(row for row in rows if row["id"] == self.line.id)
        self.assertAlmostEqual(line_row["efficiency"], 100.0, places=1)

    def test_employee_performance_uses_style_smv_not_generic_operation_time(self):
        rows = employee_performance(self.db, self.company.id)
        emp_row = next(row for row in rows if row["id"] == self.employee.id)
        self.assertAlmostEqual(emp_row["efficiency"], 100.0, places=1)


class MachineCostLineTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.flush()
        self.style = Style(company_id=self.company.id, reference="ST", description="Tee")
        self.operation = Operation(company_id=self.company.id, code="OP1", name="Costura", standard_time_min=2, cost_per_minute=0.1, machine_cost_per_minute=0.05)
        self.db.add_all([self.style, self.operation])
        self.db.flush()
        self.db.add(ProductOperation(company_id=self.company.id, style_id=self.style.id, operation_id=self.operation.id, sequence=10, smv=2))
        self.sheet = CostSheet(company_id=self.company.id, style_id=self.style.id, status="draft")
        self.db.add(self.sheet)
        self.db.commit()

    def test_rebuild_generates_machine_line_when_rate_configured(self):
        rebuild_product_cost(self.db, self.sheet)
        self.db.commit()
        self.assertGreater(self.sheet.machine_cost, 0)
        self.assertAlmostEqual(self.sheet.machine_cost, 2 * 0.05, places=4)
        self.assertGreater(self.sheet.labor_cost, 0)


class OverheadAllocationBasisTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.flush()
        self.style = Style(company_id=self.company.id, reference="ST", description="Tee")
        self.operation = Operation(company_id=self.company.id, code="OP1", name="Costura", standard_time_min=1, cost_per_minute=0.1)
        self.db.add_all([self.style, self.operation])
        self.db.flush()
        self.order_a = ProductionOrder(company_id=self.company.id, style_id=self.style.id, order_no="OF-A", quantity=100, status="in_progress")
        self.order_b = ProductionOrder(company_id=self.company.id, style_id=self.style.id, order_no="OF-B", quantity=100, status="in_progress")
        self.db.add_all([self.order_a, self.order_b])
        self.db.flush()
        now = datetime.now(timezone.utc)
        # OF A produz 30 unidades, OF B produz 70 - se o rateio for por
        # unidades, A deve ficar com 30% do custo geral, nao com metade.
        self.db.add(ProductionEvent(company_id=self.company.id, production_order_id=self.order_a.id, operation_id=self.operation.id, quantity_good=30, duration_minutes=100, event_time=now))
        self.db.add(ProductionEvent(company_id=self.company.id, production_order_id=self.order_b.id, operation_id=self.operation.id, quantity_good=70, duration_minutes=100, event_time=now))
        self.db.add(OverheadCost(
            company_id=self.company.id, category="rent", description="Renda", amount=1000,
            period_start=date.today() - timedelta(days=1), period_end=date.today() + timedelta(days=1),
            allocation_basis="units",
        ))
        self.db.commit()

    def test_allocation_by_units_not_minutes(self):
        amount, entries = _overhead_allocation(self.db, self.order_a)
        # 30 de 100 unidades totais = 30% de 1000 = 300 (nao 500, que seria por
        # minutos, ja que ambas as OFs tem a mesma duracao).
        self.assertAlmostEqual(amount, 300, places=2)


if __name__ == "__main__":
    unittest.main()
