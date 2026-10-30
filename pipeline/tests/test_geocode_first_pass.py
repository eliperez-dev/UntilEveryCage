"""First-pass input eligibility is independent from exact-match acceptance."""
import json
from pathlib import Path
import unittest

from pipeline.geocoding.first_pass import structured_query, normalize_query, provider_query, partition_groups, select_input_mode, validate_provider_interval, defer_explicit_no_number, reopen_local_input_rejections


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
                        "wrong_source_test_database", "first_pass_only"):
            self.assertIn(snippet,text)
        self.assertEqual(normalize_query("  One  ROAD, Town  "),"one road, town")

    def test_geoapify_formats_lookup_but_retains_full_source_address_and_verified_town(self):
        location={"address":"Unit 2, Calle Ejemplo 4", "region":"Madrid", "country_code":"ES"}
        group={"source":"es.locations", "query":structured_query("es.locations",location,municipality="Example Town")}
        original_query = group["query"]
        self.assertEqual(provider_query(group,"locationiq"),group["query"])
        self.assertEqual(provider_query(group,"geoapify"),group["query"])
        self.assertEqual(group["query"], original_query)
        self.assertEqual(json.loads(group["query"])["address"], location["address"])
        missing_town={"source":"es.locations","query":structured_query("es.locations",location)}
        with self.assertRaises(ValueError):
            provider_query(missing_town,"geoapify")
        for provider, source in (("other","es.locations"),("geoapify","nz.locations"),
                                 ("geoapify","es.cat.feed-sandach")):
            with self.subTest(provider=provider,source=source), self.assertRaises(ValueError):
                provider_query({**group,"source":source},provider)

    def test_three_provider_lanes_cover_queue_once_with_stable_identities(self):
        groups=[{"source":"es.locations","query":f"synthetic-query-{index}"} for index in range(300)]
        lanes=[partition_groups(groups,index,3) for index in range(3)]
        identities=[{g["query"] for g in lane} for lane in lanes]
        self.assertEqual(set.union(*identities),{g["query"] for g in groups})
        for index in range(3):
            self.assertGreater(len(lanes[index]),0)
            self.assertEqual(partition_groups(list(reversed(groups)),index,3),list(reversed(lanes[index])))
            for other in range(index):
                self.assertFalse(identities[index]&identities[other])

    def test_structured_input_selection_defers_complex_inputs_without_mutating_them(self):
        groups = [{"source": "es.locations", "query": structured_query("es.locations",
            {"address": address, "country_code": "ES", "region": "Madrid"}, municipality=town)}
            for address, town in (("Calle Example 4", "Town"), ("Calle Other 5", "Town"),
                                  ("Calle Example s/n", "Town"), ("Calle Example 4", ""))]
        original = list(groups)
        selected, deferred = select_input_mode(groups, "es_structured_numbered", 42)
        self.assertEqual(deferred, 2)
        self.assertEqual({g["query"] for g in selected}, {g["query"] for g in groups[:2]})
        self.assertEqual(groups, original)
        self.assertEqual(select_input_mode(groups)[0], groups)

    def test_provider_interval_rejects_excessive_or_nonfinite_rates(self):
        self.assertEqual(validate_provider_interval("geoapify", .25), .25)
        self.assertEqual(validate_provider_interval("locationiq", .55), .55)
        for provider in ("geoapify", "locationiq"):
            for interval in (.1, float("nan"), float("inf"), -1):
                with self.assertRaises(ValueError):
                    validate_provider_interval(provider, interval)

    def test_other_numbered_lane_is_disjoint_from_structured_and_deferred_inputs(self):
        groups = [{"source": "es.locations", "query": structured_query("es.locations",
            {"address": address, "country_code": "ES", "region": "Madrid"}, municipality="Town")}
            for address in ("Travesia Example 4", "Calle Example 4", "Calle Example 0",
                            "Poligono Example Parcela 4", "Carretera Example km 4", "Calle Example s/n")]
        selected, _ = select_input_mode(groups, "es_other_numbered")
        self.assertEqual(selected, groups[:1])

    def test_explicit_no_number_deferral_is_reversible_and_does_not_mutate_queue(self):
        groups = [{"source": "es.locations", "query": structured_query("es.locations",
            {"address": address, "country_code": "ES", "region": "Madrid"}, municipality="Town")}
            for address in ("Calle Example 4", "Calle Example s/n")]
        self.assertEqual(defer_explicit_no_number(groups), (groups[:1], 1))
        self.assertEqual(defer_explicit_no_number(groups, include_no_number=True), (groups, 0))
        self.assertEqual(len(groups), 2)

    def test_local_input_repair_rejects_other_databases_before_writing(self):
        class Connection:
            def execute(self, sql):
                if sql != "SELECT current_database()":
                    raise AssertionError("must not write")
                return self
            def fetchone(self): return ("different_database",)
        with self.assertRaisesRegex(ValueError, "wrong_source_test_database"):
            reopen_local_input_rejections(Connection())


if __name__=="__main__":
    unittest.main()
