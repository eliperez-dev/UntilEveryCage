import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from .refresh import RefreshError, refresh


ROOT = Path(__file__).parent


class GermanyRefreshTests(unittest.TestCase):
    def test_row_free_acquisition_sidecar_is_verified_and_preserved(self):
        raw = ROOT.parent.parent / "germany" / "fixtures" / "synthetic_bltu.csv"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "capture.json"
            metadata.write_text(json.dumps({"sha256": hashlib.sha256(raw.read_bytes()).hexdigest(), "byte_size": raw.stat().st_size, "final_url": "https://example.invalid/current-bltu.csv", "effective_date": "2026-09-14"}), encoding="utf-8")
            result = refresh(run_dir=root / "run", raw_path=raw, acquisition_metadata_path=metadata, retrieved_at_utc="2026-09-14T00:00:00Z")
            self.assertEqual(result["report"]["publication_eligibility"], "blocked")
            saved = json.loads((root / "run" / "acquisition-metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["final_url"], "https://example.invalid/current-bltu.csv")

    def test_assisted_refresh_is_private_and_repeatable(self):
        raw = ROOT.parent.parent / "germany" / "fixtures" / "synthetic_bltu.csv"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = refresh(run_dir=root / "one", raw_path=raw, retrieved_at_utc="2026-09-14T00:00:00Z")
            second = refresh(run_dir=root / "two", raw_path=raw, retrieved_at_utc="2026-09-14T00:00:00Z")
            self.assertEqual(first["report"]["sha256"], second["report"]["sha256"])
            self.assertEqual(first["report"]["normalized_rows"], 1)
            self.assertEqual(first["report"]["publication_eligibility"], "blocked")
            self.assertFalse(any((root / "one" / "lifecycle").glob("*/released/records.jsonl")))

    def test_network_mode_requires_explicit_portal_export_url_and_terms_review(self):
        with self.assertRaises(RefreshError):
            refresh(run_dir=Path(tempfile.mkdtemp()), fetch=True)
        with self.assertRaises(RefreshError):
            refresh(run_dir=Path(tempfile.mkdtemp()), fetch=True, export_url="https://example.invalid/export.csv", terms_review_path=ROOT / "README.md")


if __name__ == "__main__":
    unittest.main()
