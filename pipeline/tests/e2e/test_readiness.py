"""Disposable readiness checks for incomplete and fully migrated databases."""
import hashlib
import json
import os
import socket
import subprocess
import unittest
import urllib.error
import urllib.request
from .fixture import E2EEnvironment, ROOT, free_port


@unittest.skipUnless(os.environ.get("UEC_RUN_E2E") == "1", "set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
class ReadinessE2ETests(unittest.TestCase):
    def test_partial_schema_is_not_ready(self):
        env = E2EEnvironment()
        try:
            migrations = sorted((ROOT / "pipeline/migrations").glob("*.sql"))
            # This deliberately exercises the backend's own readiness
            # response against a partial schema, so skip the normal full
            # schema preflight for this one negative-path fixture.
            env.start(migration_files=migrations[:1], wait_for_ready=False, schema_preflight=False)
            env.wait_for_listening()
            self.assertIsNone(env.backend.poll(), "backend must stay alive to report schema readiness")
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{env.api_port}/health/ready", timeout=2)
            except urllib.error.HTTPError as response:
                self.assertEqual(response.code, 503)
                body = json.load(response)
                self.assertEqual(body["reason"], "database_schema_not_migrated")
            else:
                self.fail("partial schema was reported ready")
        finally:
            env.stop()

    def test_full_schema_is_ready(self):
        env = E2EEnvironment()
        try:
            env.start()
            with urllib.request.urlopen(f"http://127.0.0.1:{env.api_port}/health/ready", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.load(response)["schema"], "migrated")
            with urllib.request.urlopen(f"http://127.0.0.1:{env.api_port}/health/diagnostics", timeout=2) as response:
                diagnostics = json.load(response)
                self.assertEqual(response.status, 200)
                self.assertEqual(diagnostics["privacy"]["diagnostic_identifiers"], "excluded")
                self.assertNotIn("database_url", json.dumps(diagnostics))
                self.assertNotIn("forwarded", json.dumps(diagnostics).lower())
            # A migrated database alone is insufficient in production: the
            # current release's authoritative totals must be ready before bind.
            digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            ledger = {"schema_version": 1, "revision": "synthetic-startup", "active_restrictions": []}
            ledger["ledger_sha256"] = digest(ledger)
            snapshot = {"ledger_revision": ledger["revision"], "ledger_sha256": ledger["ledger_sha256"], "active_restrictions": []}
            manifest = {"manifest_version": "v1", "release_id": "synthetic-startup", "profile": "official", "ruleset_version": "synthetic-v1"}
            for name, value in (("ledger", ledger), ("snapshot", snapshot), ("manifest", manifest)):
                (env.cargo_target_dir / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
            production_port = free_port()
            production_env = {key: value for key, value in os.environ.items() if not key.startswith("UEC_")}
            production_env.update({"UEC_RUNTIME_MODE": "production", "UEC_DATABASE_URL": env.database_url,
                "UEC_BIND_HOST": "127.0.0.1", "PORT": str(production_port), "UEC_TRUST_PROXY": "false",
                "UEC_CORS_ORIGINS": "https://example.test",
                "UEC_RESTRICTION_LEDGER_PATH": str(env.cargo_target_dir / "ledger.json"),
                "UEC_RESTORED_RESTRICTION_SNAPSHOT_PATH": str(env.cargo_target_dir / "snapshot.json"),
                "UEC_RELEASE_MANIFEST_PATH": str(env.cargo_target_dir / "manifest.json"),
                "UEC_RELEASE_MANIFEST_SHA256": digest(manifest)})
            result = subprocess.run([env.backend.args[0]], cwd=ROOT, env=production_env,
                capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 2)
            events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
            warmup = next(event for event in events if event.get("event") == "startup_facets_warmup")
            self.assertFalse(warmup["success"])
            self.assertEqual(warmup["status"], 404)
            with socket.socket() as probe:
                self.assertNotEqual(probe.connect_ex(("127.0.0.1", production_port)), 0)
        finally:
            env.stop()


if __name__ == "__main__":
    unittest.main()
