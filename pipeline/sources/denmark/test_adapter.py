import hashlib, tempfile, unittest
import json
from pathlib import Path
from .adapter import DenmarkSmileyAdapter, check_refresh
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

    def test_registered_bridge_requires_and_checks_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / "raw.xml"; raw.write_bytes(XML)
            adapter = DenmarkSmileyAdapter()
            with self.assertRaisesRegex(ValueError, "missing acquisition provenance"):
                adapter.run_registered(raw, root / "missing", {})
            config = {"source_url": "https://example.test/source.xml", "retrieved_at_utc": "2026-01-01T00:00:00Z", "checksum_sha256": "0" * 64, "byte_size": len(XML)}
            with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                adapter.run_registered(raw, root / "bad", config)
            config["checksum_sha256"] = hashlib.sha256(XML).hexdigest()
            manifest = adapter.run_registered(raw, root / "good", config)
            self.assertEqual(manifest["acquisition"]["source_url"], config["source_url"])

    def test_candidate_mapping_preserves_source_values_and_pending_gates(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / "raw.xml"; raw.write_bytes(XML)
            parsed = {"source_id": "dk.smiley", "source_row": 2, "source_record_key": "1", "source_fields": {"ID_nummer": "1", "Virksomhed": "Test", "Adresse": "Road 1"}}
            manifest = DenmarkSmileyAdapter().write_candidate_handoff(root / "handoff", self.artifact(), [parsed])
            self.assertEqual(manifest["privacy_gate"], "pending")
            handoff = json.loads((root / "handoff" / "normalized/records.jsonl").read_text())
            self.assertEqual(handoff["source_values"]["ID_nummer"], "1")
            self.assertEqual(handoff["normalized"]["establishment_id"], "1")

    def test_refresh_guards_reject_schema_count_and_duplicate_drift(self):
        with self.assertRaisesRegex(ValueError, "schema"):
            check_refresh({"source_id":"dk.smiley", "schema_version":"a", "normalized_rows":10}, {"source_id":"dk.smiley", "schema_version":"b", "normalized_rows":10})
        with self.assertRaisesRegex(ValueError, "count"):
            check_refresh({"source_id":"dk.smiley", "schema_version":"a", "normalized_rows":100}, {"source_id":"dk.smiley", "schema_version":"a", "normalized_rows":50})
        duplicate = {"source_id":"dk.smiley", "source_row":3, "source_record_key":"1", "source_fields":{}}
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "duplicate"):
                DenmarkSmileyAdapter().write_candidate_handoff(Path(d), self.artifact(), [duplicate, duplicate])

if __name__ == "__main__": unittest.main()
