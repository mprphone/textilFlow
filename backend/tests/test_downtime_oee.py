import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    Company, DowntimeEvent, Operation, ProductOperation, ProductionEvent,
    ProductionLine, ProductionOrder, Style,
)
from backend.app.services.analytics import downtime_summary


class DowntimeOeeTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.flush()
        self.line = ProductionLine(company_id=self.company.id, code="L1", name="Linha 1")
        self.style = Style(company_id=self.company.id, reference="ST", description="Tee")
        self.operation = Operation(company_id=self.company.id, code="OP1", name="Costura", standard_time_min=1)
        self.db.add_all([self.line, self.style, self.operation])
        self.db.flush()
        self.db.add(ProductOperation(company_id=self.company.id, style_id=self.style.id, operation_id=self.operation.id, sequence=10, smv=1))
        self.order = ProductionOrder(company_id=self.company.id, style_id=self.style.id, order_no="OF-1", quantity=100, status="in_progress")
        self.db.add(self.order)
        self.db.flush()

    def test_downtime_reduces_availability_and_oee(self):
        now = datetime.now(timezone.utc)
        self.db.add(ProductionEvent(
            company_id=self.company.id, production_order_id=self.order.id, operation_id=self.operation.id,
            line_id=self.line.id, quantity_good=81, quantity_rejected=9, duration_minutes=90, event_time=now,
        ))
        self.db.add(DowntimeEvent(
            company_id=self.company.id, line_id=self.line.id, reason_code="breakdown", reason="Avaria da máquina",
            started_at=now - timedelta(minutes=10), duration_minutes=10,
        ))
        self.db.commit()
        result = downtime_summary(self.db, self.company.id)
        line_row = next(row for row in result["lines"] if row["id"] == self.line.id)
        # 90 min produtivos + 10 min parado = disponibilidade de 90%.
        self.assertAlmostEqual(line_row["availability_pct"], 90.0, places=1)
        self.assertLess(line_row["oee_pct"], line_row["availability_pct"])
        self.assertEqual(result["reasons"][0]["reason_code"], "breakdown")
        self.assertAlmostEqual(result["total_downtime_minutes"], 10.0, places=1)

    def test_no_activity_line_is_omitted(self):
        result = downtime_summary(self.db, self.company.id)
        self.assertFalse(any(row["id"] == self.line.id for row in result["lines"]))


if __name__ == "__main__":
    unittest.main()
