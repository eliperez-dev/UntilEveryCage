"""Keep Rust, the canonical schema, and the JS validator in lockstep."""
import json, re, unittest
from pathlib import Path
ROOT = Path(__file__).parents[2]
class V2ContractDriftTests(unittest.TestCase):
    def test_location_fields_match_all_contract_surfaces(self):
        rust = (ROOT / "src/lib.rs").read_text(encoding="utf-8")
        block = re.search(r"pub struct V2Location \{(.*?)\n\}", rust, re.S).group(1)
        rust_fields = set(re.findall(r"pub (\w+):", block))
        schema = json.loads((ROOT / "docs/api/v2-location.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(rust_fields, set(schema["properties"]))
        js = (ROOT / "static/modules/v2Contract.js").read_text(encoding="utf-8")
        required = set(re.findall(r"'([a-z_]+)'", re.search(r"for \(const field of \[(.*?)\]\)", js, re.S).group(1)))
        required |= {"canonical_name", "city", "reviewer_role", "publication_warning", "latitude", "longitude", "first_observed_at", "last_observed_at", "observation_count", "provenance_source"}
        self.assertEqual(rust_fields, required)
