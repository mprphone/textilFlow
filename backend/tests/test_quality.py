import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import Company, ProductionOrder, QualityInspection, Style
from backend.app.services.order_followup import followup_alerts
from backend.app.services.production_cockpit import order_cockpit
from backend.app.services.quality import aql_sample_plan


class AqlSamplePlanTest(unittest.TestCase):
    def test_sample_size_grows_with_lot_size(self):
        small = aql_sample_plan(20, 2.5)
        large = aql_sample_plan(5000, 2.5)
        self.assertLess(small["sample_size"], large["sample_size"])

    def test_sample_never_exceeds_lot_size(self):
        plan = aql_sample_plan(3, 2.5)
        self.assertLessEqual(plan["sample_size"], 3)

    def test_reject_is_accept_plus_one(self):
        plan = aql_sample_plan(1000, 2.5)
        self.assertEqual(plan["reject_min_defects"], plan["accept_max_defects"] + 1)

    def test_tighter_inspection_level_uses_bigger_sample(self):
        normal = aql_sample_plan(1000, 2.5, "II")
        strict = aql_sample_plan(1000, 2.5, "III")
        self.assertGreater(strict["sample_size"], normal["sample_size"])


class QualityDossierAlertTest(unittest.TestCase):
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

    def test_failed_inspection_surfaces_as_dossier_alert(self):
        self.db.add(QualityInspection(
            company_id=self.company.id, production_order_id=self.order.id, inspection_type="final",
            inspected_quantity=50, defect_quantity=10, defect_code="COSTURA", result="failed",
        ))
        self.db.commit()
        data = order_cockpit(self.db, self.order)
        alert_titles = [alert["title"] for alert in data["alerts"]]
        self.assertTrue(any("Qualidade reprovada" in title for title in alert_titles))

    def test_pending_inspection_does_not_alert(self):
        self.db.add(QualityInspection(
            company_id=self.company.id, production_order_id=self.order.id, inspection_type="final",
            inspected_quantity=50, defect_quantity=0, result="pending",
        ))
        self.db.commit()
        data = order_cockpit(self.db, self.order)
        alert_titles = [alert["title"] for alert in data["alerts"]]
        self.assertFalse(any("Qualidade reprovada" in title for title in alert_titles))


if __name__ == "__main__":
    unittest.main()
