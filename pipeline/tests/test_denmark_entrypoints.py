import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class DenmarkEntrypointTests(unittest.TestCase):
    def test_source_owned_entrypoint_is_canonical(self):
        canonical = ROOT / "sources/denmark/run-denmark-pipeline.py"
        self.assertIn("Source-owned entry point", canonical.read_text(encoding="utf-8"))

    def test_root_entrypoint_is_deprecated_compatibility_wrapper(self):
        legacy = ROOT / "run-denmark-pipeline.py"
        text = legacy.read_text(encoding="utf-8")
        self.assertIn("Deprecated compatibility shim", text)
        self.assertIn("one release", text)

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
