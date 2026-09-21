import hashlib, tempfile, unittest
from pathlib import Path
from .adapter_contract import SourceArtifact
from .candidate_handoff import write_handoff, CONTRACT_VERSION

class CandidateHandoffTests(unittest.TestCase):
    def artifact(self):
        return SourceArtifact("https://example.test/source", "2026-01-01T00:00:00Z", "a" * 64, 12, code_version="c1", config_version="v1", coverage="synthetic")
    def test_emits_private_importer_contract(self):
        row = {"source_id":"test.source", "source_row":2, "source_values":{"id":"A"}, "normalized":{"establishment_id":"A", "privacy_gate":"pending", "coordinate_gate":"review_required"}}
        with tempfile.TemporaryDirectory() as d:
            m = write_handoff(d, [row], self.artifact(), source_id="test.source")
            self.assertEqual(m["contract_version"], CONTRACT_VERSION); self.assertEqual(m["release_state"], "not-created")
            data = (Path(d) / "normalized/records.jsonl").read_bytes(); self.assertEqual(m["normalized_sha256"], hashlib.sha256(data).hexdigest())
    def test_rejects_guessed_or_missing_identity(self):
        bad = {"source_id":"test.source", "source_row":2, "normalized":{"name":"guess"}}
        with self.assertRaisesRegex(ValueError, "establishment_id"):
            write_handoff(tempfile.mkdtemp(), [bad], self.artifact(), source_id="test.source")

if __name__ == "__main__": unittest.main()
