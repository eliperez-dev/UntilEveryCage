import json
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from . import launchpad as launchpad_module
except ImportError:  # direct `python scripts/test_launchpad.py`
    import launchpad as launchpad_module

LaunchpadError = launchpad_module.LaunchpadError
LaunchpadPaths = launchpad_module.LaunchpadPaths
_owned_frontend = launchpad_module._owned_frontend
select_dataset = launchpad_module.select_dataset


class DatasetSelectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(__file__).resolve().parents[1] / "target" / "test-launchpad-fixtures"
        shutil.rmtree(self.directory, ignore_errors=True)
        self.directory.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_fallback_is_explicitly_row_free_and_does_not_scan(self):
        result = select_dataset(self.directory, {})
        self.assertEqual(result.mode, "sanitized-fallback")
        self.assertEqual(result.release_id, "standard-candidate")
        self.assertEqual(result.summary["records"], 1)
        self.assertIsNone(result.manifest_path)

    def test_private_mode_requires_explicit_manifest(self):
        with self.assertRaises(LaunchpadError):
            select_dataset(self.directory, {"UEC_DEV_DATASET_MODE": "private"})

    def test_private_mode_rejects_malformed_manifest(self):
        path = self.directory / "manifest.json"
        path.write_text("not json", encoding="utf-8")
        with self.assertRaises(LaunchpadError):
            select_dataset(self.directory, {"UEC_DEV_DATASET_MODE": "private", "UEC_DEV_DATASET_MANIFEST": str(path)})

    def test_private_mode_accepts_aggregate_manifest(self):
        path = self.directory / "manifest.json"
        path.write_text(json.dumps({"mode": "private", "ready": True, "release_id": "dev-2026", "row_free_summary": {"records": 123, "mapped_exact": 2}}), encoding="utf-8")
        result = select_dataset(self.directory, {"UEC_DEV_DATASET_MODE": "private", "UEC_DEV_DATASET_MANIFEST": str(path)})
        self.assertEqual(result.mode, "private")
        self.assertEqual(result.summary, {"records": 123, "mapped_exact": 2})


class OwnershipTests(unittest.TestCase):
    def test_frontend_ownership_requires_root_vite_and_port_marker(self):
        directory = Path(__file__).resolve().parents[1] / "target" / "test-launchpad-owner"
        directory.mkdir(parents=True, exist_ok=True)
        paths = LaunchpadPaths(directory)
        with patch.object(launchpad_module, "process_command", return_value=f"node {directory} frontend node_modules/vite 4173"):
            self.assertTrue(_owned_frontend(paths, 123))
        with patch.object(launchpad_module, "process_command", return_value="node unrelated vite 4173"):
            self.assertFalse(_owned_frontend(paths, 123))


if __name__ == "__main__":
    unittest.main()
