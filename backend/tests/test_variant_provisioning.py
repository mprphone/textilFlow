import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import Company, Material, Style, StyleVariant
from backend.app.services.inventory import ensure_item_for_variant, ensure_variant


class VariantProvisioningTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.flush()
        self.style = Style(company_id=self.company.id, reference="SWEAT-HOOD", description="Sweat Hoodie")
        self.db.add(self.style)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_ensure_variant_generates_expected_sku(self):
        variant = ensure_variant(self.db, self.style, "Preto", "M")
        self.assertEqual(variant.sku, "SWEAT-HOOD-PRE-M")
        self.assertEqual(variant.color, "Preto")
        self.assertEqual(variant.size, "M")
        self.assertTrue(variant.active)

    def test_ensure_variant_is_idempotent_for_same_cell(self):
        first = ensure_variant(self.db, self.style, "Preto", "M")
        second = ensure_variant(self.db, self.style, "Preto", "M")
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.query(StyleVariant).count(), 1)

    def test_ensure_variant_normalizes_accents_and_case_for_matching(self):
        first = ensure_variant(self.db, self.style, "Azul-marinho", "M")
        second = ensure_variant(self.db, self.style, "AZUL-MARINHO", " m ")
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.query(StyleVariant).count(), 1)

    def test_ensure_variant_dedupes_sku_on_token_collision(self):
        first = ensure_variant(self.db, self.style, "Azul", "M")
        second = ensure_variant(self.db, self.style, "Azul Escuro", "M")
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(first.sku, "SWEAT-HOOD-AZU-M")
        self.assertEqual(second.sku, "SWEAT-HOOD-AZU-M-2")

    def test_ensure_item_for_variant_creates_material_keyed_by_sku(self):
        variant = ensure_variant(self.db, self.style, "Preto", "M")
        material = ensure_item_for_variant(self.db, variant, self.style)
        self.assertEqual(material.code, variant.sku)
        self.assertEqual(material.color, "Preto")
        self.assertEqual(material.custom_data.get("variant_id"), variant.id)
        self.assertEqual(material.sync_status, "local")

    def test_ensure_item_for_variant_reuses_existing_material_by_code(self):
        variant = ensure_variant(self.db, self.style, "Preto", "M")
        pre_existing = Material(
            company_id=self.company.id, code=variant.sku, name="Manual entry",
            category="other", unit="UN",
        )
        self.db.add(pre_existing)
        self.db.commit()

        material = ensure_item_for_variant(self.db, variant, self.style)
        self.assertEqual(material.id, pre_existing.id)
        self.assertEqual(self.db.query(Material).filter_by(code=variant.sku).count(), 1)


if __name__ == "__main__":
    unittest.main()
