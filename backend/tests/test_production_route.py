import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    Company, CuttingJob, Customer, ProductionOrder, ProductionRouteStep, SalesOrder, SalesOrderLine,
    Style, SubcontractJob, SubcontractService, Supplier,
)
from backend.app.services.order_followup import assert_can_distribute, service_plan
from backend.app.services.production_split import distribute
from backend.app.services.production_stage import assert_subcontract_ready


class ProductionRouteTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.flush()
        self.customer = Customer(company_id=self.company.id, code="C", name="Cliente")
        self.style = Style(company_id=self.company.id, reference="ST", description="T-shirt")
        self.db.add_all([self.customer, self.style])
        self.db.flush()
        sales = SalesOrder(company_id=self.company.id, customer_id=self.customer.id, order_no="EC-1", delivery_date=date.today() + timedelta(days=10))
        self.db.add(sales)
        self.db.flush()
        line = SalesOrderLine(company_id=self.company.id, sales_order_id=sales.id, style_id=self.style.id, quantity=20, unit_price=10, delivery_date=sales.delivery_date)
        self.db.add(line)
        self.db.flush()
        self.order = ProductionOrder(
            company_id=self.company.id, sales_order_line_id=line.id, style_id=self.style.id,
            order_no="OF-1", quantity=20, status="planned",
        )
        self.db.add(self.order)
        self.db.flush()
        self.supplier = Supplier(company_id=self.company.id, code="TIN", name="Tinturaria", supplier_type="dyeing")
        self.db.add(self.supplier)
        self.db.flush()
        self.dye = SubcontractService(company_id=self.company.id, supplier_id=self.supplier.id, code="D", name="Tingir peça", category="dyeing", unit="un")
        self.db.add(self.dye)
        self.db.flush()

    def test_no_route_falls_back_to_legacy_cutting_first_rule(self):
        # Sem nenhum ProductionRouteStep, aplica-se a regra antiga: corte tem de
        # comecar antes de qualquer subcontrato (aqui o corte nunca comecou).
        service = self.dye
        result = assert_subcontract_ready(self.db, self.order, service)
        self.assertFalse(result["ready"])
        self.assertIn("Corte", result["reason"])

    def test_route_dye_fabric_before_cutting(self):
        # Malha: tingir -> cortar -> coser. Deve poder enviar a tingir mesmo
        # sem o corte ter comecado, porque a rota diz que tingir vem primeiro.
        self.db.add_all([
            ProductionRouteStep(company_id=self.company.id, style_id=self.style.id, sequence=10, step_type="subcontract", subcontract_service_id=self.dye.id, is_required=True),
            ProductionRouteStep(company_id=self.company.id, style_id=self.style.id, sequence=20, step_type="cutting", is_required=True),
            ProductionRouteStep(company_id=self.company.id, style_id=self.style.id, sequence=30, step_type="sewing", is_required=True),
        ])
        self.db.commit()
        # Nao deve levantar excecao: tingir a malha e o primeiro passo da rota.
        assert_can_distribute(self.db, self.order, {"destination": "subcontract", "subcontract_service_id": self.dye.id, "quantity": 20})
        result = distribute(self.db, self.order, {"source": "unassigned", "destination": "subcontract", "subcontract_service_id": self.dye.id, "quantity": 20})
        self.assertEqual(result["holdings"]["external"], 20)

    def test_route_sew_piece_before_dyeing(self):
        # Peca: cortar -> coser -> tingir a peca. Com o corte ja concluido, a
        # confecao interna deve estar livre e o envio a tingir so depois da
        # confecao terminar.
        self.db.add_all([
            ProductionRouteStep(company_id=self.company.id, style_id=self.style.id, sequence=10, step_type="cutting", is_required=True),
            ProductionRouteStep(company_id=self.company.id, style_id=self.style.id, sequence=20, step_type="sewing", is_required=True),
            ProductionRouteStep(company_id=self.company.id, style_id=self.style.id, sequence=30, step_type="subcontract", subcontract_service_id=self.dye.id, is_required=True),
            CuttingJob(company_id=self.company.id, production_order_id=self.order.id, planned_pieces=20, good_pieces=20, status="completed"),
        ])
        self.db.commit()
        steps = service_plan(self.db, self.order, [], 0)
        sewing = next(step for step in steps if step["key"] == "sewing")
        dyeing = next(step for step in steps if step["key"] == "dyeing")
        self.assertFalse(sewing["locked"])
        self.assertTrue(dyeing["locked"])
        with self.assertRaises(ValueError):
            distribute(self.db, self.order, {"source": "unassigned", "destination": "subcontract", "subcontract_service_id": self.dye.id, "quantity": 20})


if __name__ == "__main__":
    unittest.main()
