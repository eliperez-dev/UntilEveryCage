import json, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TURKEY_IDS={"tr.tarim.approved-food","tr.tarim.livestock-systems","tr.cevre.environment-permits","tr.mersis.organizations","tr.tuik.animal-statistics","tr.tarim.inspections-enforcement"}
class TurkeyReconMetadataTests(unittest.TestCase):
 def test_row_free_automated(self):
  r=json.loads((ROOT/"pipeline/source_registry.json").read_text(encoding="utf-8-sig")); self.assertTrue(TURKEY_IDS.issubset({s["source_id"] for s in r["sources"]})); d=(ROOT/"docs/country-recon-tr.md").read_text(encoding="utf-8"); self.assertIn("no facility rows",d.lower()); self.assertIn("fully automated",d.lower())
 def test_blocked(self):
  s=json.loads((ROOT/"docs/source-status.json").read_text(encoding="utf-8-sig")); b={x["source_id"]:x for x in s["sources"]}
  for i in TURKEY_IDS: self.assertEqual(b[i]["publication_eligibility"],"blocked")
if __name__=="__main__": unittest.main()
