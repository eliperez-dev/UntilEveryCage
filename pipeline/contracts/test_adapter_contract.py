import unittest
import hashlib
import tempfile
from pathlib import Path
from .adapter_contract import SourceArtifact, source_artifact_from_mapping
from .source_lifecycle import atomic_json, atomic_jsonl, private_manifest
from pipeline.common.orchestrator import run_private_lifecycle

class ArtifactBoundaryTests(unittest.TestCase):
    def test_legacy_mapping_is_explicitly_normalized(self):
        artifact = source_artifact_from_mapping({"source_url":"https://example.test", "retrieved_at_utc":"2026-01-01T00:00:00Z", "checksum_sha256":"a"*64, "byte_size":3})
        self.assertIsInstance(artifact, SourceArtifact); self.assertEqual(artifact.sha256, "a"*64)
    def test_missing_mapping_provenance_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "source_url"):
            source_artifact_from_mapping({"checksum_sha256":"a"*64, "byte_size":3})

    def test_synthetic_source_adapter_runs_the_private_lifecycle_contract(self):
        class SyntheticAdapter:
            source_id = "test.synthetic"
            adapter_version = "synthetic-v1"
            schema_version = "synthetic-schema-v1"

            def run(self, raw_path, run_dir, artifact):
                raw = Path(raw_path).read_bytes()
                if hashlib.sha256(raw).hexdigest() != artifact.sha256:
                    raise ValueError("synthetic adapter received mismatched provenance")
                root = Path(run_dir)
                parsed = [{"source_values": {"label": raw.decode()}}]
                normalized = [{"source_id": self.source_id, "source_values": {"label": raw.decode()},
                              "normalized": {"label": raw.decode()}}]
                quarantined = []
                _, parsed_hash, _ = atomic_jsonl(root / "parsed/records.jsonl", parsed)
                _, normalized_hash, _ = atomic_jsonl(root / "normalized/records.jsonl", normalized)
                atomic_jsonl(root / "quarantined/records.jsonl", quarantined)
                manifest = private_manifest(
                    source_id=self.source_id, adapter_version=self.adapter_version,
                    schema_version=self.schema_version, artifact=artifact, input_rows=1,
                    normalized_rows=1, quarantined_rows=0,
                    normalized_sha256=normalized_hash, parsed_sha256=parsed_hash,
                )
                atomic_json(root / "manifest.json", manifest)
                return manifest

        raw = b"synthetic fixture only"
        artifact = SourceArtifact("https://example.test/synthetic", "2026-09-25T00:00:00Z",
                                  hashlib.sha256(raw).hexdigest(), len(raw))
        with tempfile.TemporaryDirectory(dir=Path(__file__).parents[2]) as directory:
            root = Path(directory)
            raw_path = root / "preserved.csv"
            raw_path.write_bytes(raw)
            status = run_private_lifecycle(raw_path, root / "runs", artifact, SyntheticAdapter())
            self.assertEqual(status["status"], "candidate-ready")
            self.assertEqual(status["manifest"]["release_state"], "not-created")
            self.assertEqual(status["manifest"]["input_rows"], 1)
            self.assertTrue((Path(status["run_dir"]) / "qa.json").is_file())

if __name__ == "__main__": unittest.main()
