"""Keep generated D2 fixture-run history out of source control."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class D2RunnerGitignoreTests(unittest.TestCase):
    def test_generated_runner_history_is_ignored(self):
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--", "pipeline/common/.d2-runner/refresh-example/manifest.json"],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, ".d2-runner generated artifacts must stay ignored")


if __name__ == "__main__":
    unittest.main()
