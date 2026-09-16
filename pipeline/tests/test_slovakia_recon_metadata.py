import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
IDS={"sk.svps.approved-food","sk.svps.farms-aquaculture","sk.svps.inspections-experiments","sk.environment.permits","sk.statistics-corporate"}
class SlovakiaReconMetadataTests(unittest.TestCase):
 def test_row_free_sources(self):
  r=json.loads((ROOT/"pipeline/source_registry.json").read_text(encoding="utf-8")); self.assertTrue(IDS.issubset({x["source_id"] for x in r["sources"]})); d=(ROOT/"docs/country-recon-sk.md").read_text(encoding="utf-8"); self.assertIn("row-free",d); self.assertIn("fully automated",d)
 def test_blocked_status(self):
  s=json.loads((ROOT/"docs/source-status.json").read_text(encoding="utf-8")); by={x["source_id"]:x for x in s["sources"]}
  for i in IDS: self.assertEqual(by[i]["publication_eligibility"],"blocked")
if __name__=="__main__": unittest.main()
