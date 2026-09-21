"""Regression checks preventing committed non-placeholder credentials."""

from __future__ import annotations

import re
import subprocess
import unittest
import importlib.util
import os
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
NAMED_SCRIPTS = (
    ROOT / "dirty-datasets/it/geocode_italy.py",
    ROOT / "dirty-datasets/it/geocode_italy_v2.py",
    ROOT / "dirty-datasets/it/geocode_italy_test.py",
)
ASSIGNMENT = re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b\s*[:=]\s*(['\"])([^'\"]+)\1")
PLACEHOLDER_MARKERS = ("example", "placeholder", "redacted", "dummy", "changeme", "your_", "replace_me", "test-token", "not-a-real")


def tracked_texts() -> list[tuple[str, str]]:
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True)
    paths = [Path(raw.decode()) for raw in result.stdout.split(b"\0") if raw]
    texts: list[tuple[str, str]] = []
    for relative in paths:
        path = ROOT / relative
        try:
            texts.append((relative.as_posix(), path.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            continue
    return texts


def embedded_non_placeholder_credentials() -> list[tuple[str, int]]:
    findings: list[tuple[str, int]] = []
    for filename, text in tracked_texts():
        for line_number, line in enumerate(text.splitlines(), 1):
            match = ASSIGNMENT.search(line)
            if not match:
                continue
            candidate = match.group(2).lower()
            if len(candidate) >= 12 and not any(marker in candidate for marker in PLACEHOLDER_MARKERS):
                findings.append((filename, line_number))
    return findings


class CredentialRemediationTests(unittest.TestCase):
    def test_named_geocodio_scripts_use_runtime_environment_only(self):
        assignment = re.compile(r"(?im)^\s*GEOCODIO_API_KEY\s*=")
        for path in NAMED_SCRIPTS:
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(assignment.search(text), path.as_posix())
            self.assertIn("os.environ.get(\"GEOCODIO_API_KEY\", \"\")", text)
            self.assertIn("get_geocodio_api_key()", text)

    def test_imports_are_network_free_and_missing_key_fails_clearly(self):
        for index, path in enumerate(NAMED_SCRIPTS):
            with self.subTest(path=path.name):
                spec = importlib.util.spec_from_file_location(f"credential_scan_target_{index}", path)
                module = importlib.util.module_from_spec(spec)
                with patch("urllib.request.urlopen", side_effect=AssertionError("network access during import")):
                    spec.loader.exec_module(module)
                with patch.dict(os.environ, {}, clear=True):
                    with self.assertRaisesRegex(RuntimeError, "GEOCODIO_API_KEY is required"):
                        module.get_geocodio_api_key()

    def test_tracked_files_have_no_obvious_non_placeholder_credentials(self):
        self.assertEqual(embedded_non_placeholder_credentials(), [])


if __name__ == "__main__":
    unittest.main()
