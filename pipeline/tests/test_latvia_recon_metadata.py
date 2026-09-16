import json, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
IDS={"lv.pvd.approved-food","lv.ldc.slaughter-farms","lv.environment.permits","lv.stat.api","lv.animal-experiments","lv.ur.organizations"}
class LatviaReconMetadataTests(unittest.TestCase):
 def test_row_free_sources(self):
  r=json.loads((ROOT/"pipeline/source_registry.json").read_text()); self.assertTrue(IDS.issubset({x["source_id"] for x in r["sources"]})); d=(ROOT/"docs/country-recon-lv.md").read_text(); self.assertIn("row-free",d); self.assertIn("fully automated",d); self.assertNotIn("Approval ID |",d)
 def test_blocked_status(self):
  s=json.loads((ROOT/"docs/source-status.json").read_text()); by={x["source_id"]:x for x in s["sources"]}
  for i in IDS: self.assertEqual(by[i]["publication_eligibility"],"blocked")
if __name__=="__main__": unittest.main()
