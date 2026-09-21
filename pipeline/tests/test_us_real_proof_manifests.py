"""Regression checks for the tracked, row-free US proof manifests."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = ROOT / "data" / "manifests"
FORBIDDEN_ROW_KEYS = {
    "records",
    "rows",
    "source_values",
    "raw_fields",
    "payload",
    "address",
    "coordinates",
}


def _walk_keys(value):
    if isinstance(value, dict):
        yield from value.keys()
        for child in value.values():
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


class UsRealProofManifestTests(unittest.TestCase):
    def test_aphis_manifest_is_private_row_free_and_hash_complete(self):
        path = MANIFEST_DIR / "us-aphis-wave1-real-data-proof-2026-09-18.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["captured_for"], "private/test-only")
        self.assertEqual(manifest["release_state"], "not-created")
        self.assertEqual(manifest["publication_gate"], "blocked")
        artifacts = manifest["raw_artifacts"]
        self.assertEqual(len(artifacts), 112)
        self.assertEqual(
            sum(item["validation"].startswith("failed_") for item in artifacts),
            3,
        )
        for item in artifacts:
            self.assertGreater(item["bytes"], 0)
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(FORBIDDEN_ROW_KEYS.intersection(set(_walk_keys(manifest))))

    def test_fsis_manifest_cannot_be_mistaken_for_current_or_public_data(self):
        path = MANIFEST_DIR / "us-fsis-proof-2026-09-18.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["direct_csv_acquisition"]["status"], "blocked")
        self.assertFalse(manifest["direct_csv_acquisition"]["raw_artifacts_captured"])
        rehearsal = manifest["legacy_continuity_rehearsal"]
        self.assertEqual(rehearsal["release_state"], "not-created")
        self.assertEqual(manifest["publication_eligibility"], "blocked")
        self.assertTrue(rehearsal["unmatched_demographic_is_not_closure"])
        self.assertFalse(FORBIDDEN_ROW_KEYS.intersection(set(_walk_keys(manifest))))

    def test_manifest_content_is_stable_across_line_endings(self):
        expected = {
            "us-aphis-wave1-real-data-proof-2026-09-18.json": "fb5dcfd35efb17c5c0a17e6d08d407e2b32fd99b864ba8bc95f224989362c795",
            "us-fsis-proof-2026-09-18.json": "6f75f40c41b14c061a388c1c9578b6995bd6b8c17a9fde2948b5fc74adbb3812",
        }
        for name, digest in expected.items():
            normalized = (MANIFEST_DIR / name).read_text(encoding="utf-8").encode("utf-8")
            self.assertEqual(hashlib.sha256(normalized).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
