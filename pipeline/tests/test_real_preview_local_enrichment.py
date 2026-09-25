import importlib.util
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPT = Path(__file__).parents[2] / "scripts" / "real_preview.py"
SPEC = importlib.util.spec_from_file_location("real_preview_cli", SCRIPT)
PREVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREVIEW)


class LocalEnrichmentTests(unittest.TestCase):
    def test_canada_without_local_reference_is_provider_blocked(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchall.return_value = [
            ("candidate", "a" * 64, "ca.cfia.federal-meat", "opaque-key", "city_postal", "CA", "Town", "A1A", None, None, None)
        ]
        with patch.object(PREVIEW.psycopg if hasattr(PREVIEW, "psycopg") else __import__("psycopg"), "connect", return_value=connection):
            result = PREVIEW.enrich_locations("ca.cfia.federal-meat", 10, "postgresql://localhost/test")
        self.assertEqual(result["provider_blocked"], 1)
        self.assertEqual(result["external_provider_calls"], 0)
        sql = " ".join(str(call.args[0]) for call in connection.execute.call_args_list)
        self.assertNotIn("UPDATE real_preview.candidates", sql)
        self.assertNotIn("geocode_jobs", sql)

    def test_refresh_path_remains_separate_from_enrichment(self):
        source = SCRIPT.read_text(encoding="utf-8")
        refresh = source[source.index("def _refresh_source_locked"):source.index("def refresh_source")]
        self.assertNotIn("enrich_locations(", refresh)
        self.assertNotIn("geocode-worker", refresh)
        self.assertNotIn("geocoder.geocode", refresh)

    def test_enrichment_cli_requires_one_scope(self):
        with patch.object(PREVIEW, "enrich_locations") as enrich:
            enrich.return_value = {"status": "ok"}
            self.assertEqual(PREVIEW.main(["enrich-locations", "--source", "dk.smiley", "--limit", "1"]), 0)
            enrich.assert_called_once_with("dk.smiley", 1, None)


if __name__ == "__main__":
    unittest.main()
