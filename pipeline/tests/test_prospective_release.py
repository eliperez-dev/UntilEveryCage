from __future__ import annotations

import unittest
import importlib.util
from pathlib import Path

from pipeline.common import prospective_release as proposal

PREPARE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "maintenance" / "prepare-prospective-release-snapshot.py"
PREPARE_SPEC = importlib.util.spec_from_file_location("prepare_prospective_release_snapshot", PREPARE_SCRIPT)
prepare = importlib.util.module_from_spec(PREPARE_SPEC)
PREPARE_SPEC.loader.exec_module(prepare)


class _Result:
    def __init__(self, rows): self.rows = rows
    def fetchone(self): return self.rows[0]
    def fetchall(self): return self.rows


class _Connection:
    def execute(self, query, parameters=()):
        self.last = query
        if "encode(digest(string_agg(facility_id" in query:
            return _Result([(8, 5, 3, 6, "a" * 64, "c" * 64, "e" * 64)])
        if "GROUP BY source_id" in query:
            return _Result([("approved.source", 8, 5, 3, 6)])
        if "SELECT status,profile,test_only" in query:
            return _Result([("candidate", "official", False)])
        raise AssertionError(query[:100])


class ProspectiveReleaseTests(unittest.TestCase):
    def test_database_url_allows_only_existing_and_assigned_launch_loopback_copies(self):
        self.assertEqual(prepare._database_url("postgresql://127.0.0.1/uec_v0_api_repair"),
                         "postgresql://127.0.0.1/uec_v0_api_repair")
        self.assertEqual(prepare._database_url("postgresql://localhost/uec_launch_sources_test_20261025"),
                         "postgresql://localhost/uec_launch_sources_test_20261025")
        for value in ("postgresql://db.example/uec_launch_sources_test_20261025",
                      "postgresql://127.0.0.1/uec_v0_review_r3",
                      "postgresql://127.0.0.1/other"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                prepare._database_url(value)
        with self.assertRaisesRegex(ValueError, "frozen baseline must be"):
            prepare._frozen_database_url("postgresql://127.0.0.1/uec_launch_sources_test_20261025")

    def test_measure_is_row_free_and_binds_policy_and_stable_exclusions(self):
        result = proposal.measure(_Connection(), "d" * 64, "v0-candidate-test", ["a"], "b" * 64, ["approved.source"])
        self.assertEqual(result["publication_state"], "private_prospective_not_authorized")
        self.assertFalse("release_id" in result)
        self.assertEqual(result["inherited_exclusions"]["stable_facility_count"], 1)
        self.assertEqual(result["cohort"]["candidate_count"], 8)
        self.assertEqual(result["cohort"]["conditional_unmapped_count"], 2)
        self.assertEqual(result["cohort"]["geometry_evidence_sha256"], "e" * 64)
        self.assertEqual(result["selection_policy"]["exclude_source_ids"], ["fr.dgal.section-i", "fr.dgal.section-ii"])
        self.assertEqual(len(result["freeze_proposal_sha256"]), 64)

    def test_policy_uses_identity_not_a_count_subtraction(self):
        sql = proposal.selection_cte()
        self.assertIn("inherited.source_id=geometry.source_id", sql)
        self.assertIn("geometry.source_id <> ALL", sql)
        self.assertIn("geometry.classification_category='other_regulated_premises'", sql)
        self.assertIn("geometry.source_id='au.npi.facilities'", sql)
        self.assertIn("geometry.source_id='dk.smiley'", sql)
        self.assertNotIn("geometry.country_code='AU'", sql)
        self.assertNotIn("geometry.country_code='DK'", sql)


if __name__ == "__main__":
    unittest.main()
