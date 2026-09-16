import tempfile, unittest
from pathlib import Path
import pipeline.graph_rehearsal as g

class GraphRehearsalTests(unittest.TestCase):
    def test_sampling_is_deterministic_and_private(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); paths = {}
            for key in g.STRATA:
                p = root / f"{key}.csv"; p.write_text("establishment_id,grant_date\n" + "\n".join(f"ID-{i},2026-01-01" for i in range(8)) + "\n"); paths[key] = p
            old = g.STRATA; g.STRATA = {k: 5 for k in paths}
            try: one, two = g.run(paths, root / "one"), g.run(paths, root / "two")
            finally: g.STRATA = old
            self.assertEqual(one["sample_size"], 15); self.assertEqual(one["candidate_relationships"], two["candidate_relationships"]); self.assertFalse(one["gates"]["auto_merge"])

if __name__ == "__main__": unittest.main()
