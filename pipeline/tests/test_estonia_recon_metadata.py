import json
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
IDS={"ee.pta.approved-food","ee.pria.animal-register","ee.pria.aquaculture","ee.keskkonnaamet.kotkas","ee.ariregister.organizations","ee.stat.slaughter"}
class EstoniaReconMetadataTests(unittest.TestCase):
    def test_row_free_registered_sources(self):
        r=json.loads((ROOT/"pipeline/source_registry.json").read_text(encoding="utf-8")); self.assertTrue(IDS.issubset({s["source_id"] for s in r["sources"]}))
        d=(ROOT/"docs/country-recon-ee.md").read_text(encoding="utf-8"); self.assertIn("row-free",d); self.assertIn("fully automated",d); self.assertNotIn("Approval ID |",d)
    def test_status_conservative(self):
        s=json.loads((ROOT/"docs/source-status.json").read_text(encoding="utf-8")); by={x["source_id"]:x for x in s["sources"]}
        for i in IDS: self.assertEqual(by[i]["publication_eligibility"],"blocked")
if __name__ == "__main__": unittest.main()
