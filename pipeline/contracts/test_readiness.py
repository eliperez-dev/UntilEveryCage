import unittest

from pipeline.contracts.readiness import (
    ReadinessError,
    can_transition,
    readiness_from_status,
    require_private_boundary,
    require_transition,
)


class ReadinessTests(unittest.TestCase):
    def test_private_acquisition_stops_at_owner_review(self):
        readiness = readiness_from_status({
            "metadata": "verified",
            "acquisition": "artifact_private_only",
            "publication_eligibility": "blocked",
        })
        self.assertEqual(readiness.state, "awaiting-owner-review")
        self.assertEqual(readiness.owner_review, "awaiting-owner-review")
        self.assertTrue(readiness.private_candidate)
        self.assertFalse(readiness.public_release_allowed)

    def test_not_run_source_is_reconnaissance_not_ready(self):
        readiness = readiness_from_status({"metadata": "verified", "acquisition": "not_run"})
        self.assertEqual(readiness.state, "reconnaissance")
        self.assertFalse(readiness.private_candidate)

    def test_approval_requires_explicit_owner_review(self):
        self.assertTrue(can_transition("awaiting-owner-review", "approved-for-release"))
        with self.assertRaises(ReadinessError):
            require_transition("private-candidate", "approved-for-release")
        with self.assertRaises(ReadinessError):
            require_private_boundary({
                "schema_version": "country-source-readiness-v1",
                "state": "approved-for-release",
                "owner_review": "approved",
                "private_candidate": True,
                "public_release_allowed": True,
                "reasons": [],
            })


if __name__ == "__main__":
    unittest.main()
