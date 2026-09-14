import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "restriction_ledger_gate",
    Path(__file__).parents[1] / "scripts" / "maintenance" / "restriction-ledger-gate.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RestrictionLedgerGateTests(unittest.TestCase):
    def setUp(self):
        self.ledger = {"schema_version": 1, "revision": "r2", "active_restrictions": [
            {"source_id": "synthetic", "source_record_key": "private", "scope": "whole_record"}
        ]}
        self.snapshot = {"ledger_revision": "r2", "active_restrictions": list(self.ledger["active_restrictions"])}

    def test_current_restrictions_must_match_before_service(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.json"
            ledger_path.write_text(json.dumps(self.ledger), encoding="utf-8")
            MODULE.pre_service_gate(ledger_path, self.snapshot)
            with self.assertRaises(MODULE.RestrictionLedgerError):
                MODULE.pre_service_gate(ledger_path, {"ledger_revision": "r1", "active_restrictions": []})

    def test_old_restore_cannot_start_without_current_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.json"
            ledger_path.write_text(json.dumps(self.ledger), encoding="utf-8")
            old_restore = {"ledger_revision": "r1", "active_restrictions": []}
            with self.assertRaises(MODULE.RestrictionLedgerError):
                MODULE.pre_service_gate(ledger_path, old_restore)

    def test_missing_or_invalid_ledger_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            with self.assertRaises(MODULE.RestrictionLedgerError):
                MODULE.load_ledger(path)
            path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
            with self.assertRaises(MODULE.RestrictionLedgerError):
                MODULE.load_ledger(path)

    def test_crosswalk_maps_only_unique_identifiers(self):
        result = MODULE.verify_v1_v2_crosswalk([
            {"v1_id": "one", "v2_id": "A"},
            {"v1_id": "two", "v2_id": "B"},
            {"v1_id": "two", "v2_id": "C"},
        ])
        self.assertEqual(result["mapped"], {"one": "A"})
        self.assertEqual(result["unresolved"], [{"v1_id": "two", "reason": "ambiguous_mapping"}])


if __name__ == "__main__":
    unittest.main()
