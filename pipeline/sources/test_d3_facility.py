from __future__ import annotations

import hashlib
import json
import shutil
import unittest
from pathlib import Path

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.sources.d3_facility import D3_DESCRIPTORS, GermanyBltuAdapter


class D3FacilityAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[2]
        self.out = self.root.parent / ".d3-facility-test"
        shutil.rmtree(self.out, ignore_errors=True)
        self.out.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.out, ignore_errors=True)

    def test_four_distinct_facility_sources_have_sanitized_fixtures(self):
        self.assertEqual({item["source_id"] for item in D3_DESCRIPTORS()}, {
            "us.fsis", "de.locations", "fsa_approved_establishments", "fss_approved_establishments",
        })
        for item in D3_DESCRIPTORS():
            self.assertTrue(item["fixture"].exists(), item["source_id"])

    def test_private_fixture_runs_preserve_provenance_and_block_release(self):
        for item in D3_DESCRIPTORS():
            path = item["fixture"]
            files = sorted(path.iterdir()) if path.is_dir() else [path]
            raw = b"".join(candidate.read_bytes() for candidate in files if candidate.is_file() and candidate.suffix.lower() in {".csv", ".txt"})
            artifact = SourceArtifact(
                source_url=item["url"], retrieved_at_utc="2026-01-01T00:00:00Z",
                sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw),
                code_version=item["adapter_version"], config_version=item["schema_version"],
                rights_caveat="test fixture only", privacy_caveat="private test only",
            )
            output = self.out / item["source_id"].replace(".", "_")
            manifest = item["factory"]().run(path, output, artifact)
            self.assertEqual(manifest["release_state"], "not-created", item["source_id"])
            self.assertEqual(manifest["publication_state"], "private-candidate", item["source_id"])
            self.assertEqual(manifest["input_rows"], manifest["normalized_rows"] + manifest["quarantined_rows"])
            self.assertEqual(manifest["checksum_sha256"], hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else manifest["checksum_sha256"])
            self.assertFalse((output / "released" / "records.jsonl").exists())
            self.assertTrue((output / "normalized" / "records.jsonl").exists())

    def test_germany_bridge_uses_authoritative_identity(self):
        item = next(value for value in D3_DESCRIPTORS() if value["source_id"] == "de.locations")
        path = item["fixture"]
        raw = path.read_bytes()
        artifact = SourceArtifact(source_url=item["url"], retrieved_at_utc="2026-01-01T00:00:00Z",
                                  sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw),
                                  code_version=item["adapter_version"], config_version=item["schema_version"])
        output = self.out / "germany"
        manifest = GermanyBltuAdapter().run(path, output, artifact)
        rows = [json.loads(line) for line in (output / "normalized" / "records.jsonl").read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(manifest["source_id"], "de.locations")
        self.assertTrue(all(row["source_id"] == "de.locations" for row in rows))


if __name__ == "__main__":
    unittest.main()
