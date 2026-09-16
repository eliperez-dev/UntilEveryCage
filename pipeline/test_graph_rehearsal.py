import tempfile, unittest
from pathlib import Path
import pipeline.graph_rehearsal as g

class GraphRehearsalTests(unittest.TestCase):
    def test_edges_require_explicit_source_keys_and_never_auto_merge(self):
        edge = g.candidate_relationship("x", {"operator_id": "O1", "facility_id": "F1"},
                                        subject_field="operator_id", object_field="facility_id",
                                        relationship_type="operator", method="explicit_source_keys",
                                        confidence="medium")
        self.assertEqual(edge["subject_source_native_id"], "O1")
        self.assertFalse(edge["auto_merge"])
        self.assertIsNone(g.candidate_relationship("x", {"name": "same", "distance": "0"},
                                                    subject_field="operator_id", object_field="facility_id",
                                                    relationship_type="operator", method="proximity",
                                                    confidence="low"))

    def test_sampling_is_deterministic_and_private(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); paths = {}
            for key in g.STRATA:
                p = root / f"{key}.csv"; p.write_text("establishment_id,grant_date\n" + "\n".join(f"ID-{i},2026-01-01" for i in range(8)) + "\n"); paths[key] = p
            old = g.STRATA; g.STRATA = {k: 5 for k in paths}
            try: one, two = g.run(paths, root / "one"), g.run(paths, root / "two")
            finally: g.STRATA = old
            self.assertEqual(one["sample_size"], 15); self.assertEqual(one["candidate_relationships"], two["candidate_relationships"]); self.assertFalse(one["gates"]["auto_merge"])
            self.assertIn("synthetic_controls", one)
            self.assertEqual(one["observed_candidates"]["accuracy"], "not measured; no adjudicated real labels available")

if __name__ == "__main__": unittest.main()
