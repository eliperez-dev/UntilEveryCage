from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "maintenance" / "repair-france-scope-candidate.py"
SPEC = importlib.util.spec_from_file_location("repair_france_scope_candidate", SCRIPT)
repair = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repair)


class FranceScopeCandidateRepairTests(unittest.TestCase):
    def test_target_is_exact_candidate_and_loopback_database(self):
        self.assertEqual(repair.TARGET_DATABASE, "uec_country_release_test_20261027")
        self.assertEqual(repair.TARGET_RELEASE, "release-2026-10-27")
        self.assertEqual(repair.SUCCESSOR_RELEASE, "release-2026-10-27-r2")
        self.assertEqual(repair.EXPECTED_AFFECTED_MEMBERS, 20)
        repair._validate_dsn("postgresql://user:secret@127.0.0.1/uec_country_release_test_20261027")
        for dsn in (
            "postgresql://user:secret@example.invalid/uec_country_release_test_20261027",
            "postgresql://user:secret@127.0.0.1/other_database",
            "postgresql://user:secret@127.0.0.1/uec_country_release_test_20261027?host=remote.invalid",
        ):
            with self.subTest(dsn=dsn), self.assertRaisesRegex(repair.RepairError, "repair_database_not_allowlisted"):
                repair._validate_dsn(dsn)

    def test_expected_targets_are_only_representative_france_out_of_scope_points(self):
        representatives = {}
        for index in range(20):
            normalized = {"coordinates": {"latitude": 46 + index / 100,
                                           "longitude": 3 + index / 100,
                                           "jurisdiction_extent": "outside-configured-france-extents"},
                          "in_default_map_scope": False}
            representatives[f"group-{index}"] = ((f"native-{index}",), {"normalized": normalized})
        representatives["in-scope"] = (("native-inside",), {"normalized": {
            "coordinates": {"latitude": 46.0, "longitude": 3.0,
                            "jurisdiction_extent": "metropolitan-france"},
            "in_default_map_scope": True}})
        for index in range(24):
            representatives[f"unmapped-{index}"] = ((f"native-unmapped-{index}",), {"normalized": {
                "coordinates": None, "in_default_map_scope": False}})
        targets = repair._expected_targets({"representatives": representatives})
        self.assertEqual(len(targets), 20)
        self.assertEqual(targets[("native-0", "group-0")], (46.0, 3.0))
        self.assertNotIn(("native-inside", "in-scope"), targets)
        with self.assertRaisesRegex(repair.RepairError, "frozen_france_scope_target_count_mismatch"):
            repair._expected_targets({"representatives": {"one": representatives["group-0"]}})

    def test_freeze_release_binding_is_exact_and_does_not_mutate_input(self):
        original = {"release_id": repair.FROZEN_INPUT_RELEASE, "selected_sources": []}
        bound = repair._bind_candidate_release(original)
        self.assertEqual(bound["release_id"], repair.TARGET_RELEASE)
        self.assertEqual(original["release_id"], repair.FROZEN_INPUT_RELEASE)
        with self.assertRaisesRegex(repair.RepairError, "repair_freeze_release_not_allowlisted"):
            repair._bind_candidate_release({"release_id": repair.TARGET_RELEASE})

    def test_repair_report_counts_each_member_once(self):
        dry = repair._repair_summary(apply=False, release_id=repair.SUCCESSOR_RELEASE, already_corrected=0,
                                     corrected_this_run=0, remaining_bad=20)
        self.assertEqual((dry["total_corrected"], dry["corrected_this_run"], dry["remaining_bad_members"]),
                         (0, 0, 20))
        applied = repair._repair_summary(apply=True, release_id=repair.SUCCESSOR_RELEASE, already_corrected=0,
                                         corrected_this_run=20, remaining_bad=0)
        self.assertEqual((applied["total_corrected"], applied["corrected_this_run"],
                          applied["remaining_bad_members"]), (20, 20, 0))
        rerun = repair._repair_summary(apply=True, release_id=repair.SUCCESSOR_RELEASE, already_corrected=20,
                                       corrected_this_run=0, remaining_bad=0)
        self.assertEqual((rerun["total_corrected"], rerun["corrected_this_run"]), (20, 0))
        verified_successor = repair._repair_summary(apply=False, release_id=repair.SUCCESSOR_RELEASE,
                                                    already_corrected=20, corrected_this_run=0,
                                                    remaining_bad=0)
        self.assertEqual(verified_successor["total_corrected"], 20)
        self.assertEqual(verified_successor["status"], "dry_run")

    def test_corrected_lineage_contract_is_append_only_and_targets_member_binding_only(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("FROM uec.release_cohort_review_documents WHERE release_id=%s", source)
        self.assertNotIn("UPDATE uec.release_members SET observation_id", source)
        self.assertIn("coordinate_scope_correction", source)
        self.assertIn("coordinate_scope_projection", source)
        self.assertIn("INSERT INTO uec.observation_taxonomy_assignment_sets", source)
        self.assertIn("INSERT INTO uec.observation_taxonomy_assignments", source)
        self.assertIn("corrected_taxonomy_set_conflict", source)
        self.assertIn('"v0-candidate-bridge:" + TARGET_RELEASE', source)
        self.assertIn("lock_candidate=apply", source)
        self.assertIn("INSERT INTO uec.release_members(release_id,facility_id,observation_id,default_visible)", source)
        self.assertIn("supersedes_release_id", source)
        self.assertIn("successor_release_membership_conflict", source)
        self.assertIn("successor_release_already_reviewed_or_manifested", source)
        self.assertIn('"release-2026-10-27-r2"', source)
        self.assertNotIn("UPDATE uec.release_members", source)
        self.assertNotIn("UPDATE uec.observations", source)
        self.assertNotIn("UPDATE uec.source_records", source)
        self.assertNotIn("UPDATE uec.observation_taxonomy", source)
        self.assertNotIn("UPDATE uec.facilities", source)

    def test_cli_defaults_to_dry_run_and_requires_explicit_apply(self):
        with patch.object(repair, "repair", return_value={"status": "dry_run"}) as run:
            with patch("sys.stdout"):
                self.assertEqual(repair.main([
                    "--database-url", "postgresql://127.0.0.1/uec_country_release_test_20261027",
                    "--freeze", "freeze.json", "--inventory", "inventory.json",
                ]), 0)
        self.assertFalse(run.call_args.kwargs["apply"])


if __name__ == "__main__":
    unittest.main()
