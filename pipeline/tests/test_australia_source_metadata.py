import hashlib
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class AustraliaSourceMetadataTests(unittest.TestCase):
    def test_crosswalk_ids_are_unique_and_registered(self):
        crosswalk = json.loads((ROOT / "docs/countries/australia/source-crosswalk.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "pipeline/source_registry.json").read_text(encoding="utf-8"))
        crosswalk_ids = [item["source_id"] for item in crosswalk["sources"]]
        registry_ids = {item["source_id"] for item in registry["sources"]}
        self.assertEqual(len(crosswalk_ids), len(set(crosswalk_ids)))
        self.assertTrue(set(crosswalk_ids) <= registry_ids)
        self.assertEqual(crosswalk["publication_state"], "private-reconnaissance-only")

    def test_npi_metadata_matches_private_artifact(self):
        metadata = json.loads((ROOT / "data/raw/australia/metadata.json").read_text(encoding="utf-8"))
        artifact = ROOT / metadata["artifact"]["relative_path"]
        self.assertEqual(metadata["source_id"], "au.npi.facilities")
        if artifact.exists():
            self.assertEqual(artifact.stat().st_size, metadata["artifact"]["byte_size"])
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            self.assertEqual(digest, metadata["artifact"]["sha256"])
        else:
            ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", "--", str(artifact.relative_to(ROOT))],
                cwd=ROOT,
                check=False,
            )
            tracked = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", str(artifact.relative_to(ROOT))],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(ignored.returncode, 0)
            self.assertNotEqual(tracked.returncode, 0)
        self.assertEqual(metadata["artifact"]["input_rows"], 8140)
        self.assertEqual(len(metadata["artifact"]["columns"]), 22)
        self.assertEqual(metadata["bounded_observations"]["rows_with_missing_latitude_or_longitude"], 0)


if __name__ == "__main__":
    unittest.main()
