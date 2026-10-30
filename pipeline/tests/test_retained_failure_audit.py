import copy
import unittest
from unittest.mock import patch

from pipeline.geocoding.retained_failure_audit import diagnose
from pipeline.tests.test_locationiq_first_pass import candidate, query


class RetainedFailureAuditTests(unittest.TestCase):
    def test_offline_reasons_do_not_expose_addresses(self):
        base=candidate()
        variants=[([],"provider_returned_no_results"),
                  ([candidate(address={"road":"Calle Example"})],"provider_returned_no_numbered_road"),
                  ([candidate(address={**base["address"],"house_number":"5"})],"returned_street_or_number_differs"),
                  ([candidate(address={**base["address"],"city":"Wrong Town"})],"returned_locality_postcode_or_region_differs"),
                  ([base],"matches_current_rules"),
                  ([base,base],"multiple_matching_addresses")]
        with patch("urllib.request.urlopen",side_effect=AssertionError("network forbidden")):
            for payload,reason in variants:
                retained={"results":copy.deepcopy(payload)}
                result=diagnose(query("Calle Example 4"),retained,"es")
                self.assertEqual(result["reason"],reason)
                self.assertNotIn("Example",str(result))
                self.assertEqual(retained,{"results":payload})

    def test_invalid_query_and_missing_evidence_are_distinct(self):
        self.assertEqual(diagnose("invalid",{},"gb")["reason"],"invalid_stored_query")
        self.assertEqual(diagnose(query("Calle Example 4"),{},"es")["reason"],"response_evidence_not_retained")

    def test_uk_unnumbered_source_and_postcode_only_response_are_not_address_matches(self):
        q=query("Example Industrial Estate, Example Road",locality="London",postcode="SW1A 1AA",region=None,country="GB")
        result=diagnose(q,{"results":[candidate(lat="51.5",lon="-.1",address={"postcode":"SW1A 1AA","country_code":"gb"})]},"gb")
        self.assertEqual(result["reason"],"provider_returned_no_numbered_road")
        self.assertFalse(result["source_has_explicit_numbered_road"])
        self.assertTrue(result["query_has_postcode"])


if __name__=="__main__":unittest.main()
