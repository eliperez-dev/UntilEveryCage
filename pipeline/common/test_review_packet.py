import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.sources.denmark.adapter import DenmarkSmileyAdapter


class ReviewPacketTests(unittest.TestCase):
    def test_packet_is_row_free_and_delta_is_explicitly_not_observed(self):
        raw = b"<Root><Row><ID_nummer>one</ID_nummer><Virksomhed>Synthetic</Virksomhed></Row></Root>"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.xml"
            source.write_bytes(raw)
            artifact = SourceArtifact("https://example.invalid/smiley.xml", "2026-09-15T00:00:00Z", hashlib.sha256(raw).hexdigest(), len(raw), code_version="test", config_version="test")
            first = run_private_lifecycle(source, root / "one", artifact, DenmarkSmileyAdapter())
            second = run_private_lifecycle(source, root / "two", artifact, DenmarkSmileyAdapter(), previous_normalized_path=Path(first["run_dir"]) / "normalized" / "records.jsonl")
            packet = json.loads((Path(second["run_dir"]) / "review-packet.json").read_text(encoding="utf-8"))
            self.assertEqual(packet["schema_version"], "private-review-packet-v1")
            self.assertTrue(packet["counts"]["reconciles"])
            self.assertTrue(packet["counts"]["qa_matches_manifest"])
            self.assertEqual(packet["release_diff"]["status"], "delta-ready")
            self.assertEqual(packet["release_diff"]["counts"]["not_observed"], 0)
            self.assertEqual(packet["gates"]["release_state"], "not-created")
            self.assertFalse(packet["gates"]["release_promoted"])
            self.assertNotIn("source_values", json.dumps(packet))


if __name__ == "__main__":
    unittest.main()
