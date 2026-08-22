import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    BOMItem, Company, CostLine, CostSheet, Customer, Material,
    ProductionMaterialRequirement, ProductionOrder, ProposalProductionRelease,
    SalesOrder, SalesOrderLine, StockLot, Style, User,
)
from backend.app.schemas import ProposalReleaseRequest, StockMovementRequest
from backend.app.services.costing import recalculate_sheet
from backend.app.services.inventory import register_movement
from backend.app.services.proposal_release import (
    ReleaseConflictError, ReleaseValidationError, category_breakdown, classify_cost_line,
    material_requirements_preview, production_preview, release_order_reservations,
    release_sheet_to_production,
)


class ProposalReleaseTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        self.db = self.Session()
        self.company = Company(code="T", name="Test Factory")
        self.user = User(username="admin", full_name="Admin", password_hash="test")
        self.db.add_all([self.company, self.user])
        self.db.flush()
        self.customer = Customer(company_id=self.company.id, code="C1", name="Customer")
        self.style = Style(company_id=self.company.id, reference="ST-1", description="T-shirt")
        self.fabric = Material(
            company_id=self.company.id, code="FAB", name="Jersey", category="fabric",
            unit="kg", unit_cost=5,
        )
        self.trim = Material(
            company_id=self.company.id, code="LBL", name="Label", category="trim",
            unit="un", unit_cost=.1,
        )
        self.db.add_all([self.customer, self.style, self.fabric, self.trim])
        self.db.flush()
        fabric_bom = BOMItem(
            company_id=self.company.id, style_id=self.style.id, material_id=self.fabric.id,
            quantity=2, unit="kg", waste_pct=0, unit_cost=5,
        )
        trim_bom = BOMItem(
            company_id=self.company.id, style_id=self.style.id, material_id=self.trim.id,
            quantity=1, unit="un", waste_pct=0, unit_cost=.1,
        )
        self.db.add_all([fabric_bom, trim_bom])
        self.db.flush()
        self.sheet = CostSheet(
            company_id=self.company.id, style_id=self.style.id, status="approved",
            quantity_basis=10, selling_price=20,
            custom_data={"customer_id": self.customer.id, "quote_no": "PROP-TEST"},
        )
        self.db.add(self.sheet)
        self.db.flush()
        self.db.add_all([
            CostLine(
                company_id=self.company.id, cost_sheet_id=self.sheet.id, category="material",
                description="Jersey", quantity=2, unit="kg", unit_cost=5, amount=10,
                source_type="bom", source_id=fabric_bom.id,
            ),
            CostLine(
                company_id=self.company.id, cost_sheet_id=self.sheet.id, category="material",
                description="Label", quantity=1, unit="un", unit_cost=.1, amount=.1,
                source_type="bom", source_id=trim_bom.id,
            ),
            CostLine(
                company_id=self.company.id, cost_sheet_id=self.sheet.id, category="labor",
                description="Sewing", quantity=4, unit="min", unit_cost=.2, amount=.8,
                source_type="operation",
            ),
            CostLine(
                company_id=self.company.id, cost_sheet_id=self.sheet.id, category="subcontract",
                description="Tinturaria reativa", quantity=1, unit="un", unit_cost=.6, amount=.6,
            ),
            CostLine(
                company_id=self.company.id, cost_sheet_id=self.sheet.id, category="subcontract",
                description="Estamparia", quantity=1, unit="un", unit_cost=.7, amount=.7,
            ),
            CostLine(
                company_id=self.company.id, cost_sheet_id=self.sheet.id, category="overhead",
                description="Indirect", quantity=1, unit="un", unit_cost=.5, amount=.5,
            ),
        ])
        self.db.flush()
        recalculate_sheet(self.db, self.sheet)
        self.db.add_all([
            StockLot(
                company_id=self.company.id, material_id=self.fabric.id, lot_no="FAB-1",
                quantity=8, reserved=0, unit_cost=4,
            ),
            StockLot(
                company_id=self.company.id, material_id=self.fabric.id, lot_no="FAB-2",
                quantity=7, reserved=0, unit_cost=6,
            ),
            StockLot(
                company_id=self.company.id, material_id=self.trim.id, lot_no="LBL-1",
                quantity=12, reserved=0, unit_cost=.2,
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_preview_uses_order_quantity_real_stock_and_explicit_cost_groups(self):
        requirements = material_requirements_preview(self.db, self.sheet, 10)
        fabric = next(row for row in requirements if row["material_id"] == self.fabric.id)
        self.assertEqual(fabric["material_category"], "fabric")
        self.assertEqual(fabric["unit_required"], 2)
        self.assertEqual(fabric["required_quantity"], 20)
        self.assertEqual(fabric["available_quantity"], 15)
        self.assertEqual(fabric["shortage_quantity"], 5)
        self.assertAlmostEqual(fabric["average_unit_cost"], 74 / 15, places=4)
        self.assertAlmostEqual(fabric["stock_valuation_unit_cost"], 4.95, places=4)

        groups = category_breakdown(self.db, self.sheet, 10)
        self.assertEqual(groups["fabric"]["unit_cost"], 10)
        self.assertEqual(groups["accessories"]["unit_cost"], .1)
        self.assertEqual(groups["dyeing"]["unit_cost"], .6)
        self.assertEqual(groups["printing"]["unit_cost"], .7)
        self.assertEqual(groups["overhead"]["unit_cost"], .5)

        preview = production_preview(self.db, self.sheet)
        self.assertTrue(preview["can_release"])
        self.assertEqual(preview["stock_summary"]["shortage_items"], 1)
        self.assertIn("cost_variance", preview)

    def test_manual_cost_family_survives_save_and_reload(self):
        fabric = CostLine(
            company_id=self.company.id, cost_sheet_id=self.sheet.id, category="material",
            description="Algodao penteado", quantity=1, unit="kg", unit_cost=3,
            amount=3, source_type="manual_fabric",
        )
        dyeing = CostLine(
            company_id=self.company.id, cost_sheet_id=self.sheet.id, category="subcontract",
            description="Lavagem especial", quantity=1, unit="un", unit_cost=.3,
            amount=.3, source_type="manual_dyeing",
        )
        self.db.add_all([fabric, dyeing])
        self.db.flush()
        self.assertEqual(classify_cost_line(self.db, self.sheet, fabric)["cost_group"], "fabric")
        self.assertEqual(classify_cost_line(self.db, self.sheet, dyeing)["cost_group"], "dyeing")

    def test_release_is_atomic_persistent_and_idempotent(self):
        payload = ProposalReleaseRequest(
            quantity=10, order_no="OF-TEST", priority=2,
            reserve_stock=True, idempotency_key="release-test",
        )
        release, replayed = release_sheet_to_production(self.db, self.sheet.id, payload, self.user.id)
        self.assertFalse(replayed)
        self.db.commit()
        self.db.refresh(release)

        self.assertEqual(self.db.get(CostSheet, self.sheet.id).status, "production")
        self.assertEqual(self.db.query(ProposalProductionRelease).count(), 1)
        self.assertEqual(self.db.query(SalesOrder).count(), 1)
        self.assertEqual(self.db.query(SalesOrderLine).count(), 1)
        self.assertEqual(self.db.query(ProductionOrder).count(), 1)
        self.assertEqual(self.db.query(ProductionMaterialRequirement).count(), 2)
        fabric_requirement = self.db.query(ProductionMaterialRequirement).filter_by(material_id=self.fabric.id).one()
        self.assertEqual(fabric_requirement.required_quantity, 20)
        self.assertEqual(fabric_requirement.reserved_quantity, 15)
        self.assertEqual(fabric_requirement.shortage_quantity, 5)
        self.assertEqual(
            sum(row.reserved for row in self.db.query(StockLot).filter_by(material_id=self.fabric.id).all()),
            15,
        )

        replay, replayed = release_sheet_to_production(self.db, self.sheet.id, payload, self.user.id)
        self.db.commit()
        self.assertTrue(replayed)
        self.assertEqual(replay.id, release.id)
        self.assertEqual(self.db.query(ProposalProductionRelease).count(), 1)
        self.assertEqual(self.db.query(ProductionOrder).count(), 1)
        self.assertEqual(self.db.query(ProductionMaterialRequirement).count(), 2)
        self.assertEqual(
            sum(row.reserved for row in self.db.query(StockLot).filter_by(material_id=self.fabric.id).all()),
            15,
        )

    def test_invalid_customer_does_not_create_release_or_orders(self):
        self.sheet.custom_data = {"customer_id": 999999}
        self.db.commit()
        with self.assertRaises(ReleaseValidationError):
            release_sheet_to_production(
                self.db, self.sheet.id, ProposalReleaseRequest(quantity=10), self.user.id,
            )
        self.db.rollback()
        self.assertEqual(self.db.query(ProposalProductionRelease).count(), 0)
        self.assertEqual(self.db.query(SalesOrder).count(), 0)
        self.assertEqual(self.db.query(ProductionOrder).count(), 0)
        self.assertEqual(self.db.get(CostSheet, self.sheet.id).status, "approved")

    def test_draft_cannot_bypass_commercial_acceptance(self):
        self.sheet.status = "draft"
        self.db.commit()
        with self.assertRaises(ReleaseConflictError):
            release_sheet_to_production(
                self.db, self.sheet.id, ProposalReleaseRequest(quantity=10), self.user.id,
            )
        self.db.rollback()
        self.assertEqual(self.db.query(ProposalProductionRelease).count(), 0)
        self.assertEqual(self.db.query(ProductionOrder).count(), 0)

    def test_cancelling_an_order_releases_remaining_reservations_idempotently(self):
        release, _ = release_sheet_to_production(
            self.db,
            self.sheet.id,
            ProposalReleaseRequest(quantity=10, reserve_stock=True),
            self.user.id,
        )
        self.db.commit()
        order = self.db.get(ProductionOrder, release.production_order_id)
        self.assertGreater(sum(row.reserved for row in self.db.query(StockLot).all()), 0)

        released = release_order_reservations(self.db, order)
        order.status = "cancelled"
        self.db.commit()
        self.assertGreater(released, 0)
        self.assertEqual(sum(row.reserved for row in self.db.query(StockLot).all()), 0)
        self.assertTrue(all(
            row.reserved_quantity == 0
            for row in self.db.query(ProductionMaterialRequirement).all()
        ))
        self.assertEqual(release_order_reservations(self.db, order), 0)

    def test_consumption_respects_and_releases_the_order_reservation(self):
        release, _ = release_sheet_to_production(
            self.db,
            self.sheet.id,
            ProposalReleaseRequest(quantity=10, reserve_stock=True),
            self.user.id,
        )
        self.db.commit()
        lot = self.db.query(StockLot).filter_by(material_id=self.fabric.id).order_by(StockLot.id).first()
        with self.assertRaises(HTTPException):
            register_movement(
                self.db,
                company_id=self.company.id,
                user_id=self.user.id,
                payload=StockMovementRequest(stock_lot_id=lot.id, movement_type="consume", quantity=1),
            )
        self.db.rollback()

        movement = register_movement(
            self.db,
            company_id=self.company.id,
            user_id=self.user.id,
            payload=StockMovementRequest(
                stock_lot_id=lot.id,
                movement_type="consume",
                quantity=3,
                production_order_id=release.production_order_id,
            ),
        )
        self.db.commit()
        self.assertEqual(movement.quantity, -3)
        self.assertEqual(lot.quantity, 5)
        self.assertEqual(lot.reserved, 5)
        requirement = self.db.query(ProductionMaterialRequirement).filter_by(material_id=self.fabric.id).one()
        self.assertEqual(requirement.reserved_quantity, 12)


if __name__ == "__main__":
    unittest.main()
