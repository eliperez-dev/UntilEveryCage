"""Synthetic checks for the standalone public release acceptance helper."""

import importlib.util
import unittest
from pathlib import Path


HELPER_PATH = Path(__file__).parent / "e2e" / "test_country_release_acceptance.py"
SPEC = importlib.util.spec_from_file_location("country_release_acceptance", HELPER_PATH)
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


class FakeApi:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, route, params=None):
        params = params or {}
        self.calls.append((route, params))
        key = (route, params.get("q"), params.get("cursor"))
        response = self.responses.get(key)
        if response is None:
            response = self.responses.get((route, None, None))
        if response is None:
            raise AssertionError("unexpected synthetic route")
        return response, {}


class CountryReleaseAcceptanceTests(unittest.TestCase):
    def test_public_list_map_and_flat_detail_shapes(self):
        release = "country-r1"
        source = "mx.locations"
        facility_id = "00000000-0000-0000-0000-000000000001"
        responses = {
            ("/api/v2/locations", None, None): {
                "data": [{"facility_id": facility_id}],
                "meta": {"release_id": release, "total_count": 1, "next_cursor": None},
            },
            ("/api/v2/map/matches", None, None): {
                "data": {"facility_ids": [facility_id]},
                "meta": {"release_id": release, "manifest_sha256": "a" * 64,
                         "total_count": 1, "mapped_count": 1},
            },
            ("/api/v2/locations/" + facility_id, None, None): {
                "data": {"facility_id": facility_id, "canonical_name": "synthetic sample",
                         "provenance_source_id": source, "provenance_source_name": "synthetic",
                         "provenance_source_url": "https://example.invalid/source",
                         "provenance_retrieved_at": "2026-10-27T00:00:00Z",
                         "taxonomy_primary_categories": ["slaughter"]},
                "meta": {"release_id": release},
            },
            ("/api/v2/locations", "synthetic sample", None): {
                "data": [{"facility_id": facility_id, "provenance_source_id": source}],
                "meta": {"release_id": release, "total_count": 1},
            },
            ("/api/v2/locations", None, None): {
                "data": [{"facility_id": facility_id}], "meta": {"total_count": 1},
            },
        }
        api = FakeApi(responses)
        contract = {"release_id": release, "profile": "official", "manifest_sha256": "a" * 64,
                    "sources": {source: {"total_count": 1, "mapped_count": 1}}}
        acceptance._check_sources(api, contract)
        self.assertEqual(len(api.calls), 4)
        self.assertEqual(api.calls[1][0], "/api/v2/map/matches")

        # An unnamed member is still searchable by its public source name.
        responses[("/api/v2/locations/" + facility_id, None, None)]["data"].update(
            canonical_name=None, city=None,
        )
        responses[("/api/v2/locations", "synthetic", None)] = responses[
            ("/api/v2/locations", "synthetic sample", None)
        ]
        unnamed_api = FakeApi(responses)
        acceptance._check_sources(unnamed_api, contract)
        self.assertEqual(unnamed_api.calls[-1][1]["q"], "synthetic")

    def test_graph_actual_array_page_shape_is_bounded_and_filtered(self):
        release = "country-r1"
        source = "mx.locations"
        edge = {"from": {"source_id": source,
                          "entity_id": "00000000-0000-0000-0000-000000000001"},
                "to": {"source_id": "us.aphis",
                        "entity_id": "00000000-0000-0000-0000-000000000002"}}
        route = "/api/v2/graph/connections"
        responses = {
            (route, None, None): {"data": [edge], "meta": {
                "release_id": release, "ruleset_version": "ruleset-r1",
                "next_cursor": "00000000-0000-0000-0000-000000000003"}},
            (route, None, "00000000-0000-0000-0000-000000000003"): {"data": [edge], "meta": {
                "release_id": release, "ruleset_version": "ruleset-r1",
                "next_cursor": "00000000-0000-0000-0000-000000000004"}},
        }
        api = FakeApi(responses)
        contract = {"profile": "official", "graph_preservation": [{
            "release_id": release, "source_id": source, "ruleset_version": "ruleset-r1",
            "minimum_sample_edges": 2,
        }]}
        acceptance._check_graph(api, contract)
        self.assertEqual(len(api.calls), 2)

    def test_rejects_non_loopback_and_map_over_cap(self):
        with self.assertRaises(acceptance.AcceptanceFailure):
            acceptance.validate_origin("https://example.com")
        contract = {"release_id": "r1", "profile": "official", "manifest_sha256": "a" * 64,
                    "sources": {"mx.locations": {"total_count": 80_000, "mapped_count": 75_001}}}
        with self.assertRaises(acceptance.AcceptanceFailure):
            acceptance.validate_contract(contract)


if __name__ == "__main__":
    unittest.main()
