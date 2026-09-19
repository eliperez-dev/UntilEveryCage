import unittest
from .adapter_contract import SourceArtifact, source_artifact_from_mapping

class ArtifactBoundaryTests(unittest.TestCase):
    def test_legacy_mapping_is_explicitly_normalized(self):
        artifact = source_artifact_from_mapping({"source_url":"https://example.test", "retrieved_at_utc":"2026-01-01T00:00:00Z", "checksum_sha256":"a"*64, "byte_size":3})
        self.assertIsInstance(artifact, SourceArtifact); self.assertEqual(artifact.sha256, "a"*64)
    def test_missing_mapping_provenance_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "source_url"):
            source_artifact_from_mapping({"checksum_sha256":"a"*64, "byte_size":3})

if __name__ == "__main__": unittest.main()
