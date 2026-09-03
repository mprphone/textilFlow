import os
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.logging_setup import inprocess_workers_enabled
from backend.app.models import BOMItem, Company, Material, ProductionOrder, SewingPlan, StockLot, Style
from backend.app.services.modules import CORE_MODULES, enabled_modules
from backend.app.services.mrp import week_material_plan, week_monday


class WorkerEnvTest(unittest.TestCase):
    def test_inprocess_workers_default_on(self):
        with patch.dict(os.environ, {"RUN_INPROCESS_WORKERS": "1"}):
            self.assertTrue(inprocess_workers_enabled())

    def test_inprocess_workers_can_disable(self):
        with patch.dict(os.environ, {"RUN_INPROCESS_WORKERS": "0"}):
            self.assertFalse(inprocess_workers_enabled())


class WarehouseModuleTest(unittest.TestCase):
    def test_core_includes_warehouse(self):
        self.assertIn("warehouse", CORE_MODULES)

    def test_existing_shipping_company_gains_warehouse(self):
        company = Company(code="T", name="T", settings={"enabled_modules": ["overview", "shipping", "erp"]})
        modules = enabled_modules(company)
        self.assertIn("warehouse", modules)
        self.assertEqual(modules.index("warehouse"), modules.index("shipping") + 1)


class MrpWeekTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.flush()
        self.style = Style(company_id=self.company.id, reference="TEE", description="T-shirt")
        self.fabric = Material(company_id=self.company.id, code="MALHA", name="Malha", unit="kg", category="fabric")
        self.db.add_all([self.style, self.fabric])
        self.db.flush()
        self.db.add(BOMItem(
            company_id=self.company.id, style_id=self.style.id, material_id=self.fabric.id,
            quantity=0.25, unit="kg", waste_pct=0, unit_cost=4,
        ))
        self.order = ProductionOrder(
            company_id=self.company.id, style_id=self.style.id, order_no="OF-1",
            quantity=100, status="planned", planned_start=date.today(),
        )
        self.db.add(self.order)
        self.db.flush()
        start = week_monday()
        self.db.add(SewingPlan(
            company_id=self.company.id, code="SP-1", production_order_id=self.order.id,
            start_date=start, end_date=start + timedelta(days=2), quantity=40, status="planned",
        ))
        self.db.add(StockLot(
            company_id=self.company.id, material_id=self.fabric.id, lot_no="L1",
            quantity=2, reserved=0,
        ))
        self.db.commit()

    def test_week_plan_scales_bom_to_scheduled_qty_and_flags_shortage(self):
        plan = week_material_plan(self.db, self.company.id, pull_primavera=False)
        self.assertEqual(plan["plan_count"], 1)
        self.assertEqual(plan["order_count"], 1)
        row = next(item for item in plan["items"] if item["material_id"] == self.fabric.id)
        self.assertAlmostEqual(row["required"], 10.0, places=3)
        self.assertAlmostEqual(row["available_local"], 2.0, places=3)
        self.assertEqual(row["status"], "shortage")
        self.assertGreater(row["shortage"], 0)

    def test_week_plan_prefers_primavera_available(self):
        primavera = {
            "ok": True, "count": 1, "path": "Inventory/ItemWarehouses",
            "items": [{"item": "MALHA", "warehouse": "A1", "quantity": 20, "reserved": 0, "available": 20}],
        }
        with patch("backend.app.services.mrp.fetch_stock", return_value=primavera):
            plan = week_material_plan(self.db, self.company.id, pull_primavera=True)
        row = next(item for item in plan["items"] if item["material_id"] == self.fabric.id)
        self.assertEqual(row["status"], "ok")
        self.assertAlmostEqual(row["available"], 20.0, places=3)
        self.assertAlmostEqual(row["primavera_available"], 20.0, places=3)


if __name__ == "__main__":
    unittest.main()
