import json
import tempfile
import unittest
from pathlib import Path

from pipeline.scripts.diagnostics.current_geospatial_readiness import audit_current, classify_record


class CurrentGeospatialReadinessTests(unittest.TestCase):
    def test_classification_preserves_exact_city_unmapped_and_restricted_semantics(self):
        exact = {"normalized": {"coordinates": {"latitude": 55.0, "longitude": 12.0}, "city": "Town"}}
        coarse = {"normalized": {"city": "Town", "coordinate_state": "not-supplied-by-source"}}
        unresolved = {"normalized": {"name": "facility", "coordinate_state": "not-supplied-by-source"}}
        restricted = {"normalized": {"coordinates": {"latitude": 55.0, "longitude": 12.0}, "privacy_status": "suppressed"}}
        self.assertEqual(classify_record(exact)["display_state"], "exact")
        self.assertEqual(classify_record(coarse)["display_state"], "city")
        self.assertEqual(classify_record(unresolved)["display_state"], "unmapped")
        self.assertEqual(classify_record(restricted)["display_state"], "restricted")

    def test_invalid_and_geocode_evidence_are_counted_separately(self):
        invalid = {"normalized": {"coordinates": {"latitude": 91, "longitude": 12}, "city": "Town"}}
        geocoded = {"normalized": {"city": "Town", "geocode": {"status": "accepted", "precision": "address_point", "result": {"latitude": 55, "longitude": 12}}}}
        pending = {"source_values": {"latitudine": "45.0", "longitudine": "9.0"}, "normalized": {"coordinate_state": "source-value-present-pending-review"}}
        result = classify_record(invalid)
        self.assertEqual(result["evidence"]["source_coordinate_invalid"], 1)
        self.assertEqual(classify_record(geocoded)["evidence"]["accepted_geocode_exact"], 1)
        self.assertEqual(classify_record(pending)["evidence"]["source_coordinate_valid"], 1)

    def test_manifest_audit_is_deterministic_row_free_and_explicit_about_missing_handoffs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staging = root / "staging" / "source-a"
            (staging / "normalized").mkdir(parents=True)
            records = [
                {"source_id": "source-a", "source_row": 1, "normalized": {"establishment_id": "private-id", "coordinates": {"latitude": 55, "longitude": 12}, "city": "Town"}},
                {"source_id": "source-a", "source_row": 2, "normalized": {"establishment_id": "private-id-2", "city": "Town", "privacy_gate": "pending-review"}},
                {"source_id": "source-a", "source_row": 3, "normalized": {"establishment_id": "private-id-3", "privacy_status": "suppressed"}},
            ]
            records_path = staging / "normalized" / "records.jsonl"
            records_path.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
            handoff = staging / "manifest.json"
            handoff.write_text(json.dumps({"source_id": "source-a", "normalized_rows": 3}), encoding="utf-8")
            manifest = root / "sources.json"
            manifest.write_text(json.dumps({"sources": [
                {"source_id": "source-a", "country_code": "DK", "candidate_handoff_manifest": "staging/source-a/manifest.json", "normalized_rows": 3},
                {"source_id": "source-b", "country_code": "IT", "candidate_handoff_manifest": "staging/source-b/manifest.json", "normalized_rows": 10},
            ]}), encoding="utf-8")
            first = audit_current(manifest, root, "2026-09-16T00:00:00Z")
            second = audit_current(manifest, root, "2026-09-16T00:00:00Z")
            self.assertEqual(first, second)
            self.assertEqual(first["sources_listed"], 2)
            self.assertEqual(first["sources_available"], 1)
            self.assertEqual(first["totals_available_rows_only"]["records"], 3)
            self.assertEqual(first["totals_available_rows_only"]["display_exact"], 1)
            self.assertEqual(first["totals_available_rows_only"]["display_city"], 1)
            self.assertEqual(first["totals_available_rows_only"]["display_restricted"], 1)
            self.assertEqual(first["totals_available_rows_only"]["suppressed_rows"], 1)
            encoded = json.dumps(first)
            self.assertNotIn("private-id", encoded)
            self.assertNotIn("Town", encoded)
            self.assertIn("unavailable_private_handoff", encoded)


if __name__ == "__main__":
    unittest.main()
