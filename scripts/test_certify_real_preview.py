"""Focused validation tests for the row-free Denmark geocoding handoff."""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("certify_real_preview.py")
SPEC = importlib.util.spec_from_file_location("certify_real_preview", SCRIPT)
certificate = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(certificate)


class DenmarkGeocodingCertificateTests(unittest.TestCase):
    def summary(self):
        return {"geocoding": {
            "records_seen": 3,
            "unresolved_records": 3,
            "source_coordinate_records": 0,
            "eligible_records": 1,
            "queued_records": 1,
            "eligible_without_usable_address": 0,
            "eligibility_state_counts": {"eligible_pending_queue": 1, "held_for_privacy_review": 2},
            "geocoder_called": False,
        }}

    def test_validates_private_queue_and_returns_aggregate_evidence(self):
        result = certificate._denmark_geocoding_evidence(self.summary(), 3)

        self.assertEqual(result["queued_records"], 1)
        self.assertEqual(result["eligibility_state_counts"]["held_for_privacy_review"], 2)
        self.assertFalse(result["geocoder_called"])
        self.assertFalse(result["publication_approval"])

    def test_rejects_queue_count_above_approved_candidates(self):
        value = self.summary()
        value["geocoding"]["queued_records"] = 2

        with self.assertRaisesRegex(certificate.CertificationError, "do not reconcile"):
            certificate._denmark_geocoding_evidence(value, 3)

    def test_rejects_provider_execution_in_the_acquisition_command(self):
        value = self.summary()
        value["geocoding"]["geocoder_called"] = True

        with self.assertRaisesRegex(certificate.CertificationError, "unexpectedly executed"):
            certificate._denmark_geocoding_evidence(value, 3)


if __name__ == "__main__":
    unittest.main()
