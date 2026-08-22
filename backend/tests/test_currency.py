import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import (
    BOMItem, Company, CostLine, CostSheet, CuttingJob, ExchangeRate, Material,
    Operation, ProductOperation, ProductionEvent, ProductionOrder, Style,
)
from backend.app.services.cost_control import order_control, sheet_view
from backend.app.services.currency import convert_to_base


class CurrencyConversionTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test", currency="EUR")
        self.db.add(self.company)
        self.db.flush()

    def test_same_currency_is_unchanged(self):
        result = convert_to_base(self.db, self.company, 100, "EUR")
        self.assertEqual(result["amount"], 100)
        self.assertEqual(result["rate"], 1.0)
        self.assertFalse(result["fx_missing"])

    def test_no_currency_defaults_to_base(self):
        result = convert_to_base(self.db, self.company, 50, None)
        self.assertEqual(result["amount"], 50)

    def test_missing_rate_is_flagged_not_faked(self):
        result = convert_to_base(self.db, self.company, 100, "USD")
        self.assertIsNone(result["amount"])
        self.assertTrue(result["fx_missing"])

    def test_configured_rate_converts(self):
        self.db.add(ExchangeRate(company_id=self.company.id, currency="USD", rate_to_base=0.9, effective_date=date.today()))
        self.db.commit()
        result = convert_to_base(self.db, self.company, 100, "usd")
        self.assertAlmostEqual(result["amount"], 90, places=4)

    def test_latest_rate_before_date_wins(self):
        self.db.add_all([
            ExchangeRate(company_id=self.company.id, currency="USD", rate_to_base=0.9, effective_date=date.today() - timedelta(days=30)),
            ExchangeRate(company_id=self.company.id, currency="USD", rate_to_base=0.95, effective_date=date.today()),
        ])
        self.db.commit()
        old = convert_to_base(self.db, self.company, 100, "USD", on_date=date.today() - timedelta(days=15))
        self.assertAlmostEqual(old["amount"], 90, places=4)
        new = convert_to_base(self.db, self.company, 100, "USD")
        self.assertAlmostEqual(new["amount"], 95, places=4)


class SheetAndControlCurrencyTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test", currency="EUR")
        self.db.add(self.company)
        self.db.flush()
        self.style = Style(company_id=self.company.id, reference="ST", description="Tee")
        self.db.add(self.style)
        self.db.flush()
        self.db.add(ExchangeRate(company_id=self.company.id, currency="USD", rate_to_base=0.9, effective_date=date.today()))
        self.db.commit()

    def test_sheet_view_exposes_base_currency_totals(self):
        sheet = CostSheet(company_id=self.company.id, style_id=self.style.id, status="draft", quantity_basis=100, selling_price=10, currency="USD")
        self.db.add(sheet)
        self.db.commit()
        view = sheet_view(self.db, sheet)["sheet"]
        self.assertEqual(view["currency"], "USD")
        self.assertEqual(view["base_currency"], "EUR")
        self.assertFalse(view["fx_missing"])
        # 10 USD/peca x 100 pecas = 1000 USD -> 900 EUR a 0.9
        self.assertAlmostEqual(view["sales_total_base"], 900, places=2)

    def test_order_control_converts_foreign_baseline_before_comparing(self):
        sheet = CostSheet(
            company_id=self.company.id, style_id=self.style.id, status="approved",
            quantity_basis=1, selling_price=10, currency="USD",
        )
        self.db.add(sheet)
        self.db.flush()
        self.db.add(CostLine(company_id=self.company.id, cost_sheet_id=sheet.id, category="material", description="Tecido", quantity=1, unit="un", unit_cost=10, amount=10))
        self.db.flush()
        from backend.app.services.costing import recalculate_sheet
        recalculate_sheet(self.db, sheet)
        order = ProductionOrder(
            company_id=self.company.id, style_id=self.style.id, order_no="OF-1", quantity=10, status="in_progress",
            completed_quantity=10, custom_data={"approved_cost_sheet_id": sheet.id},
        )
        self.db.add(order)
        self.db.commit()
        result = order_control(self.db, order)
        # Orcamento nativo: 10 USD/peca x 10 pecas = 100 USD -> convertido a
        # 0.9 = 90 EUR. Sem a conversao, o codigo compararia 100 (USD) contra
        # custo real em EUR como se fossem a mesma moeda.
        self.assertAlmostEqual(result["metrics"]["budget_total"], 90, places=2)
        self.assertFalse(result["metrics"]["fx_missing"])
        self.assertEqual(result["metrics"]["baseline_currency"], "USD")


if __name__ == "__main__":
    unittest.main()
