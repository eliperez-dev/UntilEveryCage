import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.contracts.adapter_contract import SourceArtifact

from .handoff import write_private_monthly_handoff


MONTHLY = (
    "AppNo,TradingName,Country,CompetentAuthority,X,Y,AddressWithheld,All_Activities,Address1,Town,Postcode\n"
    "A-1,House Foods,England,Food Standards Agency,-0.12,51.50,No,CP,House Farm,London,SW1\n"
    "A-2,Withheld,Wales,Food Standards Agency,-3.18,51.48,Yes,CP,Private Road,Cardiff,CF1\n"
    "A-3,Out of scope,Jersey,Food Standards Agency,-2.10,49.20,No,CP,Island Road,St Helier,JE1\n"
).encode("cp1252")


class FsaHandoffTests(unittest.TestCase):
    def artifact(self, raw: bytes) -> SourceArtifact:
        return SourceArtifact(
            source_url="https://example.invalid/fsa-monthly.csv",
            retrieved_at_utc="2026-09-14T00:00:00Z",
            sha256=hashlib.sha256(raw).hexdigest(),
            byte_size=len(raw),
            code_version="test",
            config_version="test",
            coverage="England and Wales",
        )

    def test_monthly_rows_use_private_handoff_without_clearance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.csv"
            source.write_bytes(MONTHLY)
            manifest = write_private_monthly_handoff(source, root / "run", self.artifact(MONTHLY))
            self.assertEqual(manifest["contract_version"], "candidate-handoff-v1")
            self.assertEqual(manifest["profile"], "fsa-approved-monthly")
            self.assertEqual(manifest["source_id"], "fsa_approved_establishments")
            self.assertEqual(manifest["normalized_rows"], 2)
            self.assertEqual(manifest["release_state"], "not-created")
            self.assertEqual(manifest["privacy_gate"], "pending")
            self.assertEqual(manifest["coordinate_gate"], "review_required")
            row = json.loads((root / "run/normalized/records.jsonl").read_text().splitlines()[0])
            self.assertEqual(row["source_row"], 2)
            self.assertEqual(row["normalized"]["establishment_id"], "A-1")
            self.assertEqual(row["source_values"]["X"], "-0.12")
            self.assertIsNone(row["normalized"]["coordinates"])
            self.assertEqual(row["normalized"]["privacy_gate"], "privacy-review-required")
            self.assertEqual(row["normalized"]["coordinate_gate"], "privacy-review-required")
            self.assertEqual(manifest["qa"]["quarantined_rows"], 1)
            self.assertEqual(manifest["qa"]["anomaly_counts"]["unknown_nation"], 1)

    def test_source_mismatch_fails_before_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.csv"
            source.write_bytes(MONTHLY)
            bad = SourceArtifact("https://example.invalid", "2026-09-14T00:00:00Z", "0" * 64, len(MONTHLY))
            with self.assertRaisesRegex(ValueError, "checksum"):
                write_private_monthly_handoff(source, root / "run", bad)
            self.assertFalse((root / "run/manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
