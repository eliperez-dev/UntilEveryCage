import json
import tempfile
import unittest
from pathlib import Path

from .refresh import RefreshError, refresh_monthly


MONTHLY = (
    "AppNo,TradingName,Country,CompetentAuthority,X,Y,AddressWithheld,All_Activities,Address1,Town,Postcode\n"
    "A-1,House Foods,England,Food Standards Agency,-0.12,51.50,No,CP,House Farm,London,SW1\n"
    "A-2,Withheld,Wales,Food Standards Agency,-3.18,51.48,Yes,CP,Private Road,Cardiff,CF1\n"
).encode("cp1252")


class FsaRefreshTests(unittest.TestCase):
    def test_dry_run_emits_provenance_drift_and_not_observed_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "source.csv"
            raw.write_bytes(MONTHLY)
            previous = root / "previous.jsonl"
            previous.write_text(
                json.dumps({"normalized": {"establishment_id": "A-1"}}) + "\n"
                + json.dumps({"normalized": {"establishment_id": "A-2"}}) + "\n"
                + json.dumps({"normalized": {"establishment_id": "A-9"}}) + "\n",
                encoding="utf-8",
            )
            result = refresh_monthly(
                raw_path=raw,
                run_dir=root / "run",
                retrieved_at_utc="2026-09-14T00:00:00Z",
                effective_date="2026-09-01",
                mode="dry-run",
                previous_normalized=previous,
                bounded_sample=True,
            )
            report = result["report"]
            self.assertEqual(report["sha256"], __import__("hashlib").sha256(MONTHLY).hexdigest())
            self.assertEqual(report["input_rows"], 2)
            self.assertEqual(report["disappeared_not_observed_count"], 1)
            self.assertIn("not-observed", report["disappearance_semantics"])
            self.assertEqual(report["mode"], "dry-run")
            self.assertFalse((root / "run/handoff/manifest.json").exists())
            self.assertTrue((root / "run/refresh.json").exists())

    def test_handoff_writes_private_contract_for_bounded_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "source.csv"
            raw.write_bytes(MONTHLY)
            result = refresh_monthly(
                raw_path=raw,
                run_dir=root / "run",
                retrieved_at_utc="2026-09-14T00:00:00Z",
                effective_date="2026-09-01",
                mode="handoff",
                bounded_sample=True,
            )
            self.assertEqual(result["handoff"]["contract_version"], "candidate-handoff-v1")
            self.assertEqual(result["handoff"]["release_state"], "not-created")
            self.assertEqual(result["report"]["publication_state"], "private-candidate")

    def test_schema_drift_blocks_unbounded_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "source.csv"
            raw.write_bytes(MONTHLY)
            with self.assertRaisesRegex(RefreshError, "drift alarm"):
                refresh_monthly(raw_path=raw, run_dir=root / "run", mode="handoff")
            self.assertFalse((root / "run/handoff/manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
