"""Disposable readiness checks for incomplete and fully migrated databases."""
import json
import os
import unittest
import urllib.error
import urllib.request
from .fixture import E2EEnvironment, ROOT


@unittest.skipUnless(os.environ.get("UEC_RUN_E2E") == "1", "set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
class ReadinessE2ETests(unittest.TestCase):
    def test_partial_schema_is_not_ready(self):
        env = E2EEnvironment()
        try:
            migrations = sorted((ROOT / "pipeline/migrations").glob("*.sql"))
            env.start(migration_files=migrations[:1], wait_for_ready=False)
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
        finally:
            env.stop()


if __name__ == "__main__":
    unittest.main()
