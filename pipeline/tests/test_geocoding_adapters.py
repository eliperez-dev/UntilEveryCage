import json
import socket
import urllib.error
import urllib.parse
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
from pipeline.geocoding import dawa as MODULE
from pipeline.geocoding import geoapify
from pipeline.geocoding.registry import get_adapter


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class DawaAdapterTests(unittest.TestCase):
    def test_registry_returns_provider_adapter(self):
        self.assertIsInstance(get_adapter("dawa"), MODULE.DawaAdapter)
        with self.assertRaises(ValueError):
            get_adapter("unknown-provider")
    @patch.object(MODULE.urllib.request, "urlopen")
    def test_single_match_is_accepted_and_uses_lon_lat_order(self, urlopen):
        urlopen.return_value = FakeResponse([{"id": "address-1", "x": 9.9, "y": 55.5}])
        result = MODULE.DawaAdapter().geocode("Testvej 1, 1000, København, Denmark")
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.acceptance, "accepted_single_point")
        self.assertEqual((result.latitude, result.longitude), (55.5, 9.9))
        self.assertEqual(result.provider_address_id, "address-1")

    @patch.object(MODULE.urllib.request, "urlopen")
    def test_multiple_matches_require_review(self, urlopen):
        urlopen.return_value = FakeResponse([{"x": 9.9, "y": 55.5}, {"x": 10.0, "y": 55.6}])
        result = MODULE.DawaAdapter().geocode("Testvej 1, 1000, København, Denmark")
        self.assertEqual(result.status, "review_required")
        self.assertIsNone(result.latitude)
        self.assertFalse(result.retryable)

    @patch.object(MODULE.urllib.request, "urlopen", side_effect=OSError("connection refused"))
    def test_transport_failure_is_retryable(self, _urlopen):
        result = MODULE.DawaAdapter().geocode("Testvej 1, 1000, København, Denmark")
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.retryable)
        self.assertEqual(result.response, {"error": "OSError"})


