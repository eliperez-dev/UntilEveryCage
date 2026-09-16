import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
IDS={"cy.vs.approved-food","cy.vs.farms-livestock","cy.environment-permits","cy.companies.registry","cy.cystat.livestock-meat","cy.vs.inspections-enforcement"}
class CyprusReconMetadataTests(unittest.TestCase):
 def test_row_free_scope(self):
  r=json.loads((ROOT/"pipeline/source_registry.json").read_text(encoding="utf-8-sig"));self.assertTrue(IDS.issubset({s["source_id"] for s in r["sources"]}));d=(ROOT/"docs/country-recon-cy.md").read_text(encoding="utf-8");self.assertIn("no facility rows",d.lower());self.assertIn("republic of cyprus",d.lower());self.assertIn("fully automated",d.lower())
 def test_blocked(self):
  s=json.loads((ROOT/"docs/source-status.json").read_text(encoding="utf-8-sig"));b={x["source_id"]:x for x in s["sources"]}
  for i in IDS:self.assertEqual(b[i]["publication_eligibility"],"blocked")
if __name__=="__main__":unittest.main()
