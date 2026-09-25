"""Sanitized contracts for the strict private-preview certification command."""
import importlib.util
import sys
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "certify_real_preview.py"
SPEC = importlib.util.spec_from_file_location("certify_real_preview", SCRIPT)
CERT = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(CERT)


def ledger():
    return {
        "status": "imported", "source_id": "it.853-2004", "run_id": "acquisition-run-1",
        "runner_run_id": "runner-run-1", "public_rows": 0, "map_visible_count": 1,
        "source_run": {"run_id": "runner-run-1", "results": [{"source_id": "it.853-2004",
            "summary": {"candidate_handoff_sha256": "d" * 64, "schema_fingerprint": "e" * 64}}]},
        "acquisition": {"run_id": "acquisition-run-1", "sha256": "a" * 64, "catalog_sha256": "b" * 64},
        "normalized_sha256": "c" * 64, "candidate_handoff_sha256": "d" * 64,
        "schema_fingerprint": "e" * 64,
        "quarantine": {"input_rows": 3, "accepted_rows": 2, "quarantined_rows": 1},
        "coordinate_precision_breakdown": {"exact": 0, "source_precision_unknown": 1},
        "preview_import": {
            "status": "imported", "idempotent": True, "normalized_sha256": "c" * 64,
            "observation_count": 2, "facility_candidate_count": 2,
            "numeric_coordinate_count": 1, "city_postal_count": 1,
            "unmapped_map_candidate_count": 0, "coarse_placeable_facility_count": 0,
            "public_release_count": 0, "public_projection_count": 0,
        },
    }


class CertificationLedgerTests(unittest.TestCase):
    def test_exact_source_run_reconciles_and_returns_aggregate_evidence(self):
        result = CERT.validate_ledger(ledger(), "it.853-2004")
        self.assertEqual(result["run_id"], "acquisition-run-1")
        self.assertEqual(result["runner_run_id"], "runner-run-1")
        self.assertEqual(result["counts"]["map_visible"], 1)
        self.assertEqual(result["quarantined_rows"], 1)
        self.assertEqual(result["acquisition_hashes"], ["a" * 64, "b" * 64])

    def test_denmark_uses_out_of_scope_unmapped_semantics_without_double_counting(self):
        value = ledger()
        value["source_id"] = "dk.smiley"
        value["source_run"]["results"][0]["source_id"] = "dk.smiley"
        value["preview_import"].update({
            "observation_count": 1, "facility_candidate_count": 1,
            "numeric_coordinate_count": 0, "city_postal_count": 1,
            "unmapped_map_candidate_count": 0, "unmapped_facility_count": 1,
        })
        value["quarantine"].update({"input_rows": 1, "accepted_rows": 1, "quarantined_rows": 0})
        value["map_visible_count"] = 0
        value["coordinate_precision_breakdown"] = {"exact": 0, "unmapped": 1}
        result = CERT.validate_ledger(value, "dk.smiley")
        self.assertEqual(result["counts"]["unmapped"], 1)
        self.assertEqual(result["counts"]["unmapped_map_candidates"], 0)

    def test_wrong_source_fails_closed(self):
        with self.assertRaises(CERT.CertificationError):
            CERT.validate_ledger(ledger(), "us.fsis")

    def test_unreconciled_quarantine_fails_closed(self):
        broken = ledger()
        broken["quarantine"]["input_rows"] = 4
        with self.assertRaisesRegex(CERT.CertificationError, "do not reconcile"):
            CERT.validate_ledger(broken, "it.853-2004")

    def test_paired_source_evidence_reconciles_out_of_scope_rows(self):
        evidence = ledger()
        evidence.update({"source_id": "be.locations", "run_id": "be-run-1", "map_visible_count": 1,
            "source_run": {"run_id": "runner-be-1", "results": [{"source_id": "be.locations",
                "summary": {"candidate_handoff_sha256": "d" * 64, "schema_fingerprint": "e" * 64}}]},
            "acquisition": {"operator": {"run_id": "be-run-1", "sha256": "a" * 64},
                            "activity_codes": {"run_id": "be-run-1", "sha256": "b" * 64}},
            "quarantine": {"input_rows": 3, "accepted_rows": 3, "quarantined_rows": 0, "out_of_scope_rows": 1}})
        evidence["preview_import"].update({"observation_count": 1, "facility_candidate_count": 1,
            "numeric_coordinate_count": 0, "city_postal_count": 1, "unmapped_map_candidate_count": 0,
            "coarse_placeable_facility_count": 1})
        result = CERT.validate_ledger(evidence, "be.locations")
        self.assertEqual(result["out_of_scope_rows"], 1)
        self.assertEqual(result["counts"]["coarse_placeable"], 1)

    def test_public_rows_or_exact_precision_fail_closed(self):
        broken = ledger()
        broken["preview_import"]["public_projection_count"] = 1
        with self.assertRaisesRegex(CERT.CertificationError, "public projection"):
            CERT.validate_ledger(broken, "it.853-2004")
        broken = ledger()
        broken["coordinate_precision_breakdown"]["exact"] = 1
        with self.assertRaisesRegex(CERT.CertificationError, "exact points"):
            CERT.validate_ledger(broken, "it.853-2004")

    def test_api_evidence_must_serve_same_run_and_disclaimer(self):
        evidence = CERT.validate_ledger(ledger(), "it.853-2004")
        candidate = {"candidate_id": "opaque-id", "source_id": "it.853-2004",
                     "project_approval": False, "publication_status": "not_published"}
        def response(url, token, timeout=10.0):
            if url.endswith("/counts"):
                return {"data": {"map_visible_count": 1}, "meta": {"private_preview": True,
                    "runtime_ledger": [{"source_id": "it.853-2004", "run_id": "acquisition-run-1"}]}}
            if "/locations?" in url:
                return {"data": [candidate], "meta": {"private_preview": True}}
            if "/viewport?" in url:
                return {"data": [candidate], "meta": {"private_preview": True}}
            return {"data": candidate}
        with patch.object(CERT, "_api_json", side_effect=response):
            result = CERT._check_api("http://127.0.0.1:38001", "x" * 32, "it.853-2004", evidence)
        self.assertTrue(result["candidate_detail"])

    def test_database_evidence_binds_counts_hashes_and_empty_public_relations(self):
        evidence = CERT.validate_ledger(ledger(), "it.853-2004")
        class Result:
            def __init__(self, value): self.value = value
            def fetchone(self): return self.value
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params=()):
                if "FROM real_preview.source_preview_runs" in sql:
                    return Result(("it.853-2004", "f" * 64, "a" * 64, "c" * 64,
                        3, 2, 1, 0, 2, 2, 1, 0, 0, 2, 1, 0))
                if "FROM real_preview.candidates" in sql:
                    return Result((0,))
                if "to_regclass" in sql:
                    return Result((None,))
                raise AssertionError("unexpected database query")
        driver = SimpleNamespace(connect=lambda _: Connection())
        with patch.dict(sys.modules, {"psycopg": driver}):
            result = CERT._db_check("postgresql://user:secret@127.0.0.1:55433/uec", "it.853-2004", evidence)
        self.assertTrue(result["exact_run"])
        self.assertEqual(result["public_rows"], 0)

    def test_remote_api_endpoint_is_rejected(self):
        with self.assertRaisesRegex(CERT.CertificationError, "loopback"):
            CERT._loopback_url("http://example.invalid")


if __name__ == "__main__":
    unittest.main()
