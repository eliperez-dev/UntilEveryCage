"""Authenticated populated-database tests for both private graph APIs."""

import json
import os
import unittest
import urllib.error
import urllib.request

from .fixture import E2EEnvironment


@unittest.skipUnless(
    os.environ.get("UEC_RUN_E2E") == "1",
    "set UEC_RUN_E2E=1 to run Docker-backed E2E tests",
)
class PrivateGraphE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = E2EEnvironment().start()
        cls.env.seed_private_graph_scenario()
        cls.base = f"http://127.0.0.1:{cls.env.api_port}"
        cls.token = cls.env.private_graph_token
        cls.ids = cls.env.private_graph_ids

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    def request(self, path, token=None):
        headers = {}
        if token is not None:
            headers["X-UEC-Private-Graph-Token"] = token
        request = urllib.request.Request(self.base + path, headers=headers)
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())

    def assert_denied(self, path):
        for token in (None, "wrong-token"):
            request = urllib.request.Request(
                self.base + path,
                headers={} if token is None else {"X-UEC-Private-Graph-Token": token},
            )
            with self.subTest(path=path, token=token), self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request, timeout=10)
            self.assertEqual(error.exception.code, 404)

    def test_all_private_routes_fail_closed_without_valid_authentication(self):
        paths = [
            "/api/private/graph/entities",
            "/api/private/graph/search?q=Synthetic",
            f"/api/private/graph/entities/{self.ids['organization_a']}/neighborhood",
            "/api/private/graph/queues/statistics",
            "/api/private/graph/traverse?entity_type=organization&entity_id="
            f"{self.ids['organization_a']}",
        ]
        for path in paths:
            self.assert_denied(path)

    def test_populated_neighborhood_supports_both_directions_depth_two_and_numeric_confidence(self):
        path = (
            f"/api/private/graph/entities/{self.ids['organization_a']}/neighborhood"
            "?direction=both&depth=2&limit=100"
        )
        _, body = self.request(path, self.token)
        self.assertEqual(body["meta"]["direction"], "both")
        self.assertEqual(body["meta"]["depth"], 2)
        self.assertEqual(len(body["data"]), 5)
        relationships = {row["relationship_type"] for row in body["data"]}
        self.assertEqual(relationships, {"operator", "owner", "supplier", "parent", "customer"})
        self.assertIn(0.875, [row["confidence"] for row in body["data"]])
        self.assertIn(None, [row["confidence"] for row in body["data"]])
        self.assertTrue(all(row["storage_state"] == "private" for row in body["data"]))
        self.assertTrue(all(row["privacy_status"] == "suppressed" for row in body["data"]))
        self.assertTrue(all(row["publication_status"] == "not_eligible" for row in body["data"]))

    def test_entity_search_is_authenticated_bounded_and_deterministic(self):
        _, first = self.request("/api/private/graph/search?q=Synthetic%20graph&limit=100", self.token)
        _, second = self.request("/api/private/graph/search?q=Synthetic%20graph&limit=100", self.token)
        self.assertEqual(first["data"], second["data"])
        self.assertEqual(len(first["data"]), 5)
        self.assertTrue(all("note" not in row for row in first["data"]))

    def test_both_directions_are_applied_in_the_legacy_traverse_endpoint(self):
        path = (
            "/api/private/graph/traverse?entity_type=organization&"
            f"entity_id={self.ids['organization_a']}&direction=both&depth=2"
        )
        _, body = self.request(path, self.token)
        self.assertEqual(body["meta"]["direction"], "both")
        self.assertEqual(body["meta"]["depth"], 2)
        self.assertEqual(len(body["data"]), 5)
        self.assertNotIn("note", body["data"][0])
        self.assertIn(0.625, [row["confidence"] for row in body["data"]])

    def test_direction_filters_and_cycle_are_bounded(self):
        base = f"/api/private/graph/entities/{self.ids['organization_a']}/neighborhood"
        _, outgoing = self.request(base + "?direction=out&depth=2&limit=100", self.token)
        _, incoming = self.request(base + "?direction=in&depth=2&limit=100", self.token)
        self.assertEqual(len(outgoing["data"]), 4)
        self.assertEqual(len(incoming["data"]), 3)
        # A->B and B->A form a cycle; recursive traversal must still terminate.
        self.assertEqual(len({row["relationship_observation_id"] for row in outgoing["data"]}), 4)

    def test_queue_allowlist_uses_existing_schema_and_deterministic_limit(self):
        kinds = (
            "contradictions",
            "unresolved-identities",
            "quarantine",
            "claims",
            "rejected-candidates",
            "suppression",
            "statistics",
        )
        for kind in kinds:
            with self.subTest(kind=kind):
                _, first = self.request(f"/api/private/graph/queues/{kind}?limit=1", self.token)
                _, second = self.request(f"/api/private/graph/queues/{kind}?limit=1", self.token)
                self.assertEqual(first["meta"]["queue"], kind)
                self.assertLessEqual(len(first["data"]), 1)
                self.assertEqual(first["data"], second["data"])
        _, quarantine = self.request("/api/private/graph/queues/quarantine?limit=1", self.token)
        self.assertEqual(len(quarantine["data"]), 1)
        self.assertEqual(quarantine["data"][0][2], "rejected")


if __name__ == "__main__":
    unittest.main()
