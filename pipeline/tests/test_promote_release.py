import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "stages" / "promote-release.py"
SPEC = importlib.util.spec_from_file_location("promote_release", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleasePromotionTests(unittest.TestCase):
    def test_only_validated_releases_can_be_promoted(self):
        self.assertTrue(MODULE.can_promote("validated"))
        self.assertFalse(MODULE.can_promote("validated", True))
        self.assertFalse(MODULE.can_promote("candidate"))
        self.assertFalse(MODULE.can_promote("promoted"))
        self.assertFalse(MODULE.can_promote("rejected"))

    def test_promotion_script_scopes_replacement_to_profile(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("profile = %s", source)

    def test_test_only_releases_are_never_promotable(self):
        self.assertFalse(MODULE.can_promote("validated", test_only=True))
        self.assertIn("test-only releases cannot be validated or promoted", SCRIPT.read_text(encoding="utf-8"))

    def test_promotion_rechecks_public_safety_gates_and_supports_manifest(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for gate in ("coordinate_not_ready", "review_required", "publication_not_approved", "active_suppression", "rights_not_cleared"):
            self.assertIn(gate, source)
        self.assertIn("--manifest", source)

    def test_promotion_manifest_records_replacement_and_demo_rights_state(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"supersedes": previous[0] if previous else None', source)
        self.assertIn('"rights_review":', source)

    def test_artifact_inventory_hashes_real_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "synthetic.csv"
            artifact.write_bytes(b"id,value\n1,test\n")
            inventory = MODULE.inventory_artifacts([artifact], False)
            self.assertEqual(inventory, [{
                "name": "synthetic.csv",
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "byte_size": artifact.stat().st_size,
            }])

    def test_artifact_inventory_rejects_missing_file_or_implicit_omission(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "declare --artifact"):
                MODULE.inventory_artifacts([], False)
            with self.assertRaisesRegex(ValueError, "not a file"):
                MODULE.inventory_artifacts([Path(directory) / "absent.csv"], False)
            self.assertEqual(MODULE.inventory_artifacts([], True), [])

    def test_canonical_manifest_hash_matches_export_bytes(self):
        manifest = {"release_id": "synthetic", "created_at": "2026-09-13T00:00:00Z", "distributed_artifacts": []}
        serialized = MODULE.canonical_json(manifest)
        self.assertEqual(json.loads(serialized), manifest)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "manifest.json"
            MODULE.write_manifest(output, {"manifest": manifest, "manifest_sha256": digest,
                                           "release_id": "synthetic", "status": "promoted"})
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), digest)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), manifest)
            with self.assertRaises(FileExistsError):
                MODULE.write_manifest(output, {"manifest": manifest, "manifest_sha256": digest})
            with self.assertRaisesRegex(ValueError, "digest does not match"):
                MODULE.write_manifest(output, {"manifest": manifest, "manifest_sha256": "0" * 64})


if __name__ == "__main__":
    unittest.main()
