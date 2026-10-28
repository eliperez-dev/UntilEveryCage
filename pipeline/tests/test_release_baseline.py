from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "release_baseline.py"
SPEC = importlib.util.spec_from_file_location("release_baseline", SCRIPT)
baseline = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(baseline)


def _contract():
    return {
        "schema_version": "uec-development-baseline-v1", "release_id": "candidate-r3",
        "profile": "official", "manifest_sha256": "0" * 64,
        "dataset_version": "v0", "release_label": "v0 — Early Access", "release_channel": "early-access",
        "expected": {"public_rows": 10, "mapped_rows": 7, "named_rows": 9,
                     "unmapped_rows": 3, "source_count": 2},
    }


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _Connection:
    def __init__(self, manifest, digest, counts, migrations, *, status="promoted",
                 model_digest=None, history=None, live_counts=None,
                 restriction_counts=None, coverage=(0, 0)):
        self.manifest = manifest
        self.digest = digest
        self.model_digest = model_digest if model_digest is not None else digest
        self.counts = counts
        self.migrations = migrations
        self.status = status
        self.history = history if history is not None else [("candidate-r3", "official")]
        self.live_counts = live_counts if live_counts is not None else counts
        self.restriction_counts = restriction_counts if restriction_counts is not None else self.live_counts
        self.coverage = coverage

    def execute(self, query, params=None):
        if "schema_migrations" in query:
            return _Result(list(self.migrations.items()))
        if "public_discovery_read_models" in query:
            return _Result([(self.status, "official", False, self.manifest, self.digest,
                             self.model_digest, self.counts["public_rows"])])
        if "public_release_history" in query:
            return _Result(self.history)
        if "FULL OUTER JOIN actual" in query:
            return _Result([self.coverage])
        if "public_discovery_read_model_rows" in query:
            return _Result([tuple((self.restriction_counts if "public_access_restricted" in query
                                  else self.counts)[key] for key in baseline.COUNT_FIELDS)])
        if "public_discovery_api_read_model" in query:
            return _Result([tuple(self.live_counts[key] for key in baseline.COUNT_FIELDS)])
        if "map_facilities_public_discovery_read_model" in query:
            return _Result([tuple(self.counts[key] for key in baseline.COUNT_FIELDS)])
        raise AssertionError("unexpected query")


