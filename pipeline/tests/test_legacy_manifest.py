import csv
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[2]
MANIFEST_SCRIPT = REPOSITORY_ROOT / "pipeline/scripts/maintenance/build-legacy-manifest.ps1"
EXPECTED_COLUMNS = {
    "path", "bytes", "sha256", "data_origin",
    "source_retrieval_date_status", "source_retrieval_date",
    "source_observation_date_status", "source_observation_date",
    "generated_at_utc",
}


class LegacyManifestTests(unittest.TestCase):
    def test_generator_emits_metadata_only_legacy_inventory(self):
        output_path = REPOSITORY_ROOT / ".legacy-manifest-test.csv"
        status_path = REPOSITORY_ROOT / ".legacy-status-test.json"
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            self.skipTest("PowerShell is unavailable")
        for path in (output_path, status_path):
            path.unlink(missing_ok=True)
        try:
            subprocess.run(
                [
                    powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(MANIFEST_SCRIPT), "-RepositoryRoot", str(REPOSITORY_ROOT),
                    "-OutputPath", str(output_path), "-StatusOutputPath", str(status_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            with output_path.open(newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
        finally:
            for path in (output_path, status_path):
                path.unlink(missing_ok=True)

        self.assertTrue(rows)
        self.assertEqual(set(rows[0]), EXPECTED_COLUMNS)
        for row in rows:
            input_path = REPOSITORY_ROOT / Path(row["path"])
            self.assertTrue(input_path.is_file(), row["path"])
            self.assertEqual(row["data_origin"], "legacy")
            self.assertEqual(row["source_retrieval_date_status"], "unknown")
            self.assertEqual(row["source_retrieval_date"], "unknown")
            self.assertEqual(row["source_observation_date_status"], "unknown")
            self.assertEqual(row["source_observation_date"], "unknown")
            self.assertEqual(int(row["bytes"]), input_path.stat().st_size)
            self.assertEqual(row["sha256"], hashlib.sha256(input_path.read_bytes()).hexdigest())
            self.assertFalse({"content", "address", "coordinates"} & set(row))

    def test_generator_emits_metadata_only_status_ledger(self):
        output_path = REPOSITORY_ROOT / ".legacy-manifest-test.csv"
        status_path = REPOSITORY_ROOT / ".legacy-status-test.json"
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            self.skipTest("PowerShell is unavailable")
        for path in (output_path, status_path):
            path.unlink(missing_ok=True)
        try:
            subprocess.run(
                [
                    powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(MANIFEST_SCRIPT), "-RepositoryRoot", str(REPOSITORY_ROOT),
                    "-OutputPath", str(output_path), "-StatusOutputPath", str(status_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            with output_path.open(newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            ledger = __import__("json").loads(status_path.read_text(encoding="utf-8"))
        finally:
            for path in (output_path, status_path):
                path.unlink(missing_ok=True)

        self.assertEqual(ledger["schema_version"], "legacy-status-v1")
        self.assertEqual(ledger["scope"], "repository-relative legacy artifact metadata; no raw payloads")
        self.assertEqual(ledger["totals"]["files"], len(rows))
        self.assertEqual(ledger["totals"]["present"], len(rows))
        self.assertEqual(ledger["totals"]["sha256_verified"], len(rows))
        self.assertEqual(ledger["totals"]["metadata_only_not_migrated"], len(rows))
        self.assertEqual(ledger["totals"]["database_migrated"], 0)
        self.assertEqual(ledger["totals"]["lineage_unknown"], len(rows))
        self.assertEqual({record["path"] for record in ledger["records"]}, {row["path"] for row in rows})
        for record in ledger["records"]:
            self.assertEqual(record["artifact_state"], "present")
            self.assertEqual(record["integrity_state"], "sha256_verified")
            self.assertEqual(record["data_origin"], "legacy")
            self.assertEqual(record["lineage_state"], "unknown")
            self.assertEqual(record["currentness_state"], "unknown")
            self.assertEqual(record["database_migration_status"], "metadata_only_not_migrated")
            self.assertEqual(record["publication_status"], "not_eligible")
            self.assertNotIn("content", record)
            self.assertNotIn("address", record)
            self.assertNotIn("coordinates", record)


if __name__ == "__main__":
    unittest.main()
