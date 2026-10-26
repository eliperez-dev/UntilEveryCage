import json
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.sources.spain_rgseaa import cohort_acquisition as acquisition
from pipeline.sources.spain_rgseaa.location_enrichment import UnsupportedAesanProvinceError


class SpainBulkCohortAcquisitionTests(unittest.TestCase):
    def test_unsupported_province_stays_pending_and_does_not_block_valid_groups(self):
        keys = ["1" * 64, "2" * 64]
        registrations = ["10.000007/B", "10.000008/M"]
        provinces = ["Bilbao", "Madrid"]
        records = {
            key: {"source_id": "es.locations", "source_record_key": key,
                  "source_values": {},
                  "normalized": {"establishment_id": registration, "province": province}}
            for key, registration, province in zip(keys, registrations, provinces)
        }
        calls = []

        def lookup(province, sector, *, request_interval_seconds):
            calls.append((province, sector))
            if province == "Bilbao":
                raise UnsupportedAesanProvinceError(
                    "AESAN province has no unique supported official option", response_bytes=100)
            return {"results": [{"registration": registrations[1], "municipality": "Town M",
                                  "province": "Madrid"}],
                    "retrieved_at": "2026-10-25T00:00:00Z",
                    "result_url": "https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal_excel.jsp",
                    "request_url": "https://rgsa-web-aesan.mscbs.es/rgsa/procesaBusquedaServlet",
                    "http_requests": 3, "response_bytes": 128}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {"UEC_REAL_PREVIEW_RUNS_ROOT": str(root)}), \
                 patch.object(acquisition, "_load_records", return_value=(records, "a" * 64)), \
                 patch.object(acquisition, "_eligible_representatives",
                              return_value=list(zip(registrations, keys))):
                result = acquisition.acquire_bulk("unused", root / "records.jsonl", root / "events.jsonl",
                    request_interval_seconds=0, lookup=lookup, connect=object())
            events = [json.loads(line) for line in (root / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(calls, [("Bilbao", "10"), ("Madrid", "10")])
        self.assertEqual(result["filter_groups_completed"], 1)
        self.assertEqual(result["filter_groups_pending"], 1)
        self.assertEqual(result["unsupported_groups_this_run"], 1)
        self.assertEqual(result["unsupported_candidates_this_run"], 1)
        self.assertEqual(result["unsupported_province_labels_this_run"], ["Bilbao"])
        self.assertEqual(result["candidate_events_pending"], 1)
        self.assertEqual(result["candidate_events_written"], 1)
        self.assertEqual(result["http_requests_this_run"], 4)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source_record_key"], keys[1])

    def test_bulk_export_retention_is_private_hash_bound_and_scope_tagged(self):
        raw = b"bounded private workbook fixture"
        response_sha = hashlib.sha256(raw).hexdigest()
        result_page_sha = hashlib.sha256(b"result page").hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "events.jsonl"
            retained, byte_count = acquisition._retain_bulk_export(
                output, root.resolve(), {"province": "Madrid", "sector": "10"},
                {"_raw_export_bytes": raw, "response_sha256": response_sha,
                 "result_page_sha256": result_page_sha,
                 "retrieved_at": "2026-10-25T00:00:00Z",
                 "content_type": "application/vnd.ms-excel"}, "a" * 64)
            artifact_dir = root / "bulk-export-artifacts"
            raw_files = list(artifact_dir.glob("*.xls"))
            metadata_files = list(artifact_dir.glob("*.json"))
            raw_artifact = raw_files[0].read_bytes()
            metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
        self.assertTrue(retained)
        self.assertEqual(byte_count, len(raw))
        self.assertEqual(len(raw_files), 1)
        self.assertEqual(raw_artifact, raw)
        self.assertEqual(metadata["response_sha256"], response_sha)
        self.assertEqual(metadata["result_page_sha256"], result_page_sha)
        self.assertEqual(metadata["query_scope"]["province"], "Madrid")
        self.assertEqual(metadata["query_scope"]["sector"], "10")
        self.assertEqual(metadata["query_scope"]["registration_number"], "blank")
        self.assertEqual(metadata["retrieved_at_utc"], "2026-10-25T00:00:00Z")
        self.assertEqual(metadata["normalized_records_sha256"], "a" * 64)

    def test_explicit_zero_result_group_checkpoints_not_found_with_two_requests(self):
        key, registration = "f" * 64, "12.000009/XX"
        record = {"source_id": "es.locations", "source_record_key": key,
                  "source_values": {"N_RGSEAA": registration},
                  "normalized": {"establishment_id": registration, "province": "Madrid"}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {"UEC_REAL_PREVIEW_RUNS_ROOT": str(root)}), \
                 patch.object(acquisition, "_load_records", return_value=({key: record}, "a" * 64)), \
                 patch.object(acquisition, "_eligible_representatives", return_value=[(registration, key)]):
                result = acquisition.acquire_bulk("unused", root / "records.jsonl", root / "events.jsonl",
                    request_interval_seconds=0,
                    lookup=lambda province, sector, **kwargs: {
                        "results": [], "retrieved_at": "2026-10-25T00:00:00Z",
                        "result_url": "https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal.jsp",
                        "request_url": "https://rgsa-web-aesan.mscbs.es/rgsa/procesaBusquedaServlet",
                        "response_bytes": 128, "http_requests": 2, "explicit_zero_results": True})
            event = json.loads((root / "events.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(result["http_requests_this_run"], 2)
        self.assertEqual(result["outcomes_this_run"], {"not_found": 1})
        self.assertEqual(event["outcome"], "not_found")

    def test_exact_joins_preserve_province_conflicts_and_resume_from_event_cache(self):
        keys = ["a" * 64, "b" * 64, "c" * 64]
        registrations = ["10.000001/CO", "10.000002/CO", "12.000003/M"]
        records = {}
        for key, registration, province in zip(keys, registrations, ["Córdoba", "Córdoba", "Madrid"]):
            records[key] = {
                "source_id": "es.locations", "source_record_key": key, "source_values": {},
                "normalized": {"establishment_id": registration, "province": province,
                               "address": "PRIVATE ADDRESS", "name": "PRIVATE BUSINESS"},
            }
        candidates = [(registration, key) for registration, key in zip(registrations, keys)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event_path = root / "events.jsonl"
            calls = []

            def lookup(province, sector, *, request_interval_seconds):
                calls.append((province, sector, request_interval_seconds))
                result_rows = ([
                    {"registration": registrations[0], "municipality": "Town A", "province": "Córdoba"},
                    {"registration": registrations[1], "municipality": "Town B", "province": "Sevilla"},
                ] if province == "Córdoba" else [
                    {"registration": registrations[2], "municipality": "Town C", "province": "Madrid"},
                ])
                return {"results": result_rows, "retrieved_at": "2026-10-25T00:00:00Z",
                        "result_url": "https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal_excel.jsp",
                        "request_url": "https://rgsa-web-aesan.mscbs.es/rgsa/procesaBusquedaServlet",
                        "response_bytes": 128}

            with patch.dict(os.environ, {"UEC_REAL_PREVIEW_RUNS_ROOT": str(root)}), \
                 patch.object(acquisition, "_load_records", return_value=(records, "d" * 64)), \
                 patch.object(acquisition, "_eligible_representatives", return_value=candidates):
                first = acquisition.acquire_bulk("unused", root / "records.jsonl", event_path,
                    request_interval_seconds=0, lookup=lookup, connect=object())
                self.assertEqual(first["filter_queries_this_run"], 2)
                self.assertEqual(first["http_requests_this_run"], 6)
                self.assertEqual(first["outcomes_this_run"], {"matched": 2, "province_conflict": 1})
                self.assertEqual([len(call) for call in calls], [3, 3])
                lines = event_path.read_text(encoding="utf-8").splitlines()
                events = [json.loads(line) for line in lines]
                self.assertEqual(len(events), 3)
                self.assertNotIn("PRIVATE BUSINESS", "\n".join(lines))
                self.assertNotIn("PRIVATE ADDRESS", "\n".join(lines))

                resumed = acquisition.acquire_bulk("unused", root / "records.jsonl", event_path,
                    request_interval_seconds=0, lookup=lookup, connect=object())
                self.assertEqual(resumed["previously_checkpointed"], 3)
                self.assertEqual(resumed["filter_queries_this_run"], 0)
                self.assertEqual(len(calls), 2)

    def test_province_aliases_share_one_filter_group(self):
        keys = ["d" * 64, "e" * 64]
        registrations = ["10.000004/A", "10.000005/A"]
        records = {
            keys[0]: {"source_id": "es.locations", "source_record_key": keys[0], "source_values": {},
                      "normalized": {"establishment_id": registrations[0], "province": "A Coruña"}},
            keys[1]: {"source_id": "es.locations", "source_record_key": keys[1], "source_values": {},
                      "normalized": {"establishment_id": registrations[1], "province": "La Coruña"}},
        }
        calls = []
        def lookup(province, sector, *, request_interval_seconds):
            calls.append((province, sector))
            return {"results": [
                {"registration": registrations[0], "municipality": "Town A", "province": "La Coruña"},
                {"registration": registrations[1], "municipality": "Town B", "province": "A Coruña"}],
                "retrieved_at": "2026-10-25T00:00:00Z",
                "result_url": "https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal_excel.jsp",
                "request_url": "https://rgsa-web-aesan.mscbs.es/rgsa/procesaBusquedaServlet",
                "response_bytes": 64}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {"UEC_REAL_PREVIEW_RUNS_ROOT": str(root)}), \
                 patch.object(acquisition, "_load_records", return_value=(records, "f" * 64)), \
                 patch.object(acquisition, "_eligible_representatives",
                              return_value=list(zip(registrations, keys))):
                result = acquisition.acquire_bulk("unused", root / "records.jsonl", root / "events.jsonl",
                    request_interval_seconds=0, lookup=lookup, connect=object())
        self.assertEqual(calls, [("A Coruña", "10")])
        self.assertEqual(result["filter_queries_this_run"], 1)
        self.assertEqual(result["outcomes_this_run"], {"matched": 2})

    def test_normalized_record_sha_must_match_latest_private_snapshot(self):
        class Result:
            def __init__(self, row): self.row = row
            def fetchone(self): return self.row
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def transaction(self): return self
            def execute(self, sql, params=None):
                if sql.startswith("SET TRANSACTION READ ONLY"):
                    return Result(None)
                if "SELECT current_database()" in sql:
                    return Result(("uec_launch_sources_test_20261025",))
                if "FROM real_preview.source_manifests manifest" in sql:
                    return Result(("different-snapshot-sha",))
                raise AssertionError("representatives must not be queried after snapshot mismatch")
        with self.assertRaisesRegex(RuntimeError, "normalized_records_not_latest_snapshot"):
            acquisition._eligible_representatives("unused", "expected-snapshot-sha",
                                                  lambda *args, **kwargs: Connection())


if __name__ == "__main__":
    unittest.main()
