import json
import unittest
from pathlib import Path

from pipeline.scripts.diagnostics.data_readiness_report import DataReadinessError, build_report, canonical_bytes
from pipeline.scripts.maintenance.rehearse_candidate_private_frontend import rehearse_candidate


BASE = {
    "fsis": {"candidate_count": 7241, "numeric_coordinate_count": 7241, "city_geocode_count": 0},
    "italy": {"observation_count": 41849, "provisional_identity_count": 25316, "numeric_coordinate_count": 24749, "city_only_count": 567},
    "france": {"section_i_count": 1449, "section_ii_count": 1068, "union_candidate_count": 2283, "numeric_coordinate_count": 0, "city_postal_count": 2283},
    "denmark": {"observation_count": 58766, "validation_finding_count": 57, "legacy_v1_count": 1561},
}


class DataReadinessReportTests(unittest.TestCase):
    def test_checked_in_report_matches_builder(self):
        expected = build_report(**BASE)
        path = Path(__file__).parents[2] / "data" / "manifests" / "d1-data-readiness-report.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), expected)

    def test_checked_in_test_corpus_manifest_is_row_free_and_reconciles(self):
        path = Path(__file__).parents[2] / "data" / "manifests" / "d1-real-data-shaped-test-corpus.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(manifest["private_payloads_included"])
        self.assertTrue(manifest["fixture_contract"]["no_auto_source_selection"])
        self.assertEqual(manifest["candidates"]["total"], 34840)
        self.assertEqual(manifest["coordinate_states"]["numeric_coordinate"]["total"], 31990)
        self.assertEqual(manifest["coordinate_states"]["city_or_postal_geocode"]["total"], 2850)

    def test_private_rehearsal_is_offline_and_fail_closed_when_handoffs_are_unavailable(self):
        path = Path(__file__).parents[2] / "data" / "manifests" / "current-reacquisition-2026-09-16.json"
        rehearsal = rehearse_candidate(path, root=path.parents[2])
        self.assertEqual(rehearsal["status"], "passed")
        self.assertTrue(rehearsal["fail_closed"])
        self.assertFalse(rehearsal["private_payloads_included"])
        self.assertEqual(rehearsal["frontend_preview"]["state"], "not-run")
        self.assertTrue(all(source["handoff_state"] == "unavailable-private-handoff" for source in rehearsal["sources"]))

    def test_requested_counts_reconcile_and_publication_is_blocked(self):
        report = build_report(**BASE)
        self.assertEqual(report["candidates"]["total"], 34840)
        self.assertEqual(report["coordinate_states"]["numeric_coordinate"]["total"], 31990)
        self.assertEqual(report["coordinate_states"]["city_or_postal_geocode"]["total"], 2850)
        self.assertEqual(report["publication"]["public_api_rows"], 0)
        self.assertEqual(report["publication"]["publication_eligibility"], "blocked")

    def test_denmark_observations_are_not_facilities(self):
        report = build_report(**BASE)
        denmark = report["observations"]["denmark"]
        self.assertEqual(denmark["distinct_source_observation_identity_count"], 58766)
        self.assertIsNone(denmark["facility_identity_count"])
        self.assertIn("never labeled as a facility", denmark["observation_unit"])
        self.assertEqual(report["coordinate_states"]["denmark"]["unresolved_observations"], 58766)

    def test_unknown_quarantine_is_not_silently_zero(self):
        report = build_report(**BASE)
        self.assertEqual(report["quarantine"]["record_level_counts"], "not supplied in this row-free report")
        self.assertTrue(report["quarantine"]["unknown_is_not_zero"])

    def test_drift_fails_closed(self):
        changed = {**BASE, "italy": {**BASE["italy"], "city_only_count": 568}}
        with self.assertRaises(DataReadinessError):
            build_report(**changed)

    def test_report_is_deterministic_and_row_free(self):
        first = build_report(**BASE)
        second = build_report(**BASE)
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys(child)
        for forbidden in ("source_values", "raw_fields", "coordinates", "latitude", "longitude", "private_path"):
            self.assertNotIn(forbidden, set(keys(first)))


if __name__ == "__main__":
    unittest.main()
