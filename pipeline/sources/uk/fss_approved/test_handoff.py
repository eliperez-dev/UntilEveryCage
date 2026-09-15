import hashlib, tempfile, unittest
from pathlib import Path
from pipeline.contracts.adapter_contract import SourceArtifact
from .handoff import write_private_handoff

FIXTURE = Path(__file__).parent / "fixtures/valid.csv"
class FssHandoffTests(unittest.TestCase):
    def test_typed_handoff_is_importer_compatible_and_gated(self):
        raw = FIXTURE.read_bytes(); artifact = SourceArtifact("https://example.test/fss", "2026-01-01T00:00:00Z", hashlib.sha256(raw).hexdigest(), len(raw), code_version="test", config_version="test")
        with tempfile.TemporaryDirectory() as d:
            manifest = write_private_handoff(raw_path=FIXTURE, run_dir=d, artifact=artifact)
            self.assertEqual(manifest["publication_state"], "private-candidate")
            row = __import__("json").loads((Path(d) / "normalized/records.jsonl").read_text().splitlines()[0])
            self.assertIn("establishment_id", row["normalized"])
    def test_integrity_fails_before_output(self):
        raw = FIXTURE.read_bytes(); artifact = SourceArtifact("https://example.test/fss", "2026-01-01T00:00:00Z", "0" * 64, len(raw))
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): write_private_handoff(FIXTURE, d, artifact)
            self.assertFalse((Path(d) / "manifest.json").exists())

if __name__ == "__main__": unittest.main()
