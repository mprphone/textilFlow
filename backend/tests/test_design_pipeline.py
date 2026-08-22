import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import Company, Customer, Style, User
from backend.app.services import design as service
from backend.app.services.design_pipeline import DesignError, get_next_action, is_archived


class DesignPipelineTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Atelier")
        self.db.add(self.company)
        self.db.flush()
        self.customer = Customer(company_id=self.company.id, code="B001", name="Brownie")
        self.user = User(username="isabel", full_name="Isabel Fernandes", password_hash="x")
        self.partner = User(username="ines", full_name="Inês Jorge", password_hash="x")
        self.db.add_all([self.customer, self.user, self.partner])
        self.db.commit()

    def create(self, **overrides):
        payload = {
            "customer_id": self.customer.id,
            "request_source": "whatsapp",
            "request_group": "Brownie julho",
            "request_notes": "Cliente enviou duas inspirações",
            "models": [{
                "title": "Malha teste",
                "code": "IF_B001_001",
                "user_ids": [self.user.id],
                "quantity": 1200,
            }],
        }
        payload.update(overrides)
        return service.create_developments(self.db, self.company.id, payload)[0]

    def test_create_starts_at_pedido_recebido(self):
        item = self.create()
        data = service.serialize_development(item)
        self.assertEqual(data["current_stage"], "novo")
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["request_group"], "Brownie julho")
        self.assertEqual(data["requested_quantity"], 1200)
        self.assertEqual(data["owner_name"], "Isabel Fernandes")
        self.assertEqual(data["assignees"][0]["role"], "principal")
        self.assertEqual(data["next_action"], "Registar pedido, fotografias e referências")

    def test_next_reference_uses_client_code_and_designer_initials(self):
        first = service.next_reference(self.db, self.company.id, self.customer.id, [self.user.id])
        self.assertEqual(first["reference"], "IF_B001_001")
        self.create()
        partnership = service.next_reference(self.db, self.company.id, self.customer.id, [self.user.id, self.partner.id])
        self.assertEqual(partnership["sequence"], 2)
        self.assertEqual(partnership["reference"], "II_B001_002")

    def test_move_to_ficha_creates_style(self):
        item = self.create()
        moved = service.move_development(self.db, self.company.id, item.id, {"to_stage": "ficha_tecnica"})
        self.assertEqual(moved.current_stage, "ficha_tecnica")
        self.assertTrue(moved.style_id)
        style = self.db.get(Style, moved.style_id)
        self.assertEqual(style.reference, "IF_B001_001")
        self.assertEqual(style.workflow_stage, "ficha_tecnica")
        self.assertEqual(style.lifecycle_status, "development")

    def test_approval_only_after_client_response(self):
        item = self.create()
        with self.assertRaises(DesignError):
            service.move_development(self.db, self.company.id, item.id, {"to_stage": "aprovado"})
        service.move_development(self.db, self.company.id, item.id, {"to_stage": "proposta_cliente"})
        service.move_development(self.db, self.company.id, item.id, {"to_stage": "ficha_tecnica"})
        service.move_development(self.db, self.company.id, item.id, {"to_stage": "envio_cliente"})
        waiting = service.move_development(self.db, self.company.id, item.id, {"to_stage": "resposta_cliente"})
        self.assertEqual(waiting.status, "waiting_client")
        self.assertEqual(get_next_action(waiting), "Pedir resposta ao cliente")
        approved = service.move_development(self.db, self.company.id, item.id, {"to_stage": "aprovado"})
        self.assertEqual(approved.status, "completed")
        self.assertEqual(approved.style.lifecycle_status, "approved")

    def test_retificacoes_return_to_envio(self):
        item = self.create()
        with self.assertRaises(DesignError):
            service.move_development(self.db, self.company.id, item.id, {"to_stage": "retificacoes"})
        service.move_development(self.db, self.company.id, item.id, {"to_stage": "envio_cliente"})
        service.move_development(self.db, self.company.id, item.id, {"to_stage": "resposta_cliente"})
        fixed = service.move_development(self.db, self.company.id, item.id, {"to_stage": "retificacoes", "note": "Gola mais baixa"})
        self.assertEqual(fixed.current_stage, "retificacoes")
        resent = service.move_development(self.db, self.company.id, item.id, {"to_stage": "envio_cliente"})
        self.assertEqual(resent.current_stage, "envio_cliente")

    def test_waiting_reason_is_kept_in_history(self):
        item = self.create()
        service.patch_development(self.db, self.company.id, item.id, {"status": "blocked", "waiting_reason": "Falta validar medidas"})
        service.move_development(self.db, self.company.id, item.id, {"to_stage": "modelagem"})
        detail = service.serialize_detail(self.db, service.get_development(self.db, self.company.id, item.id))
        closed = [event for event in detail["stage_history"] if event["status"] == "completed"]
        self.assertTrue(any(event["note"] and "Falta validar medidas" in event["note"] for event in closed))

    def test_rejected_is_archived_and_out_of_today(self):
        item = self.create()
        service.patch_development(self.db, self.company.id, item.id, {
            "status": "rejected", "waiting_reason": "Cliente não gostou da gola",
        })
        loaded = service.get_development(self.db, self.company.id, item.id)
        self.assertTrue(is_archived(loaded))
        board = service.today_dashboard(self.db, self.company.id)
        self.assertTrue(all(row["id"] != item.id for row in board["priorities"]))

    def test_overdue_rises_to_today_priorities(self):
        item = self.create()
        service.patch_development(self.db, self.company.id, item.id, {
            "due_date": (date.today() - timedelta(days=2)).isoformat(),
        })
        board = service.today_dashboard(self.db, self.company.id)
        self.assertGreaterEqual(board["overdue_count"], 1)
        self.assertEqual(board["priorities"][0]["id"], item.id)
        self.assertEqual(board["priorities"][0]["risk"], "high")

    def test_parallel_tasks_drive_next_action(self):
        item = self.create()
        service.add_task(self.db, self.company.id, item.id, {"kind": "malha", "note": "Pedir 80m crua"})
        loaded = service.get_development(self.db, self.company.id, item.id)
        self.assertIn("malha", get_next_action(loaded).lower())

    def test_organization_groups_by_designer_and_client(self):
        self.create()
        service.create_developments(self.db, self.company.id, {
            "customer_id": self.customer.id,
            "models": [{"title": "Casaco", "code": "IJ_B001_002", "user_ids": [self.partner.id]}],
        })
        org = service.organization_board(self.db, self.company.id)
        names = [row["name"] for row in org["designers"]]
        self.assertIn("Isabel Fernandes", names)
        self.assertIn("Inês Jorge", names)
        self.assertEqual(org["clients"][0]["name"], "Brownie")

    def test_approved_creates_production_and_sample(self):
        item = self.create()
        service.move_development(self.db, self.company.id, item.id, {"to_stage": "resposta_cliente"})
        service.move_development(self.db, self.company.id, item.id, {"to_stage": "aprovado"})
        result = service.create_production(self.db, self.company.id, item.id, {"quantity": 800})
        self.assertFalse(result["already_released"])
        loaded = service.get_development(self.db, self.company.id, item.id)
        self.assertTrue(loaded.production_order_id)
        self.assertTrue(loaded.sample_id)
        again = service.create_production(self.db, self.company.id, item.id, {"quantity": 800})
        self.assertTrue(again["already_released"])


if __name__ == "__main__":
    unittest.main()
