import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import ArticleType, ArticleTypeCost, Company, CostLine, CostSheet, Material, Operation, StockLot, Style
from backend.app.schemas.costing import ArticleTypeCostInput
from backend.app.services.cost_sheet_automation import (
    article_type_cost_template_view,
    cost_sheet_completeness,
    ensure_required_cost_lines,
    replace_article_type_cost_template,
)
from backend.app.services.proposal_wizard import wizard_catalog


class ArticleTypeCostTemplateTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="TF", name="TextileFlow", settings={"costing": {"overhead_per_piece": .25}})
        self.db.add(self.company)
        self.db.flush()
        self.article_type = ArticleType(
            company_id=self.company.id, code="POLO", name="Polo", category="top", default_unit="un", active=True,
        )
        self.db.add(self.article_type)
        self.db.flush()

    def tearDown(self):
        self.db.close()

    def test_unconfigured_type_has_safe_suggested_model(self):
        view = article_type_cost_template_view(self.db, self.article_type)
        self.assertFalse(view["configured"])
        roles = {row["role_key"] for row in view["lines"]}
        self.assertTrue({"main_fabric", "thread", "label", "packaging", "cutting", "sewing", "packing", "factory_overhead"}.issubset(roles))
        catalog = wizard_catalog(self.db, self.company.id)
        self.assertIn(str(self.article_type.id), catalog["article_type_templates"])

    def test_configured_costs_are_injected_and_use_weighted_stock_price(self):
        fabric = Material(
            company_id=self.company.id, code="PIQUE", name="Piqué 220g", category="fabric",
            unit="kg", unit_cost=9, last_cost=8, active=True,
        )
        sewing = Operation(
            company_id=self.company.id, code="SEW", name="Confeção polo", department="Confeção",
            standard_time_min=14, cost_per_minute=.18, active=True,
        )
        self.db.add_all([fabric, sewing])
        self.db.flush()
        self.db.add_all([
            StockLot(company_id=self.company.id, material_id=fabric.id, lot_no="L1", quantity=10, reserved=0, unit_cost=5),
            StockLot(company_id=self.company.id, material_id=fabric.id, lot_no="L2", quantity=30, reserved=0, unit_cost=7),
        ])
        replace_article_type_cost_template(self.db, self.article_type, [
            ArticleTypeCostInput(
                cost_group="fabric", role_key="main_fabric", material_id=fabric.id,
                description="Piqué principal", quantity=.4, unit="kg", waste_pct=5,
                unit_cost=9, use_live_price=True, required=True, sequence=10,
            ),
            ArticleTypeCostInput(
                cost_group="labor", role_key="sewing", operation_id=sewing.id,
                description="Confeção polo", quantity=14, unit="min", unit_cost=.12,
                use_live_price=True, required=True, sequence=20,
            ),
        ])
        style = Style(
            company_id=self.company.id, article_type_id=self.article_type.id,
            reference="POLO-1", description="Polo teste",
        )
        self.db.add(style)
        self.db.flush()
        sheet = CostSheet(
            company_id=self.company.id, style_id=style.id, status="draft", quantity_basis=100,
            selling_price=20, custom_data={"valid_until":"2026-09-30", "customer_id":1},
        )
        self.db.add(sheet)
        self.db.flush()

        ensure_required_cost_lines(self.db, sheet)
        templates = self.db.query(ArticleTypeCost).filter_by(article_type_id=self.article_type.id).order_by(ArticleTypeCost.sequence).all()
        fabric_line = self.db.query(CostLine).filter_by(cost_sheet_id=sheet.id, source_type=f"article_type_cost:{templates[0].id}").one()
        sewing_line = self.db.query(CostLine).filter_by(cost_sheet_id=sheet.id, source_type=f"article_type_cost:{templates[1].id}").one()
        self.assertAlmostEqual(fabric_line.quantity, .42, places=5)
        self.assertAlmostEqual(fabric_line.unit_cost, 6.5, places=5)
        self.assertAlmostEqual(sewing_line.unit_cost, .18, places=5)

    def test_required_type_cost_marks_sheet_incomplete_but_optional_cost_does_not(self):
        replace_article_type_cost_template(self.db, self.article_type, [
            ArticleTypeCostInput(
                cost_group="subcontract", role_key="special_finish", description="Acabamento especial",
                quantity=0, unit="un", unit_cost=0, use_live_price=False, required=True, sequence=10,
            ),
            ArticleTypeCostInput(
                cost_group="accessory", role_key="decorative_badge", description="Emblema opcional",
                quantity=0, unit="un", unit_cost=0, use_live_price=False, required=False, sequence=20,
            ),
        ])
        style = Style(
            company_id=self.company.id, article_type_id=self.article_type.id,
            reference="POLO-2", description="Polo especial",
        )
        self.db.add(style)
        self.db.flush()
        sheet = CostSheet(
            company_id=self.company.id, style_id=style.id, status="draft", quantity_basis=100,
            selling_price=20, custom_data={"valid_until":"2026-09-30", "customer_id":1},
        )
        self.db.add(sheet)
        self.db.flush()
        ensure_required_cost_lines(self.db, sheet)

        result = cost_sheet_completeness(self.db, sheet)
        type_check = next(item for item in result["checks"] if item["key"] == "article_type_template")
        self.assertFalse(type_check["complete"])
        self.assertIn("Acabamento especial", type_check["detail"])
        self.assertNotIn("Emblema opcional", type_check["detail"])


if __name__ == "__main__":
    unittest.main()

