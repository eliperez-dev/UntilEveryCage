import csv
import hashlib
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
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "legacy-files.csv"
            subprocess.run(
                [
                    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(MANIFEST_SCRIPT), "-RepositoryRoot", str(REPOSITORY_ROOT),
                    "-OutputPath", str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            with output_path.open(newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))

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


if __name__ == "__main__":
    unittest.main()
