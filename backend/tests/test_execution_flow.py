import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    BatchGenealogy, Company, Operation, OperationalAlert, ProductOperation,
    ProductionBatch, ProductionLine, ProductionMovement, ProductionOrder,
    QualityInspection, Style, WorkAssignment,
)
from backend.app.services.control_tower import finite_plan, refresh_alerts
from backend.app.services.execution import batch_trace, split_batch, sync_quality_movement, transfer_operation


class ExecutionFlowTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.flush()
        self.style = Style(company_id=self.company.id, reference="ST", description="Tee")
        self.line = ProductionLine(company_id=self.company.id, code="L1", name="Linha 1", capacity_minutes_day=480, target_efficiency=100)
        op1 = Operation(company_id=self.company.id, code="O1", name="Montagem")
        op2 = Operation(company_id=self.company.id, code="O2", name="Remate")
        self.db.add_all([self.style, self.line, op1, op2])
        self.db.flush()
        self.step1 = ProductOperation(company_id=self.company.id, style_id=self.style.id, operation_id=op1.id, sequence=10, smv=2)
        self.step2 = ProductOperation(company_id=self.company.id, style_id=self.style.id, operation_id=op2.id, sequence=20, smv=1)
        self.db.add_all([self.step1, self.step2])
        self.db.flush()
        self.order = ProductionOrder(company_id=self.company.id, style_id=self.style.id, line_id=self.line.id, order_no="OF-1", quantity=100, status="in_progress", planned_end=date.today() - timedelta(days=1))
        self.db.add(self.order)
        self.db.flush()
        self.a1 = WorkAssignment(company_id=self.company.id, production_order_id=self.order.id, product_operation_id=self.step1.id, operation_id=op1.id, planned_quantity=100, completed_quantity=50)
        self.a2 = WorkAssignment(company_id=self.company.id, production_order_id=self.order.id, product_operation_id=self.step2.id, operation_id=op2.id, planned_quantity=100)
        self.db.add_all([self.a1, self.a2])
        self.db.flush()

    def test_partial_transfer_respects_operation_balance(self):
        result = transfer_operation(self.db, self.order, {"product_operation_id": self.step1.id, "quantity": 30})
        self.assertEqual(result["flow"]["steps"][0]["available_to_transfer"], 20)
        self.assertEqual(result["flow"]["steps"][1]["received_quantity"], 30)
        with self.assertRaisesRegex(ValueError, "20"):
            transfer_operation(self.db, self.order, {"product_operation_id": self.step1.id, "quantity": 21})

    def test_last_operation_transfers_partially_to_revista(self):
        self.a2.completed_quantity = 35
        transfer_operation(self.db, self.order, {"product_operation_id": self.step2.id, "quantity": 25})
        self.assertEqual(self.order.custom_data["revista_quantity"], 25)
        self.assertEqual(self.db.query(ProductionMovement).filter_by(movement_type="operation_transfer").count(), 1)

    def test_batch_split_has_complete_recursive_genealogy(self):
        parent = ProductionBatch(company_id=self.company.id, production_order_id=self.order.id, batch_no="B1", quantity=100)
        self.db.add(parent)
        self.db.flush()
        children = split_batch(self.db, parent, [{"quantity": 40}, {"quantity": 60}])
        grandchildren = split_batch(self.db, children[0], [{"quantity": 10}, {"quantity": 30}])
        trace = batch_trace(self.db, grandchildren[0])
        self.assertEqual(len(trace["batches"]), 5)
        self.assertEqual(self.db.query(BatchGenealogy).count(), 4)
        with self.assertRaisesRegex(ValueError, "igual"):
            split_batch(self.db, children[1], [{"quantity": 20}])

    def test_quality_decision_creates_release_movement(self):
        inspection = QualityInspection(company_id=self.company.id, production_order_id=self.order.id, inspection_type="revista", inspected_quantity=20, defect_quantity=2, result="conditional")
        self.db.add(inspection)
        self.db.flush()
        sync_quality_movement(self.db, inspection)
        self.assertEqual(inspection.released_quantity, 18)
        self.assertEqual(inspection.rework_quantity, 2)
        self.assertEqual(self.db.query(ProductionMovement).filter_by(movement_type="quality_release").one().quantity, 18)

    def test_finite_plan_and_persistent_alerts(self):
        plan = finite_plan(self.db, self.company.id)
        self.assertEqual(plan["orders"][0]["production_order_id"], self.order.id)
        self.assertEqual(plan["orders"][0]["required_minutes"], 300)
        alerts = refresh_alerts(self.db, self.company.id, plan)
        self.assertTrue(any(row.code == "overdue" for row in alerts))
        self.assertEqual(self.db.query(OperationalAlert).filter_by(status="open").count(), len(alerts))


if __name__ == "__main__":
    unittest.main()
