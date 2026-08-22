import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    ActualCostEntry, BOMItem, Company, CuttingJob, Material, ProductionOrder, Style,
)
from backend.app.services.cost_control import actual_order_cost


class ExtraCostCategoriesTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.flush()
        self.style = Style(company_id=self.company.id, reference="ST", description="Tee")
        self.db.add(self.style)
        self.db.flush()
        self.order = ProductionOrder(company_id=self.company.id, style_id=self.style.id, order_no="OF-1", quantity=100, status="in_progress")
        self.db.add(self.order)
        self.db.flush()

    def test_energy_and_packaging_entries_are_not_dropped_from_totals(self):
        self.db.add_all([
            ActualCostEntry(company_id=self.company.id, production_order_id=self.order.id, category="energy", description="Eletricidade", quantity=1, unit="kWh", unit_cost=50, amount=50, occurred_on=date.today()),
            ActualCostEntry(company_id=self.company.id, production_order_id=self.order.id, category="packaging", description="Caixas", quantity=1, unit="un", unit_cost=30, amount=30, occurred_on=date.today()),
            ActualCostEntry(company_id=self.company.id, production_order_id=self.order.id, category="transport", description="Portes", quantity=1, unit="un", unit_cost=20, amount=20, occurred_on=date.today()),
        ])
        self.db.commit()
        result = actual_order_cost(self.db, self.order)
        self.assertEqual(result["totals"]["energy"], 50)
        self.assertEqual(result["totals"]["packaging"], 30)
        self.assertEqual(result["totals"]["transport"], 20)


class CuttingWasteCostLineTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.flush()
        self.style = Style(company_id=self.company.id, reference="ST", description="Tee")
        self.fabric = Material(company_id=self.company.id, code="FAB", name="Malha", category="malha", unit="kg", unit_cost=5)
        self.db.add_all([self.style, self.fabric])
        self.db.flush()
        self.db.add(BOMItem(company_id=self.company.id, style_id=self.style.id, material_id=self.fabric.id, quantity=0.5, unit="kg", waste_pct=5, unit_cost=5))
        self.order = ProductionOrder(company_id=self.company.id, style_id=self.style.id, order_no="OF-1", quantity=100, status="in_progress")
        self.db.add(self.order)
        self.db.commit()

    def test_waste_above_plan_creates_actual_cost_entry(self):
        from backend.app.api.routes.resources import _track_cutting_waste_cost
        job = CuttingJob(
            company_id=self.company.id, production_order_id=self.order.id,
            planned_fabric=50, actual_fabric=60, status="in_progress",
        )
        self.db.add(job)
        self.db.flush()
        _track_cutting_waste_cost(self.db, job)
        self.db.commit()
        entry = self.db.query(ActualCostEntry).filter_by(reference=f"corte-{job.id}").first()
        self.assertIsNotNone(entry)
        self.assertAlmostEqual(entry.quantity, 10, places=2)
        self.assertAlmostEqual(entry.amount, 50, places=2)  # 10kg extra x 5/kg


if __name__ == "__main__":
    unittest.main()
