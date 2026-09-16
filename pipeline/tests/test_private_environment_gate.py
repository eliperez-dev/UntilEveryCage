"""Synthetic contract tests for the private startup/deployment gate."""
import importlib.util
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
REPOSITORY = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location(
    "private_environment_gate",
    ROOT / "scripts" / "maintenance" / "private-environment-gate.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrivateEnvironmentGateTests(unittest.TestCase):
    def setUp(self):
        self.values = {
            "UEC_RUNTIME_MODE": "production",
            "UEC_DATABASE_URL": "postgresql://redacted.invalid/uec",
            "UEC_CORS_ORIGINS": "https://example.invalid",
            "UEC_TRUST_PROXY": "true",
            "UEC_TRUSTED_PROXY_CIDRS": "192.0.2.0/24",
        }

    def fixtures(self, directory):
        ledger = {
            "schema_version": 1,
            "revision": "synthetic-r1",
            "active_restrictions": [{
                "source_id": "synthetic",
                "source_record_key": "opaque-1",
                "scope": "whole_record",
                "action": "suppress",
            }],
        }
        ledger["ledger_sha256"] = MODULE.ledger_digest(ledger)
        snapshot = {
            "ledger_revision": ledger["revision"],
            "ledger_sha256": ledger["ledger_sha256"],
            "active_restrictions": ledger["active_restrictions"],
        }
        manifest = {
            "manifest_version": "v1",
            "release_id": "synthetic-release",
            "profile": "official",
            "ruleset_version": "synthetic-v1",
            "distributed_artifacts": [],
        }
        paths = {name: Path(directory) / name for name in ("ledger.json", "snapshot.json", "manifest.json")}
        paths["ledger.json"].write_text(json.dumps(ledger), encoding="utf-8")
        paths["snapshot.json"].write_text(json.dumps(snapshot), encoding="utf-8")
        paths["manifest.json"].write_text(MODULE.canonical_json(manifest), encoding="utf-8")
        return paths, MODULE.canonical_json(manifest)

    def test_full_gate_reports_only_safe_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, manifest_json = self.fixtures(directory)
            report = MODULE.run_gate(
                REPOSITORY, self.values, paths["ledger.json"], paths["snapshot.json"],
                paths["manifest.json"], hashlib.sha256(manifest_json.encode()).hexdigest(),
            )
            self.assertEqual(report["status"], "pass")
            self.assertGreater(report["checks"]["migration_count"], 0)
            self.assertEqual(report["checks"]["restriction_ledger"]["active_restriction_count"], 1)
            self.assertNotIn("opaque-1", json.dumps(report["checks"]["restriction_ledger"]))

    def test_stale_replay_and_missing_proxy_boundary_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, _ = self.fixtures(directory)
            stale = json.loads(paths["snapshot.json"].read_text(encoding="utf-8"))
            stale["ledger_revision"] = "old"
            paths["snapshot.json"].write_text(json.dumps(stale), encoding="utf-8")
            with self.assertRaises(MODULE.PrivateEnvironmentError):
                MODULE.verify_ledger_replay(paths["ledger.json"], paths["snapshot.json"])
        invalid = dict(self.values, UEC_TRUSTED_PROXY_CIDRS=None)
        with self.assertRaises(MODULE.PrivateEnvironmentError):
            MODULE.validate_runtime_config(invalid)

    def test_manifest_rejects_path_traversal_and_migration_inventory_is_versioned(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, _ = self.fixtures(directory)
            manifest = json.loads(paths["manifest.json"].read_text(encoding="utf-8"))
            manifest["distributed_artifacts"] = [{"name": "../private.txt", "sha256": "0" * 64, "byte_size": 1}]
            serialized = MODULE.canonical_json(manifest)
            paths["manifest.json"].write_text(serialized, encoding="utf-8")
            with self.assertRaises(MODULE.PrivateEnvironmentError):
                MODULE.validate_release_manifest(paths["manifest.json"], hashlib.sha256(serialized.encode()).hexdigest())
        inventory = MODULE.validate_migrations(ROOT / "migrations")
        self.assertGreater(inventory["migration_count"], 0)
        self.assertEqual(len(inventory["migration_inventory_sha256"]), 64)

    def test_replay_sql_is_idempotent_and_does_not_embed_sensitive_columns(self):
        replay_spec = importlib.util.spec_from_file_location(
            "replay_restriction_ledger",
            ROOT / "scripts" / "maintenance" / "replay-restriction-ledger.py",
        )
        replay = importlib.util.module_from_spec(replay_spec)
        replay_spec.loader.exec_module(replay)
        with tempfile.TemporaryDirectory() as directory:
            paths, _ = self.fixtures(directory)
            sql = replay.replay_sql(paths["ledger.json"])
            self.assertIn("BEGIN;", sql)
            self.assertIn("RAISE EXCEPTION", sql)
            self.assertIn("record_access_events", sql)
            self.assertNotIn("address", sql.lower())
            self.assertNotIn("coordinate", sql.lower())

    def test_emit_sql_does_not_require_site_packages(self):
        script = ROOT / "scripts" / "maintenance" / "replay-restriction-ledger.py"
        replay_spec = importlib.util.spec_from_file_location("replay_restriction_ledger_no_site", script)
        replay = importlib.util.module_from_spec(replay_spec)
        replay_spec.loader.exec_module(replay)
        with tempfile.TemporaryDirectory() as directory:
            paths, _ = self.fixtures(directory)
            expected = replay.replay_sql(paths["ledger.json"])
            result = subprocess.run(
                [sys.executable, "-S", str(script), "--ledger", str(paths["ledger.json"]), "--emit-sql"],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, expected)


if __name__ == "__main__":
    unittest.main()
