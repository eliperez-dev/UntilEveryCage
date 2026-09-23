import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .refresh import RefreshError, refresh


ROOT = Path(__file__).parent


class BelgiumRefreshTests(unittest.TestCase):
    def test_row_free_acquisition_sidecars_are_verified_and_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            operators = ROOT / "fixtures" / "synthetic_operators.csv"
            codes = ROOT / "fixtures" / "synthetic_activity_codes.csv"
            operator_meta = root / "operator-metadata.json"
            code_meta = root / "code-metadata.json"
            operator_meta.write_text(json.dumps({"sha256": hashlib.sha256(operators.read_bytes()).hexdigest(), "byte_size": operators.stat().st_size, "final_url": "https://example.invalid/current-operators.csv", "effective_date": "2026-09-14"}), encoding="utf-8")
            code_meta.write_text(json.dumps({"sha256": hashlib.sha256(codes.read_bytes()).hexdigest(), "byte_size": codes.stat().st_size, "final_url": "https://example.invalid/current-codes.csv", "effective_date": "2026-09-14"}), encoding="utf-8")
            metadata = root / "pair.json"
            metadata.write_text(json.dumps({"operator_path": str(operator_meta), "activity_codes_path": str(code_meta)}), encoding="utf-8")
            result = refresh(run_dir=root / "run", operators_path=operators, activity_codes_path=codes, acquisition_metadata_path=metadata, retrieved_at_utc="2026-09-14T00:00:00Z")
            self.assertEqual(result["report"]["publication_eligibility"], "blocked")
            saved = json.loads((root / "run" / "acquisition-metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["operator"]["final_url"], "https://example.invalid/current-operators.csv")

    def test_assisted_pair_is_repeatable_and_keeps_artifacts_private(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = {"operators_path": ROOT / "fixtures" / "synthetic_operators.csv", "activity_codes_path": ROOT / "fixtures" / "synthetic_activity_codes.csv", "retrieved_at_utc": "2026-09-14T00:00:00Z"}
            first = refresh(run_dir=root / "one", **args)
            second = refresh(run_dir=root / "two", **args)
            self.assertEqual(first["report"]["operator_sha256"], second["report"]["operator_sha256"])
            self.assertEqual(first["report"]["activity_code_sha256"], second["report"]["activity_code_sha256"])
            self.assertEqual(first["report"]["normalized_rows"], 3)
            self.assertEqual(first["report"]["publication_eligibility"], "blocked")
            self.assertFalse(any((root / "one" / "lifecycle").glob("*/released/records.jsonl")))

    def test_partial_assisted_pair_fails_closed(self):
        with self.assertRaises(RefreshError):
            refresh(run_dir=Path(tempfile.mkdtemp()), operators_path=ROOT / "fixtures" / "synthetic_operators.csv")

    def test_acquisition_contract_fetches_both_official_artifacts_with_bounds(self):
        from . import acquire

        calls = []
        def fake_fetch_source(**kwargs):
            calls.append(kwargs)
            path = Path(kwargs["output_root"]) / kwargs["source_id"] / "run" / kwargs["artifact_name"]
            return {"artifact_path": str(path), "sha256": "a" * 64, "byte_size": 1, "run_id": "run"}

        with tempfile.TemporaryDirectory() as directory:
            review = Path(directory) / "review.json"
            review.write_text(json.dumps({"reviewer":"operator", "reference":"approval", "reviewed_at":"2026-09-23T18:34:37Z", "decision":"approved", "notes":"private processing only"}), encoding="utf-8")
            with patch.object(acquire, "fetch_source", side_effect=fake_fetch_source):
                pair = acquire.fetch_pair(output_root=Path(directory) / "private", terms_review_path=review, run_id="test-run", timeout_seconds=25, max_bytes=1000, max_attempts=2)
        self.assertEqual([call["source_id"] for call in calls], ["be.locations", "be.activity-codes"])
        self.assertEqual([call["url"] for call in calls], [acquire.CONFIG["operator_url"], acquire.CONFIG["activity_code_url"]])
        self.assertTrue(all(call["max_attempts"] == 2 and call["timeout_seconds"] == 25 and call["max_bytes"] == 1000 for call in calls))
        self.assertEqual(pair["operator"]["run_id"], pair["activity_codes"]["run_id"])


if __name__ == "__main__":
    unittest.main()
