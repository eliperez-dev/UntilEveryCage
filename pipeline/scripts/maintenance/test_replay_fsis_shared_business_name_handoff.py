"""Focused field-retention tests for the FSIS graph replay."""
from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT = Path(__file__).with_name("replay-fsis-shared-business-name-handoff.py")
SPEC = importlib.util.spec_from_file_location("replay_fsis_graph_handoff", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPLAY)


class ReplayFsisSharedBusinessNameHandoffTests(unittest.TestCase):
    def test_replay_preserves_primary_name_and_aliases_without_other_normalized_fields(self):
        projected = REPLAY._replay_normalized({
            "canonical_name": "Synthetic Establishment Name",
            "facility_display_name": "Synthetic Display Name",
            "alternate_names": ["Synthetic DBA"],
            "dba_names": "Synthetic Trading Name",
            "address": "must not be copied",
            "phone": "must not be copied",
        }, "FS-001", datetime(2026, 1, 1, tzinfo=timezone.utc))

        self.assertEqual(projected, {
            "establishment_id": "FS-001",
            "canonical_name": "Synthetic Establishment Name",
            "facility_display_name": "Synthetic Display Name",
            "alternate_names": ["Synthetic DBA"],
            "dba_names": "Synthetic Trading Name",
            "observed_at": "2026-01-01T00:00:00Z",
        })


if __name__ == "__main__":
    unittest.main()
