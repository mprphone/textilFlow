import os
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from backend.app.services.company_profile import decrypt_secret, encrypt_secret, nif_is_locked, validate_nif
from backend.app.services.supplier_dossier import COMPLETED_JOB, OPEN_JOB, _job_metrics
from backend.app.models.subcontracting import SubcontractJob


class SecretRoundtripTest(unittest.TestCase):
    def test_encrypt_decrypt_roundtrip(self):
        token = encrypt_secret("senha-secreta")
        self.assertTrue(token.startswith("tf1:") or token.startswith("tf2:"))
        self.assertEqual(decrypt_secret(token), "senha-secreta")
        self.assertIsNone(encrypt_secret("  "))
        self.assertIsNone(decrypt_secret("lixo"))

    def test_legacy_tf1_still_reads(self):
        with patch("backend.app.services.company_profile.Fernet", None):
            token = encrypt_secret("antiga")
        self.assertTrue(token.startswith("tf1:"))
        self.assertEqual(decrypt_secret(token), "antiga")


class NifTest(unittest.TestCase):
    def test_demo_nif_is_valid(self):
        self.assertEqual(validate_nif("500000000"), "500000000")
        self.assertTrue(nif_is_locked("500000000"))

    def test_old_seed_nif_is_invalid(self):
        self.assertFalse(nif_is_locked("PT500000001"))


class PartialJobMetricsTest(unittest.TestCase):
    def test_partial_counts_as_open_not_completed(self):
        self.assertIn("partial", OPEN_JOB)
        self.assertNotIn("partial", COMPLETED_JOB)
        today = date.today()
        job = SubcontractJob(
            company_id=1, supplier_id=1, subcontract_service_id=1, reference="J1",
            status="partial", sent_date=today - timedelta(days=4), expected_date=today - timedelta(days=1),
            received_date=today,
        )
        metrics = _job_metrics([job], today - timedelta(days=30), today)
        self.assertEqual(len(metrics["open_jobs"]), 1)
        self.assertEqual(metrics["completed"], 0)


class WeakSecretPolicyTest(unittest.TestCase):
    def test_require_app_secret_blocks_without_override(self):
        from backend.app.auth import require_app_secret
        env = {"APP_SECRET": "change-me-before-production", "APP_ALLOW_WEAK_SECRET": ""}
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(RuntimeError):
                require_app_secret()

    def test_require_app_secret_allows_dev_override(self):
        from backend.app.auth import require_app_secret
        env = {"APP_SECRET": "change-me-before-production", "APP_ALLOW_WEAK_SECRET": "1"}
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(require_app_secret(), "change-me-before-production")


if __name__ == "__main__":
    unittest.main()
