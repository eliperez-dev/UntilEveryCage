import hashlib, tempfile, unittest
from pathlib import Path
from .adapter import DenmarkSmileyAdapter
from pipeline.contracts.adapter_contract import SourceArtifact

XML = b'<Root><Row><ID_nummer>1</ID_nummer><Virksomhed>Test</Virksomhed></Row><Row><Virksomhed>Unkeyed</Virksomhed></Row></Root>'

class DenmarkAdapterTests(unittest.TestCase):
    def artifact(self, data=XML):
        return SourceArtifact("https://example.test/smiley.xml", "2026-01-01T00:00:00Z", hashlib.sha256(data).hexdigest(), len(data), code_version="test", config_version="test")

    def test_rerun_is_deterministic_and_private(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / "raw.xml"; raw.write_bytes(XML)
            a = DenmarkSmileyAdapter().run(raw, root / "one", self.artifact())
            b = DenmarkSmileyAdapter().run(raw, root / "two", self.artifact())
            self.assertEqual(a, b); self.assertEqual(a["quarantined_rows"], 1)
            self.assertFalse((root / "one" / "released").exists())

    def test_failed_acquisition_does_not_write_staging(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / "raw.xml"; raw.write_bytes(XML)
            with self.assertRaises(ValueError): DenmarkSmileyAdapter().run(raw, root / "run", self.artifact(b"wrong"))
            self.assertFalse((root / "run").exists())

if __name__ == "__main__": unittest.main()
