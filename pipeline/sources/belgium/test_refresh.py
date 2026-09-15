import tempfile
import unittest
from pathlib import Path

from .refresh import RefreshError, refresh


ROOT = Path(__file__).parent


class BelgiumRefreshTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
