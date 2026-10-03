from pathlib import Path
import unittest


class ActivationScopeTests(unittest.TestCase):
    def test_activation_targets_only_api_latest_snapshot_and_caps_at_24(self):
        source = Path(__file__).parents[1] / "scripts" / "stages" / "activate-au-geoapify-preview.py"
        code = source.read_text(encoding="utf-8")
        self.assertIn("candidate.snapshot_sha256=latest.snapshot_sha256", code)
        self.assertIn("if len(targets) != PILOT_SIZE", code)
        self.assertIn("PILOT_SIZE = 24", code)
        self.assertIn("source_preview_runs", code)
        self.assertIn("source_manifests", code)


if __name__ == "__main__":
    unittest.main()