class ReleaseBaselineTests(unittest.TestCase):
    def setUp(self):
        self.contract = _contract()
        self.manifest = {
            "release_id": self.contract["release_id"], "profile": "official",
            "release_status": "promoted", "test_only": False,
            "dataset_version": "v0", "release_label": "v0 — Early Access", "release_channel": "early-access",
        }
        self.digest = hashlib.sha256(json.dumps(self.manifest, sort_keys=True, separators=(",", ":"),
                                              ensure_ascii=False).encode("utf-8")).hexdigest()
        self.contract["manifest_sha256"] = self.digest
        self.migrations = baseline._migration_checksums()
        self.counts = dict(self.contract["expected"])

    def test_contract_accepts_aggregate_baseline_shape(self):
        with patch.object(Path, "read_text", return_value=json.dumps(self.contract)):
            self.assertEqual(baseline.load_contract(Path("synthetic-contract.json")), self.contract)

    def test_loopback_guard_rejects_remote_database_urls(self):
        baseline.validate_database_url("postgresql://user:secret@127.0.0.1/uec")
        with self.assertRaisesRegex(baseline.BaselineError, "loopback"):
            baseline.validate_database_url("postgresql://user:secret@example.invalid/uec")
        with self.assertRaisesRegex(baseline.BaselineError, "loopback"):
            baseline.validate_database_url("postgresql://user:secret@localhost/uec?hostaddr=203.0.113.7")

    def test_verifies_promoted_release_manifest_migrations_and_aggregates(self):
        connection = _Connection(self.manifest, self.digest, self.counts, self.migrations)
        report = baseline.verify_connection(connection, self.contract, self.migrations)
        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["counts"], self.counts)

    def test_rejects_manifest_digest_mismatch_without_exposing_values(self):
        connection = _Connection(self.manifest, "f" * 64, self.counts, self.migrations)
        with self.assertRaisesRegex(baseline.BaselineError, "manifest_digest") as error:
            baseline.verify_connection(connection, self.contract, self.migrations)
        self.assertNotIn(self.digest, str(error.exception))

    def test_rejects_projection_count_and_migration_drift(self):
        wrong_counts = {**self.counts, "public_rows": 11}
        with self.assertRaisesRegex(baseline.BaselineError, "projection_counts"):
            baseline.verify_connection(_Connection(self.manifest, self.digest, wrong_counts, self.migrations),
                                       self.contract, self.migrations)
        drifted = dict(self.migrations)
        first = next(iter(drifted))
        drifted[first] = "0" * 64
        with self.assertRaisesRegex(baseline.BaselineError, "migrations"):
            baseline.verify_connection(_Connection(self.manifest, self.digest, self.counts, drifted),
                                       self.contract, drifted)

    def test_public_metadata_mismatch_is_rejected(self):
        wrong = {**self.manifest, "release_channel": "preview"}
        digest = hashlib.sha256(json.dumps(wrong, sort_keys=True, separators=(",", ":"),
                                           ensure_ascii=False).encode("utf-8")).hexdigest()
        contract = {**self.contract, "manifest_sha256": digest}
        with self.assertRaisesRegex(baseline.BaselineError, "identity_mismatch"):
            baseline.verify_connection(_Connection(wrong, digest, self.counts, self.migrations),
                                       contract, self.migrations)

    def test_validated_release_requires_explicit_historical_mode(self):
        connection = _Connection(self.manifest, self.digest, self.counts, self.migrations,
                                 status="validated")
        with self.assertRaisesRegex(baseline.BaselineError, "identity_mismatch"):
            baseline.verify_connection(connection, self.contract, self.migrations)

    def test_historical_mode_matches_frozen_contract_and_exact_live_rows(self):
        live_counts = {**self.counts, "public_rows": 8, "mapped_rows": 6,
                       "named_rows": 7, "unmapped_rows": 2}
        connection = _Connection(self.manifest, self.digest, self.counts, self.migrations,
                                 status="validated", live_counts=live_counts)
        report = baseline.verify_connection(connection, self.contract, self.migrations,
                                            allow_validated_historical=True)
        self.assertTrue(report["historical"])
        self.assertEqual(report["counts"], live_counts)

    def test_historical_mode_rejects_bad_history_cache_or_live_membership(self):
        options = {"status": "validated", "live_counts": {
            **self.counts, "public_rows": 8, "mapped_rows": 6, "named_rows": 7, "unmapped_rows": 2}}
        bad_cases = (
            {**options, "history": []},
            {**options, "history": [("candidate-r3", "community")]},
            {**options, "history": [("candidate-r3", "official"), ("candidate-r3", "official")]},
            {**options, "coverage": (1, 0)},
            {**options, "coverage": (0, 1)},
            {**options, "live_counts": {**self.counts, "public_rows": 9},
             "restriction_counts": {**self.counts, "public_rows": 8,
                                    "mapped_rows": 6, "named_rows": 7, "unmapped_rows": 2}},
        )
        for case in bad_cases:
            with self.subTest(case=case):
                connection = _Connection(self.manifest, self.digest, self.counts,
                                         self.migrations, **case)
                with self.assertRaises(baseline.BaselineError):
                    baseline.verify_connection(connection, self.contract, self.migrations,
                                               allow_validated_historical=True)

    def test_historical_mode_rejects_changed_model_hash_or_frozen_counts(self):
        connection = _Connection(self.manifest, self.digest, self.counts, self.migrations,
                                 status="validated", model_digest="f" * 64)
        with self.assertRaisesRegex(baseline.BaselineError, "manifest_digest"):
            baseline.verify_connection(connection, self.contract, self.migrations,
                                       allow_validated_historical=True)
        changed_cache = {**self.counts, "public_rows": 9}
        connection = _Connection(self.manifest, self.digest, changed_cache, self.migrations,
                                 status="validated")
        with self.assertRaisesRegex(baseline.BaselineError, "cached_contract_counts"):
            baseline.verify_connection(connection, self.contract, self.migrations,
                                       allow_validated_historical=True)


if __name__ == "__main__":
    unittest.main()
