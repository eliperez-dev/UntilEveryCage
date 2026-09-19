import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from .adapter_contract import SourceArtifact
from .source_lifecycle import SourceConfig, atomic_jsonl, private_manifest, validate_private_manifest


class SourceLifecyclePrimitiveTests(unittest.TestCase):
    def artifact(self, raw: bytes = b"synthetic") -> SourceArtifact:
        return SourceArtifact(
            "https://example.test/source", "2026-09-15T00:00:00Z",
            hashlib.sha256(raw).hexdigest(), len(raw),
            code_version="adapter-v1", config_version="config-v1",
        )

    def test_jsonl_hash_and_bytes_are_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            one = Path(directory) / "one.jsonl"
            two = Path(directory) / "two.jsonl"
            rows = [{"source_id": "x", "value": 2}, {"source_id": "x", "value": 1}]
            _, first_hash, first_count = atomic_jsonl(one, rows)
            _, second_hash, second_count = atomic_jsonl(two, rows)
            self.assertEqual(first_hash, second_hash)
            self.assertEqual(first_count, second_count)
            self.assertEqual(one.read_bytes(), two.read_bytes())
            self.assertEqual([json.loads(line) for line in one.read_text().splitlines()], rows)

    def test_source_config_is_a_small_checked_in_interface(self):
        config = SourceConfig("x", "https://example.test/x", "adapter-v1", "schema-v1")
        self.assertEqual(config.as_mapping()["geocoding"], "disabled")
        with self.assertRaisesRegex(ValueError, "source_id"):
            SourceConfig("", "https://example.test/x", "adapter-v1", "schema-v1")

    def test_manifest_reconciles_counts_and_keeps_release_uncreated(self):
        manifest = private_manifest(
            source_id="x", adapter_version="a", schema_version="s",
            artifact=self.artifact(), input_rows=3, normalized_rows=2,
            quarantined_rows=1, normalized_sha256="b" * 64,
        )
        self.assertEqual(manifest["contract_version"], "source-lifecycle-v1")
        self.assertEqual(manifest["release_state"], "not-created")
        with self.assertRaisesRegex(ValueError, "reconcile"):
            validate_private_manifest({**manifest, "quarantined_rows": 2})


if __name__ == "__main__":
    unittest.main()
