"""Unit contracts for the public discovery read model builder and migration."""

import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "maintenance" / "build_public_discovery_read_model.py"
SPEC = importlib.util.spec_from_file_location("build_public_discovery_read_model", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class PublicDiscoveryReadModelTests(unittest.TestCase):
    def test_content_digest_is_deterministic_and_binds_public_projection_fields(self):
        row = ("facility", "observation", "record", "Name", "DK", None, "City", "POINT (10 55)", "exact", "label", "accepted", "provider", datetime(2026, 1, 1, tzinfo=timezone.utc), "slaughter", datetime(2026, 1, 2, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc), "official", "source", "Source", "https://example.invalid", datetime(2026, 1, 1, tzinfo=timezone.utc), "unknown")
        self.assertEqual(MODULE.content_digest([row]), MODULE.content_digest([row]))
        self.assertNotEqual(MODULE.content_digest([row]), MODULE.content_digest([(*row[:-1], "attribution_required")]))

    def test_naive_timestamps_are_rejected(self):
        row = ("facility", "observation", "record", "Name", "DK", None, "City", None, "unmapped", "label", None, None, None, "slaughter", datetime(2026, 1, 2), datetime(2026, 1, 2, tzinfo=timezone.utc), "official", "source", "Source", "https://example.invalid", datetime(2026, 1, 1, tzinfo=timezone.utc), "unknown")
        with self.assertRaises(MODULE.ReadModelBlocked):
            MODULE.content_digest([row])

    def test_migration_is_atomic_manifest_bound_and_live_gated(self):
        migration = (ROOT / "migrations" / "037_public_discovery_read_model.sql").read_text(encoding="utf-8").lower()
        for token in ("public_discovery_read_models", "public_discovery_read_model_rows", "content_sha256", "append_only", "release_manifests", "publication_review_release_current", "public_access_restricted", "facility_lifecycle_current"):
            self.assertIn(token, migration)
        self.assertNotIn("drop table", migration)

    def test_operator_query_never_selects_raw_fields(self):
        query = MODULE.SELECT_ROWS.lower()
        self.assertNotIn("raw_fields", query)
        self.assertIn("map_facilities_display_history", query)


if __name__ == "__main__":
    unittest.main()
