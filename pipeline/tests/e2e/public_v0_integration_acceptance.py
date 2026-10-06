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

    def request(self, path):
        with urllib.request.urlopen(self.origin + path, timeout=120) as response:
            return response.status, response.headers, response.read()

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
                                             ("profile=official&release_id=bad%2Fid", "invalid_release_id")):
            with self.assertRaises(urllib.error.HTTPError) as invalid:
                self.request("/api/v2/map/feed?" + invalid_query)
            self.assertEqual(invalid.exception.code, 400)
            self.assertEqual(json.loads(invalid.exception.read())["error"]["code"], expected_code)


if __name__ == "__main__":
    unittest.main()
