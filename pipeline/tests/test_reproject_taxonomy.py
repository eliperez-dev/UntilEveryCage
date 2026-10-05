from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stderr
from types import SimpleNamespace
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / "scripts" / "maintenance" / "reproject-taxonomy.py"
SPEC = importlib.util.spec_from_file_location("reproject_taxonomy_test", SCRIPT)
REPROJECT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(REPROJECT)


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _IdentityConnection:
    def __init__(self, *, stale=False, missing=False, bad_provenance=False,
                 wrong_group=False, wrong_representative=False):
        self.stale = stale
        self.missing = missing
        self.bad_provenance = bad_provenance
        self.wrong_group = wrong_group
        self.wrong_representative = wrong_representative

    def execute(self, statement, params=()):
        statement = str(statement)
        if "FROM real_preview.source_preview_runs" in statement and "ORDER BY created_at" in statement:
            return _Result([("b" * 64 if self.stale else "a" * 64,)])
        if "FROM real_preview.source_preview_runs" in statement:
            return _Result([] if self.missing else [("x" * 64 if self.bad_provenance else "c" * 64,
                             "d" * 64, "https://example.test/source", "2026-01-01T00:00:00+00:00",
                             1, 0, 1, 1, 0)])
        if "FROM real_preview.source_manifests" in statement:
            return _Result([("c" * 64, "d" * 64, 1, "https://example.test/source",
                             "2026-01-01T00:00:00+00:00", "code-v1", "config-v1")])
        if "FROM real_preview.observations" in statement:
            return _Result([("preview-uuid", "record-1", "numeric_source_coordinate", "GB", "Town", None,
                              51.5, -0.12, "source", None, True)])
        if "FROM real_preview.candidates" in statement:
            return _Result([("candidate-uuid", "wrong-group" if self.wrong_group else "group-1",
                              "other-preview-uuid" if self.wrong_representative else "preview-uuid",
                              "numeric_source_coordinate", "GB", "Town", None, 51.5, -0.12, "source", 1)])
        raise AssertionError("unexpected query in read-only source identity test")


class _Importer:
    SOURCE_GROUP_KEY_INDEX = 9


class ReprojectTaxonomyTests(unittest.TestCase):
    def setUp(self):
        self.entry = {"source_id": "test.source", "snapshot_sha256": "a" * 64,
                      "source_artifact_sha256": "c" * 64, "normalized_sha256": "d" * 64,
                      "accepted_count": 1, "quarantined_count": 0}
        self.parsed = ("record-1", "numeric_source_coordinate", "GB", "Town", None,
                       51.5, -0.12, "source", None, "group-1")
        raw = {"normalized": {}, "source_values": {}}
        self.handoff = {"rows": [(self.parsed, raw)],
                        "groups": {"group-1": [(self.parsed, raw)]},
                        "representatives": {"group-1": (self.parsed, raw)},
                        "source_url": "https://example.test/source",
                        "manifest": {"retrieved_at_utc": "2026-01-01T00:00:00Z",
                                     "code_version": "code-v1", "config_version": "config-v1"}}

    def test_loopback_target_requires_exact_allowed_database_name(self):
        REPROJECT._validate_preview_database_url(
            "postgresql://user:pass@localhost:55433/uec_v0_review_r2", "uec_v0_review_r2")
        REPROJECT._validate_preview_database_url(
            "postgresql://user:pass@127.0.0.1:55433/uec", "uec")
        for url, database in (("postgresql://u:p@example.test/db", "uec"),
                              ("postgresql://u:p@localhost/db", "uec"),
                              ("postgresql://u:p@localhost/uec", "other")):
            with self.subTest(url=url, database=database), self.assertRaises(ValueError):
                REPROJECT._validate_preview_database_url(url, database)

    def test_dry_run_identity_accepts_exact_snapshot_without_v2_assignments(self):
        checked = REPROJECT._assert_preview_source_identity(
            _IdentityConnection(), "test.source", self.entry, self.handoff, _Importer())
        self.assertEqual(checked["observation_count"], 1)
        self.assertEqual(set(checked["groups"]), {"group-1"})

    def test_stale_latest_snapshot_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "missing or stale"):
            REPROJECT._assert_preview_source_identity(
                _IdentityConnection(stale=True), "test.source", self.entry, self.handoff, _Importer())

    def test_missing_snapshot_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "missing or stale"):
            REPROJECT._assert_preview_source_identity(
                _IdentityConnection(missing=True), "test.source", self.entry, self.handoff, _Importer())

    def test_source_provenance_drift_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "provenance or counts mismatch"):
            REPROJECT._assert_preview_source_identity(
                _IdentityConnection(bad_provenance=True), "test.source", self.entry, self.handoff, _Importer())

    def test_candidate_group_drift_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "group set mismatch"):
            REPROJECT._assert_preview_source_identity(
                _IdentityConnection(wrong_group=True), "test.source", self.entry, self.handoff, _Importer())

    def test_candidate_representative_drift_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "representative mismatch"):
            REPROJECT._assert_preview_source_identity(
                _IdentityConnection(wrong_representative=True), "test.source", self.entry, self.handoff, _Importer())

    def test_frozen_preview_cli_redacts_database_error_payload(self):
        class SyntheticDatabaseError(Exception):
            pass

        class FakeTransaction:
            def __enter__(self):
                return self

            def __exit__(self, _type, _value, _traceback):
                return False

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, _type, _value, _traceback):
                return False

            def transaction(self):
                return FakeTransaction()

            def execute(self, _statement, _params=()):
                raise SyntheticDatabaseError("SYNTHETIC PRIVATE ROW MARKER")

        fake_psycopg = SimpleNamespace(connect=lambda _url: FakeConnection())
        argv = ["reproject-taxonomy.py", "--preview-freeze", "freeze.json", "--inventory", "inventory.json",
                "--expected-database", "uec", "--database-url", "postgresql://user:secret@localhost/uec"]
        stderr = io.StringIO()
        with patch.object(sys, "argv", argv), patch.dict(os.environ, {}, clear=True), \
                patch.dict(sys.modules, {"psycopg": fake_psycopg}), redirect_stderr(stderr):
            self.assertEqual(REPROJECT.main(), 1)
        output = stderr.getvalue()
        self.assertNotIn("SYNTHETIC PRIVATE ROW MARKER", output)
        self.assertNotIn("secret", output)
        self.assertIn('"mode": "blocked"', output)


if __name__ == "__main__":
    unittest.main()
