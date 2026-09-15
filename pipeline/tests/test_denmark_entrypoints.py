import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class DenmarkEntrypointTests(unittest.TestCase):
    def test_new_entrypoint_preserves_help_contract(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "sources/denmark/run-denmark-pipeline.py"), "--help"],
            cwd=ROOT.parent,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Denmark", result.stdout)

    def test_legacy_entrypoint_remains_available(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "run-denmark-pipeline.py"), "--help"],
            cwd=ROOT.parent,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Denmark", result.stdout)


if __name__ == "__main__":
    unittest.main()
