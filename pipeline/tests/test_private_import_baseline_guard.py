"""Synthetic guard tests for source-scoped imports beside the approved V0 copy."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


IMPORTER_PATH = Path(__file__).parents[1] / "scripts" / "maintenance" / "import-real-preview.py"
IMPORTER_SPEC = importlib.util.spec_from_file_location("import_real_preview_baseline_guard", IMPORTER_PATH)
IMPORTER = importlib.util.module_from_spec(IMPORTER_SPEC)
assert IMPORTER_SPEC.loader
IMPORTER_SPEC.loader.exec_module(IMPORTER)


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _LaunchTestConnection:
    def __init__(self, database=IMPORTER.LAUNCH_BASELINE_DATABASE):
        self.database = database
        self.isolation_set = False

    def execute(self, query, params=None):
        if query.startswith("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"):
            self.isolation_set = True
            return _Result(None)
        if "current_database()" in query:
            return _Result((self.database,))
        raise AssertionError("unexpected database query")


class PrivateImportBaselineGuardTests(unittest.TestCase):
    def test_assigned_loopback_baseline_requires_v0_and_records_source_state(self):
        connection = _LaunchTestConnection()
        before = {"counts": {"release_members": 3}, "sha256": "a" * 64}
        database_url = f"postgresql://operator:secret@127.0.0.1/{IMPORTER.LAUNCH_BASELINE_DATABASE}"
        with patch.object(IMPORTER, "source_public_counts", return_value=(3, 0)), \
             patch.object(IMPORTER, "source_public_state", return_value=before), \
             patch("pipeline.scripts.release_baseline.verify_connection", return_value={"status": "verified"}) as verify:
            captured = IMPORTER._prepare_launch_baseline_state(connection, database_url, "fsa_approved_establishments")
        self.assertEqual(captured, before)
        self.assertTrue(connection.isolation_set)
        verify.assert_called_once()

    def test_unverified_v0_baseline_fails_closed_without_exposing_details(self):
        connection = _LaunchTestConnection()
        database_url = f"postgresql://operator:secret@127.0.0.1/{IMPORTER.LAUNCH_BASELINE_DATABASE}"
        with patch.object(IMPORTER, "source_public_counts", return_value=(3, 0)), \
             patch("pipeline.scripts.release_baseline.verify_connection", side_effect=ValueError("sensitive diagnostic")):
            with self.assertRaises(IMPORTER.ImportFailure) as failure:
                IMPORTER._prepare_launch_baseline_state(connection, database_url, "fsa_approved_establishments")
        self.assertEqual(failure.exception.code, "launch_baseline_verification_failed")
        self.assertNotIn("sensitive", str(failure.exception))

    def test_unknown_database_never_receives_baseline_exception(self):
        connection = _LaunchTestConnection(database="different_test_db")
        database_url = "postgresql://operator:secret@127.0.0.1/different_test_db"
        with patch.object(IMPORTER, "source_public_counts", return_value=(3, 0)), \
             patch("pipeline.scripts.release_baseline.verify_connection") as verify:
            self.assertIsNone(IMPORTER._prepare_launch_baseline_state(
                connection, database_url, "fsa_approved_establishments"))
        self.assertFalse(connection.isolation_set)
        verify.assert_not_called()

    def test_source_public_state_change_fails_closed(self):
        connection = object()
        before = {"counts": {"release_members": 3}, "sha256": "a" * 64}
        changed = {"counts": {"release_members": 3}, "sha256": "b" * 64}
        with patch.object(IMPORTER, "source_public_state", return_value=changed):
            with self.assertRaises(IMPORTER.ImportFailure) as failure:
                IMPORTER._assert_launch_baseline_state_unchanged(
                    connection, "fsa_approved_establishments", before)
        self.assertEqual(failure.exception.code, "launch_baseline_source_state_changed")

    def test_unchanged_source_public_state_returns_verified_counts(self):
        connection = object()
        state = {"counts": {"release_members": 3, "uec.map_facilities_public_discovery": 2},
                 "sha256": "a" * 64}
        with patch.object(IMPORTER, "source_public_state", return_value=state):
            counts = IMPORTER._assert_launch_baseline_state_unchanged(
                connection, "fsa_approved_establishments", state)
        self.assertEqual(counts, (3, 2))


if __name__ == "__main__":
    unittest.main()
