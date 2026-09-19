import json
import tempfile
import unittest
from pathlib import Path

from pipeline.scripts.maintenance.rehearse_real_v2 import build_rehearsal


class RealV2RehearsalTests(unittest.TestCase):
    def test_conversion_preserves_rows_privately_and_quarantines_missing_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root, output = Path(directory) / "static", Path(directory) / "run"
            country = root / "aa"
            country.mkdir(parents=True)
            (country / "locations.csv").write_text("establishment_id,establishment_name,city,latitude,longitude,slaughter\nA,Alpha,Town,52.1,4.2,true\n,Unknown,Town,52.2,4.3,true\n", encoding="utf-8")
            registry = Path(directory) / "registry.json"
            registry.write_text(json.dumps({"sources": [{"source_id": "aa.locations", "url": "https://example.test/aa"}]}), encoding="utf-8")
            import pipeline.scripts.maintenance.rehearse_real_v2 as module
            old = module.COUNTRIES
            module.COUNTRIES = ("aa",)
            try:
                report = build_rehearsal(root=root, output=output, registry_path=registry, max_records=10)
            finally:
                module.COUNTRIES = old
            self.assertEqual(report["totals"], {"input": 2, "normalized": 1, "quarantined": 1})
            self.assertEqual(json.loads((output / "aa" / "manifest.json").read_text())["publication_state"], "private-candidate")
            self.assertTrue((output / "aa" / "candidate-handoff" / "normalized" / "records.jsonl").is_file())
            self.assertTrue(report["strata"])
            self.assertNotIn("Alpha", (output / "rehearsal-report.json").read_text())

    def test_selection_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root, output = Path(directory) / "static", Path(directory) / "run"
            country = root / "aa"
            country.mkdir(parents=True)
            rows = "establishment_id,establishment_name,city\n" + "\n".join(f"{i},Name {i},Town" for i in range(12)) + "\n"
            (country / "locations.csv").write_text(rows, encoding="utf-8")
            registry = Path(directory) / "registry.json"
            registry.write_text(json.dumps({"sources": []}), encoding="utf-8")
            import pipeline.scripts.maintenance.rehearse_real_v2 as module
            old = module.COUNTRIES
            module.COUNTRIES = ("aa",)
            try:
                report = build_rehearsal(root=root, output=output, registry_path=registry, max_records=5)
            finally:
                module.COUNTRIES = old
            self.assertEqual(report["selection"]["selected_records"], 5)
            self.assertEqual(report["totals"]["input"], 5)


if __name__ == "__main__":
    unittest.main()
