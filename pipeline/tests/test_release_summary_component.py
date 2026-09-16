"""Unit contracts for the manifest-bound summary component builder."""

import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "maintenance" / "build_release_summary_component.py"
SPEC = importlib.util.spec_from_file_location("build_release_summary_component", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class ReleaseSummaryComponentTests(unittest.TestCase):
    def test_content_digest_is_deterministic_and_content_bound(self):
        row = ("facility", "observation", "record", datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc), "slaughter")
        self.assertEqual(MODULE.content_digest([row]), MODULE.content_digest([row]))
        changed = (*row[:-1], "logistics_and_storage")
        self.assertNotEqual(MODULE.content_digest([row]), MODULE.content_digest([changed]))

    def test_naive_timestamps_are_rejected(self):
        row = ("facility", "observation", "record", datetime(2026, 1, 1), datetime(2026, 1, 2, tzinfo=timezone.utc), "slaughter")
        with self.assertRaises(MODULE.ComponentBlocked):
            MODULE.content_digest([row])

    def test_migration_is_append_only_and_candidate_view_is_live_gated(self):
        migration = (ROOT / "migrations" / "033_release_summary_component.sql").read_text(encoding="utf-8").lower()
        for token in ("manifest_sha256", "content_sha256", "release_summary_component_rows_append_only", "public_access_restricted", "publication_review_release_current", "manifest.manifest_sha256 = component_meta.manifest_sha256"):
            self.assertIn(token, migration)
        self.assertNotIn("drop table", migration)
        self.assertNotIn("drop view", migration)


if __name__ == "__main__":
    unittest.main()
