"""Keep the public explorer on the implemented read-only API boundary."""

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
API = ROOT / "docs" / "api"
PUBLIC_PATHS = {
    "/api/v2/locations",
    "/api/v2/locations/{facility_id}",
    "/api/v2/locations.csv",
    "/api/v2/releases/manifest",
    "/api/v2/discovery/filters",
    "/api/v2/discovery/facets",
    "/api/v2/graph/connections",
    "/api/v2/graph/entities",
    "/api/v2/graph/entities/{entity_id}/neighborhood",
    "/api/v2/releases/{release_id}/map/tiles/{z}/{x}/{y}.mvt",
}


class PublicOpenApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((API / "public-openapi.json").read_text(encoding="utf-8"))
        cls.contract = json.loads((API / "v2-contract.json").read_text(encoding="utf-8"))
        cls.rust = (ROOT / "src" / "lib.rs").read_text(encoding="utf-8")
        cls.graph = (ROOT / "src" / "graph_public.rs").read_text(encoding="utf-8")
        cls.main = (ROOT / "src" / "main.rs").read_text(encoding="utf-8")

    def resolve(self, value):
        if "$ref" not in value:
            return value
        target = value["$ref"]
        if target == "./v2-location.schema.json":
            return json.loads((API / "v2-location.schema.json").read_text(encoding="utf-8"))
        self.assertTrue(target.startswith("#/"), target)
        resolved = self.spec
        for part in target[2:].split("/"):
            resolved = resolved[part.replace("~1", "/").replace("~0", "~")]
        return resolved

    def query_names(self, path):
        return {
            self.resolve(parameter)["name"]
            for parameter in self.spec["paths"][path]["get"]["parameters"]
            if self.resolve(parameter)["in"] == "query"
        }

    @staticmethod
    def handler(source, name):
        start = source.index("pub async fn " + name + "(")
        remaining = source[start:]
        end = re.search(r"\n(?:pub async fn |#\[derive|#\[cfg)", remaining)
        return remaining[:end.start()] if end else remaining

    @staticmethod
    def fields(source, name):
        block = re.search(r"pub struct " + name + r" \{(.*?)\n\}", source, re.S).group(1)
        return set(re.findall(r"^\s+(?:pub )?(\w+):", block, re.M))

    def test_exact_public_get_allowlist_matches_contract_and_registered_handlers(self):
        self.assertEqual(self.spec["openapi"], "3.1.0")
        self.assertEqual(self.spec["servers"], [{"url": "/", "description": "Same-origin backend"}])
        self.assertEqual(set(self.spec["paths"]), PUBLIC_PATHS)
        contract_paths = {key[4:] for key in self.contract["endpoints"] if key.startswith("GET /api/v2/")}
        self.assertEqual(set(self.spec["paths"]), contract_paths)
        registered = set(re.findall(r'\.route\(\s*"([^"]+)"\s*,\s*get\(', self.main))
        tile_template = "/api/v2/releases/{release_id}/map/tiles/{z}/{x}/{y}.mvt"
        for path, item in self.spec["paths"].items():
            self.assertEqual(set(item), {"get"}, path)
            registered_path = path.replace("/{z}/{x}/{y}.mvt", "/{*tile_path}") if path == tile_template else path
            self.assertIn(registered_path, registered)
            self.assertNotIn("requestBody", item["get"])
            self.assertNotIn("security", item["get"])
        self.assertNotIn("securitySchemes", self.spec["components"])
        self.assertNotIn("security", self.spec)

    def test_refs_operation_ids_and_path_parameters_are_resolvable(self):
        ids = []
        for path, item in self.spec["paths"].items():
            operation = item["get"]
            ids.append(operation["operationId"])
            parameters = [self.resolve(value) for value in operation["parameters"]]
            pairs = [(value["in"], value["name"]) for value in parameters]
            self.assertEqual(len(pairs), len(set(pairs)), path)
            expected = set(re.findall(r"\{([^}]+)\}", path))
            actual = {value["name"] for value in parameters if value["in"] == "path"}
            self.assertEqual(actual, expected)
            self.assertTrue(all(value["required"] for value in parameters if value["in"] == "path"))
            self.assertIn("200", operation["responses"])
            self.assertIn("429", operation["responses"])
        self.assertEqual(len(ids), len(set(ids)))

        def walk(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    self.resolve(value)
                self.assertNotIn("example", value)
                self.assertNotIn("examples", value)
                if value.get("type") == "object" and "properties" in value:
                    self.assertTrue(set(value.get("required", [])) <= set(value["properties"]))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(self.spec)

    def test_location_schema_reuses_checked_rust_dto(self):
        location = self.spec["components"]["schemas"]["Location"]
        self.assertEqual(location, {"$ref": "./v2-location.schema.json"})
        schema = self.resolve(location)
        rust_fields = self.fields(self.rust, "V2Location")
        self.assertEqual(set(schema["properties"]), rust_fields)
        self.assertEqual(set(schema["required"]), rust_fields)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["privacy_screening_status"], {"const": "passed"})

    def test_effective_location_and_facets_queries_follow_handlers(self):
        location_queries = self.query_names("/api/v2/locations")
        self.assertEqual(location_queries, self.fields(self.rust, "V2LocationParams"))
        body = self.handler(self.rust, "get_v2_locations_handler")
        self.assertTrue(location_queries <= set(re.findall(r"params\s*\.\s*(\w+)", body)))
        facets = self.handler(self.rust, "get_v2_facets_handler")
        applied = set(re.findall(r"params\s*\.\s*(\w+)", facets))
        self.assertEqual(self.query_names("/api/v2/discovery/facets"), applied)
        self.assertTrue({"q", "category_keys", "release_id", "limit", "radius_km"}.isdisjoint(applied))
        for path, name in [
            ("/api/v2/releases/manifest", "get_v2_release_manifest_handler"),
            ("/api/v2/locations.csv", "get_v2_locations_export_handler"),
        ]:
            used = set(re.findall(r"params\s*\.\s*(\w+)", self.handler(self.rust, name)))
            self.assertEqual(self.query_names(path), used)
            self.assertEqual(used, {"profile"})
        detail = self.handler(self.rust, "get_v2_location_detail_handler")
        self.assertEqual(self.query_names("/api/v2/locations/{facility_id}"), set(re.findall(r"params\s*\.\s*(\w+)", detail)))

    def test_graph_query_surface_follows_used_fields_without_fake_traversal(self):
        fields = self.fields(self.graph, "PublicGraphQuery")
        common = {"profile", "cursor", "limit"}
        connection_fields = common | {"connection_type", "min_confidence", "max_confidence", "confidence_band", "include_conflicting", "source_id", "entity_id"}
        self.assertEqual(self.query_names("/api/v2/graph/connections"), connection_fields)
        connections = self.handler(self.graph, "connections")
        used = set(re.findall(r"query\s*\.\s*(\w+)", connections))
        self.assertEqual(used | {"profile", "limit"}, connection_fields)
        entities = self.handler(self.graph, "entities")
        entity_fields = common | {"q", "entity_type"}
        self.assertEqual(self.query_names("/api/v2/graph/entities"), entity_fields)
        self.assertEqual(set(re.findall(r"query\s*\.\s*(\w+)", entities)) | {"profile", "q", "limit"}, entity_fields)
        adjacent = self.query_names("/api/v2/graph/entities/{entity_id}/neighborhood")
        self.assertEqual(adjacent, connection_fields - {"entity_id"})
        self.assertTrue(connection_fields | entity_fields <= fields)
        neighborhood = self.handler(self.graph, "neighborhood")
        self.assertIn("connections(State(state), Query(query))", neighborhood)
        self.assertTrue({"release_id", "direction", "depth"}.isdisjoint(adjacent))

    def test_caps_profile_defaults_and_error_gates_match_implementation(self):
        params = self.spec["components"]["parameters"]
        self.assertEqual(params["profile"]["schema"]["enum"], ["official", "secondary", "community"])
        self.assertEqual(params["profile"]["schema"]["default"], "official")
        self.assertIn("not project-approved", params["profile"]["description"])
        self.assertEqual(params["graphLimit"]["schema"], {"type": "integer", "minimum": 1, "maximum": 100, "default": 50})
        self.assertIn("const MAX_LIMIT: i64 = 100;", self.graph)
        self.assertIn("const DEFAULT_LIMIT: i64 = 50;", self.graph)
        self.assertIn("unwrap_or(100).clamp(1, 1000)", self.rust)
        self.assertIn("unwrap_or(0).clamp(0, 1_000_000)", self.rust)
        self.assertIn("rows.len() > 1000", self.handler(self.rust, "get_v2_locations_export_handler"))
        self.assertEqual(self.spec["components"]["schemas"]["FacetValues"]["maxItems"], 20)
        self.assertIn(".take(20)", self.handler(self.rust, "get_v2_facets_handler"))
        self.assertEqual(params["zPath"]["schema"]["maximum"], 14)
        self.assertIn("z > 14", self.handler(self.rust, "get_v2_map_tile_handler"))
        for path in ["/api/v2/locations", "/api/v2/locations/{facility_id}"]:
            responses = self.spec["paths"][path]["get"]["responses"]
            self.assertIn("410", responses)
            self.assertIn("500", responses)
        internal = self.spec["components"]["responses"]["Internal"]
        self.assertIn("text/plain", internal["content"])
        self.assertIn("No eligible unpinned release", self.spec["paths"]["/api/v2/locations"]["get"]["description"])
        for path in PUBLIC_PATHS - {"/api/v2/locations", "/api/v2/discovery/filters"}:
            self.assertIn("404", self.spec["paths"][path]["get"]["responses"])
        self.assertIn("does not announce a public release", self.spec["info"]["description"])

    def test_graph_dtos_match_published_fields(self):
        edge_body = self.graph[self.graph.index("fn public_edge("):self.graph.index("const EDGE_SELECT")]
        wire_fields = set(re.findall(r'^        "([a-z_]+)":', edge_body, re.M))
        edge_schema = self.spec["components"]["schemas"]["GraphEdge"]
        self.assertEqual(set(edge_schema["properties"]), wire_fields)
        self.assertEqual(set(edge_schema["required"]), wire_fields)
        entity_body = self.handler(self.graph, "entities")
        row = re.search(r'json!\(\{("entity_id".*?)\}\)', entity_body).group(1)
        entity_fields = set(re.findall(r'"([a-z_]+)":', row))
        entity_schema = self.spec["components"]["schemas"]["GraphEntity"]
        self.assertEqual(set(entity_schema["properties"]), entity_fields)
        self.assertEqual(set(entity_schema["required"]), entity_fields)


if __name__ == "__main__":
    unittest.main()
