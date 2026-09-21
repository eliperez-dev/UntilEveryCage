import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from .adapter_contract import SourceArtifact
from .private_run import PrivateRunError, run_typed_adapter, summarize_private_run


class StubAdapter:
    source_id = "test.source"
    adapter_version = "test-v1"

    def run(self, raw_path, run_dir, artifact):
        raw = Path(raw_path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != artifact.sha256:
            raise ValueError("hash mismatch")
        root = Path(run_dir)
        root.joinpath("normalized").mkdir(parents=True)
        rows = [{"source_id": self.source_id, "normalized": {"establishment_id": "A"}}]
        root.joinpath("normalized/records.jsonl").write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
        return {
            "source_id": self.source_id,
            "adapter_version": self.adapter_version,
            "schema_version": "test-schema",
            "source_url": artifact.source_url,
            "retrieved_at_utc": artifact.retrieved_at_utc,
            "checksum_sha256": artifact.sha256,
            "byte_size": len(raw),
            "input_rows": 2,
            "normalized_rows": 1,
            "quarantined_rows": 1,
            "publication_state": "private-candidate",
            "release_state": "not-created",
            "geocoding": "disabled",
            "anomaly_counts": {"synthetic_quarantine": 1},
        }


class PrivateRunTests(unittest.TestCase):
    def artifact(self, raw):
        return SourceArtifact("https://example.test", "2026-09-14T00:00:00Z", hashlib.sha256(raw).hexdigest(), len(raw), code_version="c", config_version="k")

    def test_typed_runner_writes_row_free_report_and_not_observed_delta(self):
        raw = b"synthetic"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_path = root / "raw.bin"
            raw_path.write_bytes(raw)
            previous = root / "previous.jsonl"
            previous.write_text(json.dumps({"normalized": {"establishment_id": "A"}}) + "\n" + json.dumps({"normalized": {"establishment_id": "B"}}) + "\n", encoding="utf-8")
            manifest, report = run_typed_adapter(StubAdapter(), raw_path, root / "run", self.artifact(raw), previous_normalized_path=previous)
            self.assertEqual(report["disappeared_not_observed_count"], 1)
            self.assertIn("not-observed", report["disappearance_semantics"])
            self.assertEqual(report["anomaly_counts"], {"synthetic_quarantine": 1})
            self.assertNotIn("source_values", (root / "run/qa.json").read_text())

    def test_manifest_invariants_fail_closed(self):
        with self.assertRaisesRegex(PrivateRunError, "row counts"):
            summarize_private_run({"source_id": "x", "input_rows": 2, "normalized_rows": 2, "quarantined_rows": 2, "release_state": "not-created"})


if __name__ == "__main__":
    unittest.main()
