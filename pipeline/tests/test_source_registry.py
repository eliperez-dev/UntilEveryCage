import json
import tempfile
import unittest
from pathlib import Path

from pipeline.source_registry import REGISTRY_PATH, SourceRegistryError, load_registry, validate_registry


class SourceRegistryTests(unittest.TestCase):
    def test_repository_registry_loads_and_references_existing_legacy_paths(self):
        registry = load_registry()
        self.assertEqual(len(registry["sources"]), 209)
        self.assertEqual(len({source["source_id"] for source in registry["sources"]}), 209)

    def test_unknowns_are_explicit(self):
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(registry["unknown_value"], "unknown")
        self.assertIn("unknown", {source["url"] for source in registry["sources"]})

    def test_allows_source_without_legacy_paths(self):
        registry = load_registry()
        belgium = next(source for source in registry["sources"] if source["source_id"] == "be.locations")
        self.assertEqual(belgium["legacy_paths"], [])

    def test_rejects_duplicate_ids(self):
        registry = load_registry()
        registry["sources"].append(dict(registry["sources"][0]))
        with self.assertRaises(SourceRegistryError):
            validate_registry(registry)

    def test_rejects_invalid_url(self):
        registry = load_registry()
        registry["sources"][0]["url"] = "javascript:alert(1)"
        with self.assertRaises(SourceRegistryError):
            validate_registry(registry)

    def test_rejects_non_string_scalar_fields_with_source_registry_error(self):
        scalar_fields = [
            "source_id", "jurisdiction_scope", "url", "access_method", "cadence",
            "attribution_licensing_notes", "adapter_status", "expected_artifact_schema",
        ]
        for field in scalar_fields:
            with self.subTest(field=field):
                registry = load_registry()
                registry["sources"][0][field] = None
                with self.assertRaises(SourceRegistryError):
                    validate_registry(registry)

    def test_rejects_non_string_url_before_parsing(self):
        for malformed_url in (None, 7, [], {}):
            with self.subTest(malformed_url=malformed_url):
                registry = load_registry()
                registry["sources"][0]["url"] = malformed_url
                with self.assertRaises(SourceRegistryError):
                    validate_registry(registry)

    def test_rejects_malformed_lists_and_path_items_before_filesystem_use(self):
        for malformed_paths in (None, "static_data/ca/locations.csv", [None], [7], [""]):
            with self.subTest(malformed_paths=malformed_paths):
                registry = load_registry()
                registry["sources"][0]["legacy_paths"] = malformed_paths
                with self.assertRaises(SourceRegistryError):
                    validate_registry(registry, repository_root=Path.cwd())
        for malformed_blockers in (None, "blocker", [None], [7], [""]):
            with self.subTest(malformed_blockers=malformed_blockers):
                registry = load_registry()
                registry["sources"][0]["blockers"] = malformed_blockers
                with self.assertRaises(SourceRegistryError):
                    validate_registry(registry)

    def test_rejects_path_that_escapes_repository(self):
        registry = load_registry()
        registry["sources"][0]["legacy_paths"] = ["../outside.csv"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repository"
            root.mkdir()
            with self.assertRaises(SourceRegistryError):
                validate_registry(registry, repository_root=root)

    def test_load_registry_wraps_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(SourceRegistryError):
                load_registry(path)

    def test_rejects_missing_legacy_path(self):
        registry = load_registry()
        registry["sources"][0]["legacy_paths"] = ["does-not-exist.csv"]
        with self.assertRaises(SourceRegistryError):
            validate_registry(registry, repository_root=Path.cwd())


if __name__ == "__main__":
    unittest.main()
