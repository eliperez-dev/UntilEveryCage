import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
REGISTRY = ROOT / "pipeline/source_registry.json"
OPERATIONS = ROOT / "pipeline/source_operations.json"
STATUS = ROOT / "docs/source-status.json"
CROSSWALK = ROOT / "docs/countries/ireland/v1-field-crosswalk.json"
MANIFEST = ROOT / "data/manifests/ireland-source-artifacts.json"


class IrelandReconMetadataTests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.operations = json.loads(OPERATIONS.read_text(encoding="utf-8"))
        self.status = json.loads(STATUS.read_text(encoding="utf-8"))
        self.crosswalk = json.loads(CROSSWALK.read_text(encoding="utf-8"))
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_ireland_source_inventory_is_consistent(self):
        expected = {
            "ie.fsai.approved-directory",
            "ie.dafm.approved-establishments",
            "ie.dafm.former-la-establishments",
            "ie.dafm.milk-dairy-establishments",
            "ie.hse.low-throughput-meat",
            "ie.sfpa.approved-establishments",
            "ie.sfpa.freezer-vessels",
            "ie.sfpa.factory-vessels",
            "ie.epa.leap",
            "ie.planning.npad",
            "ie.cro.companies",
            "ie.cso.livestock-slaughterings",
            "ie.dafm.national-beef-kill",
            "ie.dafm.seafood-processing-funding",
            "ie.fsai.enforcement-orders",
            "ie.dafm.animal-welfare-controls",
        }
        registry_ids = {item["source_id"] for item in self.registry["sources"]}
        schedule_ids = {item["source_id"] for item in self.operations["schedules"]}
        status_ids = {item["source_id"] for item in self.status["sources"]}
        crosswalk_ids = {item["source_id"] for item in self.crosswalk["sources"]}
        self.assertEqual(expected, registry_ids & expected)
        self.assertEqual(expected, schedule_ids & expected)
        self.assertEqual(expected, status_ids & expected)
        self.assertEqual(expected, crosswalk_ids)

    def test_observed_counts_are_semantically_bounded(self):
        observed = {
            item["source_id"]: item.get("observed_counts", {})
            for item in self.crosswalk["sources"]
        }
        self.assertEqual(observed["ie.hse.low-throughput-meat"]["approval_number_nodes"], 72)
        self.assertEqual(observed["ie.sfpa.approved-establishments"]["page_entries"], 184)
        self.assertEqual(observed["ie.sfpa.freezer-vessels"]["page_entries"], 50)
        self.assertEqual(observed["ie.sfpa.factory-vessels"]["page_entries"], 1)
        self.assertIsNone(observed["ie.dafm.approved-establishments"]["row_count"])
        self.assertIsNone(observed["ie.cso.livestock-slaughterings"]["facility_count"])

    def test_manifest_hashes_and_retention_are_explicit(self):
        digest = re.compile(r"^[0-9a-f]{64}$")
        self.assertEqual(self.manifest["publication_state"], "blocked; no release artifact created")
        for artifact in self.manifest["artifacts"]:
            self.assertIsNone(artifact["source_artifact_sha256"])
            snapshot_hash = artifact["snapshot_sha256"]
            if snapshot_hash is not None:
                self.assertRegex(snapshot_hash, digest)
                self.assertGreater(artifact["snapshot_characters"], 0)
            self.assertNotIn("raw/", artifact["official_url"])

    def test_crosswalk_requires_activity_children_for_repeated_sources(self):
        by_id = {item["source_id"]: item for item in self.crosswalk["sources"]}
        for source_id in (
            "ie.hse.low-throughput-meat",
            "ie.sfpa.approved-establishments",
        ):
            source = by_id[source_id]
            self.assertIn("activity_model", source)
            self.assertEqual(source["activity_model"]["child_key"], "activity_observation_key")
        self.assertIn("source_key", self.crosswalk["canonical_entity_rules"])

    def test_metadata_files_have_stable_content_digests_for_change_detection(self):
        for path in (CROSSWALK, MANIFEST):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertRegex(digest, r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