class GeoapifyAdapterTests(unittest.TestCase):
    QUERY = "10 Example Road, Melbourne, VIC 3000, Australia"

    @staticmethod
    def pilot_adapter(**kwargs):
        return geoapify.GeoapifyAdapter(country_code="au", pilot_auto_display=True, **kwargs)

    @staticmethod
    def gb_private_adapter(**kwargs):
        return geoapify.GeoapifyAdapter(country_code="gb", private_source_profile=True, **kwargs)

    @staticmethod
    def us_aphis_adapter(**kwargs):
        return geoapify.GeoapifyAdapter(country_code="us", private_source_profile=True, locality_only=True, **kwargs)

    def test_key_is_required(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GEOAPIFY_API_KEY"):
                geoapify.GeoapifyAdapter()

    def test_high_confidence_address_match_is_private_exact_candidate(self):
        payload = {"type": "FeatureCollection", "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [12.5, 55.6]},
            "properties": {"place_id": "candidate-1", "result_type": "building",
                           "country_code": "au", "address_line1": "10 Example Road",
                           "rank": {"confidence": 0.98}},
        }]}
        opener = unittest.mock.Mock(return_value=FakeResponse(payload))
        result = self.pilot_adapter(api_key="test-secret", opener=opener).geocode(self.QUERY)
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.acceptance, "high_confidence_address_match")
        self.assertEqual((result.latitude, result.longitude), (55.6, 12.5))
        self.assertEqual(result.provider_address_id, "candidate-1")
        self.assertNotIn("test-secret", json.dumps(result.response))
        request = opener.call_args.args[0]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        self.assertEqual(query["filter"], ["countrycode:au"])
        self.assertEqual(query["bias"], ["countrycode:none"])
        self.assertEqual(query["limit"], ["2"])

    def test_generic_geoapify_remains_unfiltered_and_review_gated(self):
        payload = {"features": [{
            "geometry": {"type": "Point", "coordinates": [12.5, 55.6]},
            "properties": {"place_id": "candidate", "result_type": "building"},
        }]}
        opener = unittest.mock.Mock(return_value=FakeResponse(payload))
        result = geoapify.GeoapifyAdapter(api_key="test-secret", opener=opener).geocode("Example address")
        self.assertEqual(result.status, "review_required")
        self.assertEqual(result.acceptance, "review_provider_candidate")
        self.assertEqual((result.latitude, result.longitude), (55.6, 12.5))
        query = urllib.parse.parse_qs(urllib.parse.urlparse(opener.call_args.args[0].full_url).query)
        self.assertNotIn("filter", query)
        self.assertNotIn("bias", query)

    def test_country_mismatch_and_address_mismatch_do_not_return_points(self):
        for country, address in (("nz", "10 Example Road"), ("au", "99 Other Street")):
            payload = {"features": [{
                "geometry": {"coordinates": [144.9, -37.8]},
                "properties": {"place_id": "candidate", "result_type": "building",
                               "country_code": country, "address_line1": address,
                               "rank": {"confidence": 0.99}},
            }]}
            result = self.pilot_adapter(
                api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse(payload))
            ).geocode(self.QUERY)
            self.assertEqual(result.status, "review_required")
            self.assertIsNone(result.latitude)
            self.assertIsNone(result.longitude)

    def test_low_confidence_and_ambiguous_results_do_not_return_points(self):
        feature = {"geometry": {"coordinates": [144.9, -37.8]}, "properties": {
            "result_type": "building", "country_code": "au",
            "address_line1": "10 Example Road", "rank": {"confidence": 0.89},
        }}
        for features in ([feature], [feature, feature]):
            payload = {"features": features}
            result = self.pilot_adapter(
                api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse(payload))
            ).geocode(self.QUERY)
            self.assertEqual(result.status, "review_required")
            self.assertIsNone(result.latitude)

    def test_private_source_profile_accepts_one_viable_match_among_weak_alternatives(self):
        good = {"geometry": {"type": "Point", "coordinates": [-2.5, 55.9]},
                "properties": {"place_id": "good", "result_type": "building", "country_code": "gb",
                               "address_line1": "10 Example Road", "rank": {"confidence": 0.96}}}
        weak = {"geometry": {"type": "Point", "coordinates": [-3, 56]},
                "properties": {"place_id": "weak", "result_type": "building", "country_code": "gb",
                               "address_line1": "Elsewhere Road", "rank": {"confidence": 0.80}}}
        query = "10 Example Road, Exampleton, AB1 2CD, United Kingdom"
        result = self.gb_private_adapter(
            api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse({"features": [good, weak]}))
        ).geocode(query)
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.provider_address_id, "good")
        self.assertEqual(result.response["_uec_selected_feature_index"], 0)

    def test_spain_private_profile_matches_accented_address_without_relaxing_number(self):
        adapter = geoapify.GeoapifyAdapter(
            api_key="test-secret", country_code="es", private_source_profile=True,
            allow_locality_match=False,
            opener=unittest.mock.Mock(return_value=FakeResponse({"features": [{
                "geometry": {"coordinates": [-3.7, 40.4]},
                "properties": {"place_id": "synthetic", "result_type": "building",
                               "country_code": "es", "address_line1": "10 Calle de la Constitución",
                               "rank": {"confidence": 0.95}},
            }]})),
        )
        result = adapter.geocode("10 Calle de la Constitucion, Madrid, España")
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.acceptance, "high_confidence_address_match")
        mismatch = adapter.geocode("11 Calle de la Constitucion, Madrid, España")
        self.assertEqual(mismatch.status, "review_required")
        self.assertIsNone(mismatch.latitude)

    def test_spain_verified_municipality_profile_accepts_only_exact_city_province_country_context(self):
        def feature(city="Albarracin", province="Teruel", country="es", kind="city", confidence=0.96):
            return {"geometry": {"type": "Point", "coordinates": [-1.4, 40.4]}, "properties": {
                "place_id": "synthetic-locality", "result_type": kind, "country_code": country,
                "city": city, "county": province, "state": "Aragon",
                "rank": {"confidence": confidence},
            }}

        query = "Albarracín, Teruel, Spain"
        def adapter(features):
            return geoapify.GeoapifyAdapter(
                api_key="test-secret", country_code="es", private_source_profile=True,
                locality_only=True, municipality_only=True,
                opener=unittest.mock.Mock(return_value=FakeResponse({"features": features})),
            )

        accepted = adapter([feature()]).geocode(query)
        self.assertEqual(accepted.status, "accepted")
        self.assertEqual(accepted.acceptance, "approximate_locality_match")
        self.assertEqual(accepted.precision, "geoapify_locality_point")

        cases = (
            ([feature(city="Teruel")], "wrong municipality"),
            ([feature(province="Zaragoza")], "wrong province"),
            ([feature(country="pt")], "wrong country"),
            ([feature(confidence=0.89)], "low confidence"),
            ([feature(kind="building")], "street-level result"),
            ([feature(), feature()], "ambiguous municipality"),
        )
        for features, reason in cases:
            with self.subTest(reason=reason):
                result = adapter(features).geocode(query)
                self.assertEqual(result.status, "review_required")
                self.assertIsNone(result.latitude)
                self.assertIsNone(result.longitude)
        wrong_country_context = adapter([feature()]).geocode("Albarracín, Teruel, France")
        self.assertEqual(wrong_country_context.status, "review_required")
        missing_province = adapter([feature()]).geocode("Albarracín, Spain")
        self.assertEqual(missing_province.status, "review_required")
        community_is_not_province = adapter([{
            **feature(), "properties": {key: value for key, value in feature()["properties"].items()
                                        if key != "county"},
        }]).geocode(query)
        self.assertEqual(community_is_not_province.status, "review_required")

    def test_spain_private_profile_rejects_wrong_country_wrong_address_ambiguity_and_low_confidence(self):
        def feature(country="es", address="10 Calle de la Constitución", confidence=0.96):
            return {"geometry": {"coordinates": [-3.7, 40.4]}, "properties": {
                "place_id": "synthetic", "result_type": "building", "country_code": country,
                "address_line1": address, "rank": {"confidence": confidence},
            }}

        query = "10 Calle de la Constitucion, Madrid, España"
        cases = (
            ([feature(country="pt")], "wrong country"),
            ([feature(address="11 Calle de la Constitución")], "different number"),
            ([feature(), feature()], "ambiguous viable results"),
            ([feature(confidence=0.89)], "low confidence"),
        )
        for features, reason in cases:
            with self.subTest(reason=reason):
                adapter = geoapify.GeoapifyAdapter(
                    api_key="test-secret", country_code="es", private_source_profile=True,
                    allow_locality_match=False,
                    opener=unittest.mock.Mock(return_value=FakeResponse({"features": features})),
                )
                result = adapter.geocode(query)
                self.assertEqual(result.status, "review_required")
                self.assertIsNone(result.latitude)
                self.assertIsNone(result.longitude)

    def test_spain_rejections_retain_only_redacted_private_candidate_diagnostics(self):
        def feature(country="es", address="11 Calle Real", confidence=0.96):
            return {"geometry": {"type": "Point", "coordinates": [-3.7, 40.4]}, "properties": {
                "country_code": country, "result_type": "building", "address_line1": address,
                "street": "Calle Real", "housenumber": "11", "county": "Synthetic Province",
                "postcode": "28001",
                "rank": {"confidence": confidence}, "name": "Synthetic Business", "place_id": "secret-id"}}

        def adapter(features):
            return geoapify.GeoapifyAdapter(
                api_key="test-secret", country_code="es", private_source_profile=True,
                allow_locality_match=False,
                opener=unittest.mock.Mock(return_value=FakeResponse({"features": features, "apiKey": "test-secret"})),
            )

        mismatch = adapter([feature()]).geocode("10 Calle Real, Madrid, 28001, España")
        self.assertEqual(mismatch.status, "review_required")
        self.assertEqual(mismatch.response["diagnostic_projection"], "private_es_rejected_candidate_properties")
        serialized = json.dumps(mismatch.response)
        self.assertNotIn("Synthetic Business", serialized)
        self.assertNotIn("secret-id", serialized)
        self.assertNotIn("test-secret", serialized)
        self.assertEqual(mismatch.response["features"][0]["properties"]["housenumber"], "11")
        self.assertEqual(mismatch.response["features"][0]["properties"]["county"], "Synthetic Province")
        self.assertEqual(mismatch.response["features"][0]["geometry"]["coordinates"], [-3.7, 40.4])

        ambiguous = adapter([feature("es", "10 Calle Real"), feature("es", "10 Calle Real")]).geocode(
            "10 Calle Real, Madrid, 28001, España")
        self.assertEqual(ambiguous.acceptance, "ambiguous_multiple_viable_results")
        self.assertEqual(len(ambiguous.response["features"]), 2)

        unresolved = adapter([]).geocode("10 Calle Real, Madrid, España")
        self.assertEqual(unresolved.status, "unresolved")
        self.assertEqual(unresolved.response["features"], [])
        self.assertNotIn("apiKey", json.dumps(unresolved.response))

    def test_non_spain_private_rejection_diagnostics_remain_unchanged(self):
        feature = {"geometry": {"coordinates": [-2.5, 55.9]}, "properties": {
            "country_code": "gb", "result_type": "building", "address_line1": "11 Other Road",
            "rank": {"confidence": 0.96}, "name": "Synthetic Business"}}
        result = self.gb_private_adapter(
            api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse({"features": [feature]}))
        ).geocode("10 Example Road, Exampleton, AB1 2CD, United Kingdom")
        self.assertEqual(result.status, "review_required")
        self.assertEqual(result.response, {"result_count": 1, "viable_result_count": 0})

    def test_private_source_profile_rejects_multiple_viable_or_wrong_country(self):
        base = {"geometry": {"type": "Point", "coordinates": [-2.5, 55.9]},
                "properties": {"result_type": "building", "country_code": "gb",
                               "address_line1": "10 Example Road", "rank": {"confidence": 0.96}}}
        query = "10 Example Road, Exampleton, AB1 2CD, United Kingdom"
        duplicate = json.loads(json.dumps(base))
        outcome = self.gb_private_adapter(
            api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse({"features": [base, duplicate]}))
        ).geocode(query)
        self.assertEqual(outcome.status, "review_required")
        self.assertEqual(outcome.acceptance, "ambiguous_multiple_viable_results")
        wrong_country = json.loads(json.dumps(base))
        wrong_country["properties"]["country_code"] = "ie"
        outcome = self.gb_private_adapter(
            api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse({"features": [wrong_country]}))
        ).geocode(query)
        self.assertEqual(outcome.status, "review_required")
        self.assertIsNone(outcome.latitude)

    def test_city_point_requires_country_and_query_locality_and_is_approximate(self):
        payload = {"features": [{
            "geometry": {"coordinates": [144.9, -37.8]},
            "properties": {"result_type": "city", "country_code": "au", "city": "Melbourne",
                           "rank": {"confidence": 0.94}},
        }]}
        result = self.pilot_adapter(
            api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse(payload))
        ).geocode("10 Example Road, Melbourne, Australia")
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.acceptance, "approximate_locality_match")
        self.assertEqual(result.precision, "geoapify_locality_point")

        payload["features"][0]["properties"]["city"] = "Sydney"
        mismatch = self.pilot_adapter(
            api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse(payload))
        ).geocode("10 Example Road, Melbourne, Australia")
        self.assertEqual(mismatch.status, "review_required")
        self.assertIsNone(mismatch.latitude)

    def test_aphis_locality_profile_requires_exact_city_state_country_and_rejects_buildings(self):
        query = "Exampletown, TX, United States"
        city = {"geometry": {"coordinates": [-97.7, 30.3]}, "properties": {
            "result_type": "city", "country_code": "us", "city": "Exampletown", "state_code": "TX",
            "rank": {"confidence": 0.95}}}
        accepted = self.us_aphis_adapter(api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse({"features": [city]}))).geocode(query)
        self.assertEqual(accepted.acceptance, "approximate_locality_match")
        building = json.loads(json.dumps(city)); building["properties"]["result_type"] = "building"; building["properties"]["address_line1"] = "Exampletown"
        rejected = self.us_aphis_adapter(api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse({"features": [building]}))).geocode(query)
        self.assertEqual(rejected.status, "review_required")
        wrong_state = json.loads(json.dumps(city)); wrong_state["properties"]["state_code"] = "CA"
        rejected = self.us_aphis_adapter(api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse({"features": [wrong_state]}))).geocode(query)
        self.assertEqual(rejected.status, "review_required")

    def test_invalid_coordinates_fail_closed(self):
        payload = {"features": [{"geometry": {"coordinates": [999, 55]}, "properties": {}}]}
        result = geoapify.GeoapifyAdapter(api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse(payload))).geocode("Example")
        self.assertEqual(result.status, "failed")
        self.assertFalse(result.retryable)
        self.assertEqual(result.response, {"error": "invalid_provider_coordinates"})

    @patch.object(MODULE.urllib.request, "urlopen")
    def test_malformed_payload_fails_closed(self, urlopen):
        urlopen.return_value = FakeResponse({"features": []})
        result = MODULE.DawaAdapter().geocode("Testvej 1, 1000, København, Denmark")
        self.assertEqual(result.status, "failed")
        self.assertFalse(result.retryable)
        self.assertEqual(result.response, {"error": "invalid_provider_schema"})

    @patch.object(MODULE.urllib.request, "urlopen")
    def test_invalid_coordinates_are_not_accepted(self, urlopen):
        urlopen.return_value = FakeResponse([{"id": "bad", "x": 181, "y": float("nan")}])
        result = MODULE.DawaAdapter().geocode("Testvej 1, 1000, København, Denmark")
        self.assertEqual(result.status, "unresolved")
        self.assertEqual(result.acceptance, "invalid_coordinates")

    @patch.object(MODULE.urllib.request, "urlopen")
    def test_http_retry_classification_is_bounded(self, urlopen):
        for status, retryable in ((401, False), (403, False), (429, True), (500, True), (503, True)):
            urlopen.side_effect = urllib.error.HTTPError("https://example.invalid", status, "failure", {}, None)
            result = MODULE.DawaAdapter().geocode("private query")
            self.assertEqual(result.response["status"], status)
            self.assertEqual(result.retryable, retryable)
            self.assertNotIn("private query", json.dumps(result.response))

    @patch.object(MODULE.urllib.request, "urlopen", side_effect=socket.timeout("timed out private query"))
    def test_timeout_is_retryable_and_redacted(self, _urlopen):
        result = MODULE.DawaAdapter().geocode("private query")
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.retryable)
        self.assertNotIn("private query", json.dumps(result.response))

    def test_registry_constructs_geoapify_from_environment(self):
        with patch.dict("os.environ", {"GEOAPIFY_API_KEY": "test-secret"}):
            self.assertIsInstance(get_adapter("geoapify"), geoapify.GeoapifyAdapter)


if __name__ == "__main__":
    unittest.main()
