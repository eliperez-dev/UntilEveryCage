"""First-pass input eligibility is independent from exact-match acceptance."""
import json
from pathlib import Path
import unittest

from pipeline.geocoding.first_pass import structured_query, normalize_query


class FirstPassInputTests(unittest.TestCase):
    def test_comma_in_single_site_nz_address_is_not_a_request_blocker(self):
        location = {"address":"Unit 2, 12 Example Road", "city":"Example Town",
                    "country_code":"NZ", "location_count":1, "number_of_locations":"1"}
        self.assertEqual(json.loads(structured_query("nz.locations",location))["address"],location["address"])
        for count in (0,2,True,"1"):
            self.assertIsNone(structured_query("nz.locations",{**location,"location_count":count}))

    def test_uk_street_without_number_and_postcode_without_town_can_be_queried(self):
        location = {"address_lines":["Example Industrial Estate", "Example Road"],
                    "postal_code":"SW1A 1AA", "country_code":"GB"}
        value=json.loads(structured_query("fss_approved_establishments",location))
        self.assertEqual(value["locality"],"")
        self.assertEqual(value["address"],"Example Industrial Estate, Example Road")
        self.assertIsNone(structured_query("fsa_approved_establishments",{**location,"address_lines":[]}))

    def test_spain_keeps_complete_source_address_and_verified_town(self):
        location={"address":"Example Industrial Estate, Calle Ejemplo 4", "region":"Madrid", "country_code":"ES"}
        value=json.loads(structured_query("es.locations",location,municipality="Example Town"))
        self.assertEqual(value["address"],location["address"])
        self.assertEqual(value["locality"],"Example Town")
        self.assertIsNone(structured_query("es.locations",{**location,"country_code":"GB"}))
        self.assertIsNone(structured_query("not-an-approved-source",location))

    def test_no_retry_and_local_database_guards_remain_in_planner(self):
        text=(Path(__file__).parents[1]/"geocoding/first_pass.py").read_text(encoding="utf-8")
        for snippet in ("uec.geocode_request_reservations", "attempted.source_record_key IS NULL",
                        "wrong_source_test_database", "provider_interval=1.05", "first_pass_only"):
            self.assertIn(snippet,text)
        self.assertEqual(normalize_query("  One  ROAD, Town  "),"one road, town")


if __name__=="__main__":
    unittest.main()
