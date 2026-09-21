import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "data" / "manifests" / "pl-source-artifacts.json"
PRIVATE_METADATA = ROOT / "data" / "raw" / "poland" / "20260916T000000Z" / "metadata.json"


class PolandMetadataIntegrityTests(unittest.TestCase):
    def test_manifest_and_crosswalk_have_unique_source_ids(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        crosswalk = json.loads((ROOT / "docs" / "countries" / "pl" / "source-crosswalk.json").read_text(encoding="utf-8"))
        manifest_ids = [item["source_id"] for item in manifest["artifacts"]]
        crosswalk_ids = [item["source_id"] for item in crosswalk["sources"]]
        self.assertEqual(len(manifest_ids), len(set(manifest_ids)))
        self.assertEqual(len(crosswalk_ids), len(set(crosswalk_ids)))
        self.assertEqual(set(manifest_ids) - {"pl.private.recon-metadata"}, set(crosswalk_ids))

    def test_private_metadata_hash_and_privacy_boundary(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        metadata = json.loads(PRIVATE_METADATA.read_text(encoding="utf-8"))
        entry = next(item for item in manifest["artifacts"] if item["source_id"] == "pl.private.recon-metadata")
        canonical_bytes = PRIVATE_METADATA.read_bytes().replace(b"\r\n", b"\n")
        digest = hashlib.sha256(canonical_bytes).hexdigest()
        self.assertEqual(entry["sha256"], digest)
        self.assertEqual(entry["bytes"], len(canonical_bytes))
        privacy = metadata["privacy"]
        self.assertFalse(privacy["raw_source_rows_retained"])
        self.assertFalse(privacy["addresses_retained"])
        self.assertFalse(privacy["coordinates_retained"])
        self.assertFalse(privacy["personal_contacts_retained"])

    def test_giw_counts_are_nonnegative_and_not_facility_total(self):
        metadata = json.loads(PRIVATE_METADATA.read_text(encoding="utf-8"))
        giw = next(item for item in metadata["source_observations"] if item["source_id"] == "pl.giw.approved-food")
        counts = giw["observed_sections"]
        self.assertTrue(all(isinstance(value, int) and value >= 0 for value in counts.values()))
        self.assertEqual(giw["capture_status"], "metadata_only")
        self.assertIn("one-to-many", giw["row_identity"])


if __name__ == "__main__":
    unittest.main()
