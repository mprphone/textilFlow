import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models import Company
from backend.app.services.sequences import formatted, next_value


class SequencesTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        self.company = Company(code="T", name="Test")
        self.db.add(self.company)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_next_value_increments_per_company_and_key(self):
        self.assertEqual(next_value(self.db, self.company.id, "sewing_plan"), 1)
        self.assertEqual(next_value(self.db, self.company.id, "sewing_plan"), 2)
        self.assertEqual(next_value(self.db, self.company.id, "other"), 1)

    def test_formatted_pads_with_zeros_and_applies_prefix(self):
        self.assertEqual(formatted(self.db, self.company.id, "subcontract", prefix="EXT-", width=3), "EXT-001")
        self.assertEqual(formatted(self.db, self.company.id, "subcontract", prefix="EXT-", width=3), "EXT-002")

    def test_formatted_period_scopes_the_sequence_independently(self):
        self.assertEqual(formatted(self.db, self.company.id, "subcontract", prefix="EXT-", width=3, period="20260101"), "EXT-001")
        self.assertEqual(formatted(self.db, self.company.id, "subcontract", prefix="EXT-", width=3, period="20260102"), "EXT-001")
        self.assertEqual(formatted(self.db, self.company.id, "subcontract", prefix="EXT-", width=3, period="20260101"), "EXT-002")


if __name__ == "__main__":
    unittest.main()
