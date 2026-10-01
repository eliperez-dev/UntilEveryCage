"""Deterministic and precision-safe public MVT hierarchy contracts."""

import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "maintenance" / "build_public_map_artifacts.py"
SPEC = importlib.util.spec_from_file_location("build_public_map_artifacts", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)
PROMOTE_SPEC = importlib.util.spec_from_file_location("promote_release_map_artifacts", ROOT / "scripts" / "stages" / "promote-release.py")
PROMOTE = importlib.util.module_from_spec(PROMOTE_SPEC)
assert PROMOTE_SPEC.loader
PROMOTE_SPEC.loader.exec_module(PROMOTE)


class PublicMapArtifactTests(unittest.TestCase):
    def test_exact_and_coarse_features_cluster_separately_with_expansion_zoom(self):
        facilities = [
            {"record_id": "exact-a", "longitude": 0.01, "latitude": 0.01, "kind": "exact", "category_key": "farm"},
            {"record_id": "exact-b", "longitude": 0.02, "latitude": 0.02, "kind": "exact", "category_key": "farm"},
            {"record_id": "coarse-a", "longitude": 0.03, "latitude": 0.03, "kind": "coarse", "category_key": "farm"},
            {"record_id": "coarse-b", "longitude": 0.04, "latitude": 0.04, "kind": "coarse", "category_key": "farm"},
        ]
        tiles = MODULE.hierarchy_features("release-a", "official", facilities, max_zoom=1)
        low_zoom = [feature for (zoom, _, _), features in tiles.items() if zoom == 0 for feature in features]
        self.assertEqual(len(low_zoom), 2)
        exact_cluster = next(feature for feature in low_zoom if feature["exact_count"])
        coarse_cluster = next(feature for feature in low_zoom if feature["coarse_count"])
        self.assertEqual((exact_cluster["kind"], exact_cluster["count"], exact_cluster["exact_count"], exact_cluster["coarse_count"], exact_cluster["next_zoom"]), ("cluster", 2, 2, 0, 1))
        self.assertEqual((coarse_cluster["kind"], coarse_cluster["count"], coarse_cluster["exact_count"], coarse_cluster["coarse_count"], coarse_cluster["next_zoom"]), ("cluster", 2, 0, 2, 1))
        self.assertNotEqual(exact_cluster["feature_key"], coarse_cluster["feature_key"])
        self.assertIsNone(exact_cluster["record_id"])
        self.assertIsNone(coarse_cluster["record_id"])
        self.assertIsNone(exact_cluster["category_key"])
        self.assertIsNone(exact_cluster["category_keys_compact"])
        self.assertIsNone(coarse_cluster["category_key"])
        self.assertIsNone(coarse_cluster["category_keys_compact"])
        self.assertEqual(exact_cluster["count"], 2)  # category toggles never imply a filtered aggregate count

    def test_exact_leaf_resolves_record_and_coarse_leaf_never_does(self):
        facilities = [
            {"record_id": "exact-id", "longitude": -100, "latitude": 40, "kind": "exact", "category_key": "farm"},
            {"record_id": "coarse-id", "longitude": 100, "latitude": -40, "kind": "coarse", "category_key": "farm"},
        ]
        tiles = MODULE.hierarchy_features("release-a", "official", facilities, max_zoom=0)
        leaves = [feature for features in tiles.values() for feature in features]
        exact = next(feature for feature in leaves if feature["kind"] == "exact")
        coarse = next(feature for feature in leaves if feature["kind"] == "coarse")
        self.assertEqual(exact["record_id"], "exact-id")
        self.assertIsNone(coarse["record_id"])
        self.assertEqual(coarse["coarse_count"], 1)
        self.assertIsNone(coarse["category_key"])
        self.assertIsNone(coarse["category_keys_compact"])

    def test_zero_zero_is_not_a_usable_public_map_coordinate(self):
        with self.assertRaisesRegex(ValueError, "unusable zero coordinate"):
            MODULE._point("POINT (0 0)")

    def test_coincident_exact_records_remain_distinct_at_max_zoom(self):
        facilities = [
            {"record_id": "exact-a", "longitude": 12, "latitude": 55, "kind": "exact", "category_key": "farm"},
            {"record_id": "exact-b", "longitude": 12, "latitude": 55, "kind": "exact", "category_key": "farm"},
        ]
        tiles = MODULE.hierarchy_features("release-a", "official", facilities, max_zoom=0)
        leaves = [feature for features in tiles.values() for feature in features]
        self.assertEqual({feature["record_id"] for feature in leaves}, {"exact-a", "exact-b"})
        self.assertTrue(all(feature["count"] == 1 and feature["kind"] == "exact" for feature in leaves))

    def test_feature_keys_are_stable_and_profile_scoped(self):
        key = MODULE._feature_key("release-a", "official", 4, 3, 9, "exact")
        self.assertEqual(key, MODULE._feature_key("release-a", "official", 4, 3, 9, "exact"))
        self.assertNotEqual(key, MODULE._feature_key("release-a", "secondary", 4, 3, 9, "exact"))
        self.assertNotEqual(key, MODULE._feature_key("release-b", "official", 4, 3, 9, "exact"))

    def test_tile_builder_drops_unmapped_and_selects_only_allowlisted_properties(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('point is None or row[8] == "unmapped"', source)
        compact_source = "".join(source.split())
        self.assertIn("SELECTfeature_key,kind,count,exact_count,coarse_count,next_zoom,", compact_source)
        self.assertIn("record_id,category_key,category_keys_compact,geom", compact_source)
        for forbidden in ("canonical_name", "street_address", "source_url", "evidence", "token"):
            self.assertNotIn(f'"{forbidden}"', source)
        self.assertNotIn("real_preview", source)
        self.assertIn('release[0] != "validated" or release[1]', source)

    def test_compact_category_keys_are_sorted_bounded_and_reject_unknowns(self):
        compact = MODULE.compact_category_keys(["slaughter", "processing_and_preparation", "slaughter", "not_a_key"])
        self.assertEqual(compact, "|processing_and_preparation|slaughter|")
        self.assertTrue(MODULE.compact_category_keys_match(compact, "slaughter"))
        self.assertFalse(MODULE.compact_category_keys_match(compact, "aughter"))
        self.assertEqual(MODULE.compact_category_keys(None), "|unclassified|")

    def test_promotion_rejects_stale_or_corrupt_private_tile_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tile = root / "0" / "0" / "0.mvt"
            tile.parent.mkdir(parents=True)
            tile.write_bytes(b"synthetic mvt")
            digest = hashlib.sha256(tile.read_bytes()).hexdigest()
            artifact = {
                "schema_version": "uec-public-map-artifact-v1",
                "release_id": "release-a",
                "profile": "official",
                "generated_at": "2026-09-29T12:00:00Z",
                "attribution": [],
                "bounds": None,
                "source_layer": "uec_map",
                "feature_schema_version": "uec-map-feature-v1",
                "feature_properties": ["feature_key", "kind", "count", "exact_count", "coarse_count", "next_zoom", "record_id", "category_key"],
                "count_semantics": "count",
                "feature_key_semantics": "stable",
                "next_zoom_semantics": "child zoom",
                "suppression_generation": 7,
                "min_zoom": 0,
                "max_zoom": 14,
                "tile_url_template": "/api/v2/releases/release-a/map/tiles/{z}/{x}/{y}.mvt?profile=official",
                "tiles": [{"z": 0, "x": 0, "y": 0, "sha256": digest, "etag": f'"{digest}"', "byte_size": len(tile.read_bytes())}],
                "cache_policy": {"max_age_seconds": 0, "cache_control": "public, max-age=0, must-revalidate"},
            }
            manifest_path = root / "map-artifact.json"
            manifest_path.write_text(json.dumps(artifact), encoding="utf-8")
            self.assertEqual(PROMOTE.validate_map_artifact(manifest_path, "release-a", "official", 7)["source_layer"], "uec_map")
            artifact["feature_schema_version"] = "uec-map-feature-v2"
            artifact["feature_properties"].append("category_keys_compact")
            manifest_path.write_text(json.dumps(artifact), encoding="utf-8")
            self.assertEqual(PROMOTE.validate_map_artifact(manifest_path, "release-a", "official", 7)["feature_schema_version"], "uec-map-feature-v2")
            with self.assertRaisesRegex(ValueError, "identity or schema"):
                PROMOTE.validate_map_artifact(manifest_path, "release-a", "secondary", 7)
            with self.assertRaisesRegex(ValueError, "stale suppression"):
                PROMOTE.validate_map_artifact(manifest_path, "release-a", "official", 8)
            tile.write_bytes(b"changed bytes")
            with self.assertRaisesRegex(ValueError, "checksum"):
                PROMOTE.validate_map_artifact(manifest_path, "release-a", "official", 7)


if __name__ == "__main__":
    unittest.main()
