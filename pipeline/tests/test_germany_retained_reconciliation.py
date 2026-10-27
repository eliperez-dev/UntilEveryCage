import unittest
import uuid
from unittest.mock import patch

from pipeline.geocoding.germany_retained_reconciliation import (
    MATCH_METHOD, RULESET, _context_matches, _result_id, reconcile, replay,
)


QUERY = "Musterstr. 12, 12345, Berlin, Berlin, Germany"


def result(**changes):
    value = {
        "place_id": 123, "lat": "52.5200", "lon": "13.4050", "class": "building",
        "type": "house", "addresstype": "building", "display_name": "must not persist",
        "address": {"house_number": "12", "road": "Musterstraße", "postcode": "12345",
                    "city": "Berlin", "state": "Berlin", "state_code": "BE", "country_code": "de"},
        "extra_secret": "must not persist",
    }
    value.update(changes)
    return value


class RetainedGermanyReconciliationTests(unittest.TestCase):
    def test_invalid_batch_limits_fail_before_opening_a_database(self):
        for limit in (None, True, 0, -1, 5001, 1.5, "24"):
            with self.subTest(limit=limit), patch(
                    "pipeline.geocoding.germany_retained_reconciliation.psycopg.connect") as connect:
                with self.assertRaisesRegex(ValueError, "finite_limit_required"):
                    reconcile("postgresql://synthetic", limit=limit)
                connect.assert_not_called()

    def test_replays_narrow_spelling_variant_without_preserving_unprojected_fields(self):
        replayed = replay(QUERY, {"results": [result()]})
        self.assertIsNotNone(replayed)
        self.assertEqual(replayed["_uec_selected_result_index"], 0)
        self.assertEqual(replayed["results"][0]["address"]["house_number"], "12")
        self.assertNotIn("display_name", str(replayed))
        self.assertNotIn("extra_secret", str(replayed))

    def test_wrong_components_or_non_street_variants_do_not_replay(self):
        for field, value in (("house_number", "13"), ("postcode", "54321"),
                             ("city", "Potsdam"), ("state", "Bayern"),
                             ("country_code", "at"), ("road", "Musterweg")):
            item = result()
            item["address"][field] = value
            with self.subTest(field=field):
                self.assertIsNone(replay(QUERY, {"results": [item]}))

    def test_ambiguous_retained_results_are_not_replayed(self):
        self.assertIsNone(replay(QUERY, {"results": [result(), result(place_id=456)]}))

    def test_invalid_response_and_source_context_are_rejected(self):
        for response in (None, {}, {"results": []}, {"results": [result()] * 3}):
            self.assertIsNone(replay(QUERY, response))
        self.assertTrue(_context_matches(QUERY, "Musterstr. 12", "12345", "Berlin", "Berlin"))
        self.assertFalse(_context_matches(QUERY, "Musterstraße 13", "12345", "Berlin", "Berlin"))

    def test_ruleset_and_result_identity_are_versioned_and_stable(self):
        self.assertEqual(RULESET, "german-street-spelling-v1")
        self.assertEqual(MATCH_METHOD, "locationiq_retained_street_v1")
        parent = uuid.UUID("0f974caf-f7db-4a87-8c1d-643f62455d6e")
        self.assertEqual(_result_id(parent), _result_id(parent))
        self.assertNotEqual(_result_id(parent), parent)


if __name__ == "__main__":
    unittest.main()
