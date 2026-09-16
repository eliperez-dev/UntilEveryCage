import json
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class BosniaReconMetadataTests(unittest.TestCase):
    def test_row_free_bosnia_recon_is_present(self):
        text=(ROOT/"docs"/"country-recon-ba.md").read_text(encoding="utf-8")
        self.assertIn("row-free",text); self.assertIn("fully automated",text); self.assertIn("state/entity/cantonal",text)
        self.assertIn("Recommended next country: North Macedonia",text)
    def test_bosnia_sources_have_conservative_status(self):
        registry=json.loads((ROOT/"pipeline"/"source_registry.json").read_text(encoding="utf-8")); status=json.loads((ROOT/"docs"/"source-status.json").read_text(encoding="utf-8"))
        ids={s["source_id"] for s in registry["sources"] if s["source_id"].startswith("ba.")}
        self.assertEqual(ids,{s["source_id"] for s in status["sources"] if s["source_id"].startswith("ba.")}); self.assertEqual(len(ids),6)
        for s in status["sources"]:
            if s["source_id"].startswith("ba."): self.assertEqual(s["publication_eligibility"],"blocked"); self.assertNotEqual(s["runtime_health"],"healthy")
if __name__ == "__main__": unittest.main()
