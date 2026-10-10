"""Opt-in acceptance against the disposable database-backed local API.

Run with UEC_API_ORIGIN=http://127.0.0.1:38206 python -m unittest
pipeline.tests.e2e.public_v0_integration_acceptance -v
"""

import csv
import io
import json
import math
import os
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BASELINE_PATH = Path(__file__).parents[2] / "contracts" / "development-baseline.json"


class PublicV0IntegrationAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.origin = os.environ.get("UEC_API_ORIGIN", "").rstrip("/")
        if not cls.origin:
            raise unittest.SkipTest("set UEC_API_ORIGIN to opt into the disposable real-v0 API acceptance")
        cls.baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        cls.release_id = cls.baseline["release_id"]

    def request(self, path, headers=None):
        request = urllib.request.Request(self.origin + path, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            if error.code == 304:
                return error.code, error.headers, error.read()
            raise

    def get_json(self, path, headers=None):
        status, response_headers, body = self.request(path, headers)
        return status, response_headers, json.loads(body)

    def compact_features(self, payload):
        """Expand compact-v1 only for parity assertions; do not retain row data."""
        compact = payload["data"]
        self.assertEqual(compact["format"], "compact-v1")
        dictionaries = compact["dictionaries"]
        source_ids = dictionaries["source_ids"]
        category_keys = dictionaries["category_keys"]
        precisions = dictionaries["precisions"]
        self.assertTrue(all(isinstance(value, str) and value for value in source_ids))
        self.assertTrue(all(isinstance(value, str) and value for value in category_keys))
        self.assertTrue(all(isinstance(value, str) and value for value in precisions))

        features = []
        for row in compact["features"]:
            self.assertEqual(len(row), 7)
            facility_id, longitude, latitude, source_index, category_index, category_indexes, precision_index = row
            self.assertIsInstance(facility_id, str)
            self.assertIsInstance(category_indexes, list)
            self.assertIsInstance(source_index, int)
            self.assertIsInstance(category_index, int)
            self.assertIsInstance(precision_index, int)
            self.assertTrue(all(isinstance(index, int) for index in category_indexes))
            self.assertGreaterEqual(source_index, 0)
            self.assertGreaterEqual(category_index, 0)
            self.assertGreaterEqual(precision_index, 0)
            self.assertLess(source_index, len(source_ids))
            self.assertLess(category_index, len(category_keys))
            self.assertLess(precision_index, len(precisions))
            self.assertTrue(all(0 <= index < len(category_keys) for index in category_indexes))
            features.append((
                facility_id, longitude, latitude, source_ids[source_index], category_keys[category_index],
                tuple(category_keys[index] for index in category_indexes), precisions[precision_index],
            ))
        return features

    def test_public_v0_surfaces_and_bounded_csv(self):
        release_path = "/api/v2/releases/manifest?profile=official"
        status, _, body = self.request(release_path)
        self.assertEqual(status, 200)
        manifest_response = json.loads(body)
        release = manifest_response["data"]
        self.assertEqual(release["release_id"], self.release_id)
        self.assertEqual(release["manifest_sha256"], self.baseline["manifest_sha256"])

        query = urllib.parse.urlencode({"profile": "official", "release_id": self.release_id})
        status, feed_headers, body = self.request("/api/v2/map/feed?" + query)
        self.assertEqual(status, 200)
        self.assertEqual(feed_headers["X-Uec-Release-Id"], self.release_id)
        self.assertEqual(feed_headers["Content-Type"].split(";", 1)[0], "application/geo+json")
        self.assertEqual(feed_headers["Cache-Control"], "public, max-age=0, must-revalidate")
        feed = json.loads(body)
        meta = feed["meta"]
        expected = self.baseline["expected"]
        self.assertEqual(meta["manifest_sha256"], self.baseline["manifest_sha256"])
        self.assertEqual(meta["public_record_count"], expected["public_rows"])
        self.assertEqual(meta["feature_count"], expected["mapped_rows"])
        self.assertEqual(meta["unmapped_count"], expected["unmapped_rows"])
        features = feed["data"]["features"]
        self.assertEqual(len(features), expected["mapped_rows"])
        ids = [feature["id"] for feature in features]
        self.assertEqual(len(set(ids)), len(ids))
        allowed_precision = {"exact", "city", "source_reported", "approximate"}
        for feature in features:
            self.assertEqual(feature["type"], "Feature")
            self.assertEqual(feature["geometry"]["type"], "Point")
            longitude, latitude = feature["geometry"]["coordinates"]
            self.assertTrue(math.isfinite(longitude) and -180 <= longitude <= 180)
            self.assertTrue(math.isfinite(latitude) and -90 <= latitude <= 90)
            props = feature["properties"]
            self.assertIn(props["precision"], allowed_precision)
            self.assertEqual(props["weight"], 1)
            self.assertTrue(props["category_key"])
            self.assertTrue(props["category_keys"])
            self.assertFalse({"name", "canonical_name", "address", "source_payload"} & props.keys())

        compact_query = urllib.parse.urlencode({
            "profile": "official", "release_id": self.release_id, "format": "compact",
        })
        compact_status, compact_headers, compact_body = self.request("/api/v2/map/feed?" + compact_query)
        self.assertEqual(compact_status, 200)
        self.assertEqual(compact_headers["Content-Type"].split(";", 1)[0], "application/json")
        self.assertEqual(compact_headers["ETag"], feed_headers["ETag"])
        self.assertEqual(compact_headers["X-Uec-Manifest-Sha256"], self.baseline["manifest_sha256"])
        self.assertEqual(compact_headers["X-Uec-Suppression-Generation"], str(meta["suppression_generation"]))
        compact = json.loads(compact_body)
        self.assertEqual(compact["meta"], meta)
        legacy_projection = {
            (
                feature["id"], *feature["geometry"]["coordinates"], feature["properties"]["source_id"],
                feature["properties"]["category_key"], tuple(feature["properties"]["category_keys"]),
                feature["properties"]["precision"],
            )
            for feature in features
        }
        self.assertEqual(set(self.compact_features(compact)), legacy_projection)

        conditional_status, conditional_headers, conditional_body = self.request(
            "/api/v2/map/feed?" + compact_query, {"If-None-Match": compact_headers["ETag"]}
        )
        self.assertEqual(conditional_status, 304)
        self.assertEqual(conditional_body, b"")
        self.assertEqual(conditional_headers["ETag"], compact_headers["ETag"])
        self.assertEqual(conditional_headers["X-Uec-Release-Id"], self.release_id)
        self.assertEqual(conditional_headers["X-Uec-Manifest-Sha256"], self.baseline["manifest_sha256"])
        self.assertEqual(conditional_headers["X-Uec-Suppression-Generation"], str(meta["suppression_generation"]))

        _, _, unfiltered_locations = self.get_json(
            "/api/v2/locations?" + urllib.parse.urlencode({
                "profile": "official", "release_id": self.release_id, "limit": "1",
            })
        )
        self.assertEqual(unfiltered_locations["meta"]["total_count"], expected["public_rows"])

        category_precision_totals = {}
        for feature in features:
            precision = feature["properties"]["precision"]
            for category in set(feature["properties"]["category_keys"]):
                key = (category, precision)
                category_precision_totals[key] = category_precision_totals.get(key, 0) + 1
        self.assertTrue(category_precision_totals)
        for (category, precision), expected_total in category_precision_totals.items():
            location_query = urllib.parse.urlencode({
                "profile": "official", "release_id": self.release_id, "category_keys": category,
                "display_precision": precision, "limit": "1",
            })
            _, _, filtered = self.get_json("/api/v2/locations?" + location_query)
            self.assertEqual(filtered["meta"]["total_count"], expected_total)
            self.assertLessEqual(len(filtered["data"]), 1)
        selected_categories = sorted({category for category, _ in category_precision_totals})[:2]
        if len(selected_categories) == 2:
            for precision in sorted({feature["properties"]["precision"] for feature in features}):
                expected_union = sum(
                    feature["properties"]["precision"] == precision
                    and bool(set(feature["properties"]["category_keys"]) & set(selected_categories))
                    for feature in features
                )
                union_query = urllib.parse.urlencode({
                    "profile": "official", "release_id": self.release_id,
                    "category_keys": ",".join(selected_categories), "display_precision": precision, "limit": "1",
                })
                _, _, filtered = self.get_json("/api/v2/locations?" + union_query)
                self.assertEqual(filtered["meta"]["total_count"], expected_union)

        detail_query = urllib.parse.urlencode({"profile": "official", "release_id": self.release_id})
        status, _, detail_body = self.request(f"/api/v2/locations/{ids[0]}?{detail_query}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(detail_body)["data"]["facility_id"], ids[0])
        self.assertEqual(self.request("/api/v2/locations?profile=official&limit=1")[0], 200)
        self.assertEqual(self.request("/api/v2/discovery/facets?profile=official")[0], 200)

        csv_query = urllib.parse.urlencode({"profile": "official", "limit": "1000"})
        status, headers, csv_body = self.request("/api/v2/locations.csv?" + csv_query)
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Uec-Export-Total-Count"], str(expected["public_rows"]))
        self.assertEqual(headers["X-Uec-Export-Returned-Count"], "1000")
        self.assertEqual(headers["X-Uec-Export-Truncated"], "true")
        self.assertEqual(sum(1 for _ in csv.reader(io.StringIO(csv_body.decode("utf-8")))) - 1, 1000)

        with self.assertRaises(urllib.error.HTTPError) as oversize:
            self.request("/api/v2/locations.csv?profile=official")
        self.assertEqual(oversize.exception.code, 400)
        self.assertEqual(json.loads(oversize.exception.read())["error"]["code"], "export_too_large")
        for invalid_query, expected_code in (("profile=invalid&release_id=" + self.release_id, "invalid_profile"),
                                             ("profile=official&release_id=bad%2Fid", "invalid_release_id"),
                                             ("profile=official&release_id=" + self.release_id + "&format=invalid", "invalid_format")):
            with self.assertRaises(urllib.error.HTTPError) as invalid:
                self.request("/api/v2/map/feed?" + invalid_query)
            self.assertEqual(invalid.exception.code, 400)
            self.assertEqual(json.loads(invalid.exception.read())["error"]["code"], expected_code)


if __name__ == "__main__":
    unittest.main()
