import importlib.util
import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPT = Path(__file__).parents[2] / "scripts" / "real_preview.py"
SPEC = importlib.util.spec_from_file_location("real_preview_cli", SCRIPT)
PREVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREVIEW)


class LocalEnrichmentTests(unittest.TestCase):
    def test_npi_source_coordinates_are_recorded_by_shared_enrichment(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchall.return_value = [
            ("candidate", "a" * 64, "au.npi.facilities", "NPI-1", "numeric_source_coordinate", "AU", None, None, -33.1, 151.2, None)
        ]
        with patch.object(__import__("psycopg"), "connect", return_value=connection):
            result = PREVIEW.enrich_locations("au.npi.facilities", 10, "postgresql://localhost/test")
        self.assertEqual(result["resolved"], 0)
        self.assertEqual(result["provider_blocked"], 0)
        self.assertEqual(result["unresolved"], 0)
        sql = " ".join(str(call.args[0]) for call in connection.execute.call_args_list)
        self.assertIn("state_code", sql)
        self.assertTrue(any("source_coordinate" in call.args[1] and "source_coordinate_present" in call.args[1]
                            for call in connection.execute.call_args_list if len(call.args) > 1))
        self.assertNotIn("geocode_jobs", sql)

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

    def test_catalonia_reference_conflicts_are_counted_separately(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        candidate = ("candidate", "a" * 64, "es.cat.feed-sandach", "opaque-key", "city_postal", "ES", "Town", "08000", None, None, "coarse_eligible")
        references = [
            ("Town", "080193", 41.2, 1.8, "icgc-ref-a", "https://example.test/a", datetime.date(2024, 11, 27), "a" * 64),
            ("Town", "080193", 41.3, 1.9, "icgc-ref-b", "https://example.test/b", datetime.date(2024, 11, 27), "b" * 64),
        ]

        def execute(sql, params=()):
            result = MagicMock()
            if "SELECT admin_name,admin_code" in sql:
                result.fetchall.return_value = references
            elif "SELECT municipality_code" in sql:
                result.fetchone.return_value = ("080193",)
            elif "SELECT candidate.candidate_id" in sql:
                result.fetchall.return_value = [candidate]
            else:
                result.fetchall.return_value = []
            return result

        connection.execute.side_effect = execute
        with patch.object(__import__("psycopg"), "connect", return_value=connection):
            result = PREVIEW.enrich_locations("es.cat.feed-sandach", 10, "postgresql://localhost/test")
        self.assertEqual(result["resolved"], 0)
        self.assertEqual(result["conflicts"], 1)
        self.assertEqual(result["examined"], 1)

    def test_catalonia_private_viewport_walks_all_coarse_pages(self):
        pages = [
            (200, {"data": [{"candidate_id": "one", "source_id": "es.cat.feed-sandach",
                             "display_precision": "locality_reference_coarse"}],
                   "meta": {"private_preview": True, "next_cursor": "next"}}),
            (200, {"data": [{"candidate_id": "two", "source_id": "es.cat.feed-sandach",
                             "display_precision": "locality_reference_coarse"}],
                   "meta": {"private_preview": True, "next_cursor": None}}),
        ]
        with patch.object(PREVIEW, "_http", side_effect=pages) as http:
            result = PREVIEW._catalonia_private_viewport_acceptance("secret-token", 2, "http://127.0.0.1:38001")
        self.assertEqual(result["features"], 2)
        self.assertEqual(result["pages"], 2)
        self.assertEqual(result["display_precision"], "locality_reference_coarse")
        self.assertEqual(http.call_count, 2)

    def test_catalonia_private_viewport_rejects_exact_or_unlabeled_points(self):
        page = (200, {"data": [{"candidate_id": "one", "source_id": "es.cat.feed-sandach",
                                "display_precision": "source_provided_exact"}],
                      "meta": {"private_preview": True, "next_cursor": None}})
        with patch.object(PREVIEW, "_http", return_value=page):
            with self.assertRaises(PREVIEW.PreviewError):
                PREVIEW._catalonia_private_viewport_acceptance("secret-token", 1, "http://127.0.0.1:38001")

    def test_catalonia_certificate_is_written_only_after_enrichment_acceptance(self):
        source = SCRIPT.read_text(encoding="utf-8")
        start = source.index("def strict_live_private_e2e")
        end = source.index("def _catalonia_private_viewport_acceptance", start)
        body = source[start:end]
        self.assertLess(body.index("_catalonia_private_viewport_acceptance("),
                        body.index("temporary.replace(certificate_path)"))
        self.assertIn('certificate["location_enrichment"] = catalonia_location_acceptance', body)
        self.assertIn('"counts": certificate["counts"]', body)

    def test_catalonia_reference_capture_is_bounded_and_terms_pinned(self):
        metadata = MagicMock()
        metadata.__enter__.return_value = metadata
        metadata.status = 200
        metadata.geturl.return_value = "https://analisi.transparenciacatalunya.cat/api/views/wpyq-we8x.json"
        metadata.headers = {"Content-Type": "application/json; charset=utf-8"}
        metadata.read.return_value = json.dumps({
            "rowsUpdatedAt": int(datetime.datetime(2024, 11, 27, 11, 22, 54, tzinfo=datetime.timezone.utc).timestamp())
        }).encode()
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.geturl.return_value = "https://analisi.transparenciacatalunya.cat/api/v3/views/wpyq-we8x/export.csv?accessType=DOWNLOAD"
        response.headers = {"Content-Type": "text/csv; charset=utf-8"}
        response.read.return_value = b"reviewed-test-header\n"
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "private" / "reference.csv"
            with patch.object(PREVIEW.urllib.request, "urlopen", side_effect=[metadata, response]):
                result = PREVIEW.acquire_catalonia_locality_reference(
                    artifact, Path(__file__).parents[2] / "data" / "terms-reviews" / "es.cat.icgc.municipality-capital-localities.json")
            self.assertEqual(result["dataset_date"], "2024-11-27")
            self.assertEqual(result["byte_size"], len(b"reviewed-test-header\n"))
            self.assertEqual(len(result["catalog_metadata_sha256"]), 64)
            self.assertEqual(artifact.read_bytes(), b"reviewed-test-header\n")

    def test_enrichment_cli_requires_one_scope(self):
        with patch.object(PREVIEW, "enrich_locations") as enrich:
            enrich.return_value = {"status": "ok"}
            self.assertEqual(PREVIEW.main(["enrich-locations", "--source", "dk.smiley", "--limit", "1"]), 0)
            enrich.assert_called_once_with("dk.smiley", 1, None)

    def test_reference_import_is_available_through_shared_cli(self):
        with patch.object(PREVIEW, "import_location_references") as importer:
            importer.return_value = {"status": "ok", "imported_or_existing": 123}
            self.assertEqual(PREVIEW.main([
                "import-location-references", "--reference-file", "reference.csv",
                "--reference-source-id", "es.cat.icgc.municipality-capital-localities",
                "--reference-url", "https://analisi.transparenciacatalunya.cat/api/v3/views/wpyq-we8x/export.csv?accessType=DOWNLOAD",
                "--reference-date", "2024-11-27", "--database-url", "postgresql://localhost/test",
            ]), 0)
            importer.assert_called_once_with(
                "reference.csv", "es.cat.icgc.municipality-capital-localities",
                "https://analisi.transparenciacatalunya.cat/api/v3/views/wpyq-we8x/export.csv?accessType=DOWNLOAD",
                "2024-11-27", "postgresql://localhost/test",
            )

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
