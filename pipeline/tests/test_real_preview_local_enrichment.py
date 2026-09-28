import importlib.util
import datetime
import tempfile
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

    def test_catalonia_resolution_uses_only_stable_admin_code(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchall.return_value = [
            ("candidate", "a" * 64, "es.cat.feed-sandach", "opaque-key", "city_postal", "ES", "Town", "08000", None, None, "coarse_eligible")
        ]
        connection.execute.return_value.fetchone.return_value = ("080193",)
        refs = [("Town", "080193", 41.2, 1.8, "icgc-ref", "https://example.test/ref",
                 datetime.date(2024, 11, 27), "a" * 64)]
        # The initial candidate batch query and the municipality-code lookup
        # are distinguished by their SQL; neither uses city/postal matching.
        def execute(sql, params=()):
            result = MagicMock()
            if "SELECT admin_name,admin_code" in sql:
                result.fetchall.return_value = refs
            elif "SELECT municipality_code" in sql:
                result.fetchone.return_value = ("080193",)
            elif "SELECT candidate.candidate_id" in sql:
                result.fetchall.return_value = connection.execute.return_value.fetchall.return_value
            else:
                result.fetchall.return_value = []
            return result
        connection.execute.side_effect = execute
        with patch.object(__import__("psycopg"), "connect", return_value=connection):
            result = PREVIEW.enrich_locations("es.cat.feed-sandach", 10, "postgresql://localhost/test")
        self.assertEqual(result["resolved"], 1)
        sql = " ".join(str(call.args[0]) for call in connection.execute.call_args_list)
        self.assertIn("admin_code=%s", sql)
        self.assertNotIn("lower(city_name)", sql)
        self.assertNotIn("geocode_jobs", sql)
        self.assertEqual(result["external_provider_calls"], 0)

    def test_enrichment_cli_requires_one_scope(self):
        with patch.object(PREVIEW, "enrich_locations") as enrich:
            enrich.return_value = {"status": "ok"}
            self.assertEqual(PREVIEW.main(["enrich-locations", "--source", "dk.smiley", "--limit", "1"]), 0)
            enrich.assert_called_once_with("dk.smiley", 1, None)

    def test_reviewed_icgc_reference_accepts_exact_ine_and_idescat_codes(self):
        reference_url = "https://analisi.transparenciacatalunya.cat/api/v3/views/wpyq-we8x/export.csv?accessType=DOWNLOAD"
        icgc_csv = (
            "Municipi,Municipi forma indexada,Cap de municipi,Cap de municipi indexada,"
            "Codi municipi,Codi municipi INE,Comarca,Codi comarca,Abreviatura comarca,"
            "Província,Codi província,UTM X,UTM Y,Longitud,Latitud,Georeferència\n"
            "Municipality,Municipality,Capital,Capital,080193,08019,County,01,C,"
            "Barcelona,08,430000,4580000,2.0,41.0,\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "references.csv"
            path.write_text(icgc_csv, encoding="utf-8")
            connection = MagicMock()
            connection.__enter__.return_value = connection
            cursor = MagicMock()
            connection.cursor.return_value.__enter__.return_value = cursor
            with patch.object(__import__("psycopg"), "connect", return_value=connection):
                result = PREVIEW.import_location_references(
                    str(path), "es.cat.icgc.municipality-capital-localities",
                    reference_url, "2024-11-27", "postgresql://localhost/test",
                )
        self.assertEqual(result["imported_or_existing"], 2)
        sql = str(cursor.executemany.call_args.args[0])
        params = cursor.executemany.call_args.args[1]
        self.assertIn("ON CONFLICT (country_code,admin_code,reference_source_id) DO NOTHING", sql)
        self.assertIn("source_artifact_sha256", sql)
        self.assertEqual([row[0] for row in params], ["080193", "08019"])
        self.assertEqual(result["external_provider_calls"], 0)

    def test_icgc_reference_url_is_bound_to_reviewed_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "references.csv"
            path.write_text(
                "Municipi,Municipi forma indexada,Cap de municipi,Cap de municipi indexada,"
                "Codi municipi,Codi municipi INE,Comarca,Codi comarca,Abreviatura comarca,"
                "Província,Codi província,UTM X,UTM Y,Longitud,Latitud,Georeferència\n",
                encoding="utf-8",
            )
            with self.assertRaises(PREVIEW.PreviewError):
                PREVIEW.import_location_references(
                    str(path), "es.cat.icgc.municipality-capital-localities",
                    "https://analisi.transparenciacatalunya.cat/api/v3/views/other/export.csv?accessType=DOWNLOAD",
                    "2024-11-27", "postgresql://localhost/test",
                )


if __name__ == "__main__":
    unittest.main()
