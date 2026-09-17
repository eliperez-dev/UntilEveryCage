import json
import tempfile
import unittest
from pathlib import Path

from pipeline.common.demonstration_release import DemonstrationReleaseError, load_review, load_selection


class DemonstrationReleaseDocumentTests(unittest.TestCase):
    def write(self, value):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "document.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        self.addCleanup(directory.cleanup)
        return path

    def selection(self, **overrides):
        value = {
            "selection_version": "uec-demo-selection-v1",
            "candidate_release_id": "candidate-dk",
            "source_id": "dk.smiley",
            "source_artifact_sha256": "a" * 64,
            "record_ids": ["11111111-1111-4111-8111-111111111111"],
            "selection_reason": "bounded reviewed facility sample",
        }
        value.update(overrides)
        return value

    def review(self, **overrides):
        value = {
            "review_version": "uec-demo-review-v1",
            "release_id": "demo-dk",
            "source_id": "dk.smiley",
            "source_artifact_sha256": "a" * 64,
            "rights_status": "cleared",
            "rights_reference": "operator terms review R-1",
            "reviewer_role": "authorized project maintainer",
            "reviewed_at": "2026-09-17T12:00:00Z",
            "decisions": [{
                "source_record_id": "11111111-1111-4111-8111-111111111111",
                "factual_review_status": "reviewed",
                "privacy_screening_status": "passed",
                "maintainer_approval": "approved",
                "publication_eligible": True,
                "note": "bounded demonstration decision",
            }],
        }
        value.update(overrides)
        return value

    def test_selection_is_row_free_and_normalized(self):
        value = load_selection(self.write(self.selection()))
        self.assertEqual(value["record_ids"], ["11111111-1111-4111-8111-111111111111"])
        self.assertNotIn("address", value)
        self.assertNotIn("coordinates", value)

    def test_selection_rejects_duplicate_or_oversized_ids(self):
        with self.assertRaises(DemonstrationReleaseError):
            load_selection(self.write(self.selection(record_ids=["11111111-1111-4111-8111-111111111111"] * 2)))
        oversized = [f"11111111-1111-4111-8111-{index:012d}" for index in range(26)]
        with self.assertRaises(DemonstrationReleaseError):
            load_selection(self.write(self.selection(record_ids=oversized)))

    def test_review_requires_explicit_rights_and_all_approval_fields(self):
        value = load_review(self.write(self.review()))
        self.assertEqual(value["rights_status"], "cleared")
        self.assertEqual(value["decisions"][0]["maintainer_approval"], "approved")
        with self.assertRaises(DemonstrationReleaseError):
            load_review(self.write(self.review(rights_status="pending")))
        blocked = self.review(decisions=[{**self.review()["decisions"][0], "privacy_screening_status": "failed"}])
        with self.assertRaises(DemonstrationReleaseError):
            load_review(self.write(blocked))


if __name__ == "__main__":
    unittest.main()
