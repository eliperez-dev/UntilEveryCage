import importlib.util
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/diagnostics/real-preview-enrichment-status.py"
SPEC = importlib.util.spec_from_file_location("preview_enrichment_status", SCRIPT)
STATUS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STATUS)


class PreviewEnrichmentContractTests(unittest.TestCase):
    def test_migration_has_append_only_candidate_target_and_exclusive_latest_state(self):
        migration = (ROOT / "migrations/049_preview_geocode_targets.sql").read_text()
        for state in (
            "source_coordinate", "coarse_eligible", "exact_eligible", "queued",
            "resolved", "insufficient", "restricted", "provider_blocked",
            "retryable", "unresolved", "conflict",
        ):
            self.assertIn(f"'{state}'", migration)
        self.assertIn("UNIQUE REFERENCES real_preview.candidates(candidate_id)", migration)
        self.assertIn("real_preview.candidate_enrichment_reconciliation", migration)
        self.assertIn("real_preview.reject_mutation()", migration)

    def test_status_is_aggregate_only(self):
        rows = [("resolved", "local_coarse_reference_available", 3)]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchall.return_value = rows
        with patch.object(STATUS.psycopg, "connect", return_value=connection):
            result = STATUS.report("postgresql://synthetic")
        self.assertEqual(result["candidate_count"], 3)
        self.assertEqual(result["privacy"], "aggregate_only")
        self.assertNotIn("candidate_id", str(result))
        self.assertNotIn("query", str(result))

    def test_importer_seeds_safe_local_and_source_location_states(self):
        source = (ROOT / "scripts/maintenance/import-real-preview.py").read_text()
        self.assertIn("source_coordinate_present", source)
        self.assertIn("local_coarse_reference_available", source)
        self.assertIn("city_or_postal_reference_input", source)
        self.assertIn("no_usable_location_input", source)
        self.assertIn("NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events", source)

    def test_refresh_path_has_no_geocoder_or_worker_invocation(self):
        source = (ROOT.parent / "scripts/real_preview.py").read_text()
        refresh = source[source.index("def _refresh_source_locked"):source.index("def refresh_source")]
        self.assertNotIn("geocode-worker", refresh)
        self.assertNotIn("geocoder.geocode", refresh)
        self.assertNotIn("enrich-locations", refresh)


if __name__ == "__main__":
    unittest.main()
