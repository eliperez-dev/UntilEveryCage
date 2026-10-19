from __future__ import annotations

import unittest

from pipeline.common import prospective_release as proposal


class _Result:
    def __init__(self, rows): self.rows = rows
    def fetchone(self): return self.rows[0]
    def fetchall(self): return self.rows


class _Connection:
    def execute(self, query, parameters=()):
        self.last = query
        if "encode(digest(string_agg(facility_id" in query:
            return _Result([(8, 5, 3, 6, "a" * 64, "c" * 64)])
        if "GROUP BY source_id" in query:
            return _Result([("approved.source", 8, 5, 3)])
        if "SELECT status,profile,test_only" in query:
            return _Result([("candidate", "official", False)])
        raise AssertionError(query[:100])


class ProspectiveReleaseTests(unittest.TestCase):
    def test_measure_is_row_free_and_binds_policy_and_stable_exclusions(self):
        result = proposal.measure(_Connection(), "d" * 64, "v0-candidate-test", ["a"], "b" * 64)
        self.assertEqual(result["publication_state"], "private_prospective_not_authorized")
        self.assertFalse("release_id" in result)
        self.assertEqual(result["inherited_exclusions"]["stable_facility_count"], 1)
        self.assertEqual(result["cohort"]["candidate_count"], 8)
        self.assertEqual(result["selection_policy"]["exclude_country_codes"], ["FR"])
        self.assertEqual(len(result["freeze_proposal_sha256"]), 64)

    def test_policy_uses_identity_not_a_count_subtraction(self):
        sql = proposal.selection_cte()
        self.assertIn("geometry.facility_id = ANY", sql)
        self.assertIn("geometry.country_code IS DISTINCT FROM 'FR'", sql)
        self.assertIn("geometry.classification_category='other_regulated_premises'", sql)


if __name__ == "__main__":
    unittest.main()
