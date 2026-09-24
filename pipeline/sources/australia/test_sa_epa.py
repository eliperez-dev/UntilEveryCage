"""Contract tests use only synthetic rows shaped like the observed GeoJSON."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.sources.australia import sa_epa


FIXTURE = Path(__file__).parent / "fixtures" / "sa_epa_synthetic.geojson"
TEST_TEMP_ROOT = FIXTURE.parents[4] / "target"


class _Response:
    def __init__(self, url, body, headers=None):
        self.status = 200
        self._url = url
        self._body = body
        self.headers = headers or {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def geturl(self):
        return self._url

    def read(self, size=-1):
        return self._body if size < 0 else self._body[:size]


class _Opener:
    def __init__(self, bodies):
        self.bodies = bodies

    def urlopen(self, request, timeout):
        url = request.full_url
        body = self.bodies[url]
        if isinstance(body, tuple):
            return _Response(body[0], body[1], {"Content-Type": "application/geo+json"})
        return _Response(url, body)


def _terms_file(root):
    path = root / "terms.json"
    path.write_text(json.dumps({"source_id": sa_epa.SOURCE_ID, "decision": "approved",
                                "license": sa_epa.LICENSE_TITLE, "private_preview_only": True}), encoding="utf-8")
    return path


class SouthAustraliaEpaTests(unittest.TestCase):
    def setUp(self):
        self.adapter = sa_epa.SouthAustraliaEpaAdapter()
        self.raw = FIXTURE.read_bytes()

    def test_exact_category_and_named_activity_whitelist(self):
        result = self.adapter.parse_bytes(self.raw)
        self.assertEqual(result["input_rows"], 5)
        self.assertEqual(len(result["accepted"]), 4)
        self.assertEqual(result["out_of_scope_rows"], 1)
        self.assertEqual(result["activity_counts"], {"intensive-animal-keeping": 2, "slaughtering": 1,
                                                       "animal-product-processing": 1})
        self.assertEqual(result["accepted"][0]["normalized"]["country_code"], "AU")
        self.assertEqual(result["accepted"][0]["normalized"]["region"], "South Australia")
        self.assertEqual(result["accepted"][0]["normalized"]["coordinates"]["precision"], "source-precision-unknown")
        self.assertEqual(result["coordinate_counts"], {
            "source_coordinates_outside_south_australia_envelope": 1,
            "zero_zero_source_coordinates": 1,
        })
        self.assertEqual(len(result["coordinate_quarantine"]), 2)
        self.assertEqual(result["accepted"][2]["normalized"]["coordinates"], {})

    def test_category_only_and_vague_titles_are_excluded(self):
        document = json.loads(self.raw)
        document["features"][0]["properties"]["LICENCE_NAME"] = "Synthetic Farm"
        result = self.adapter.parse_bytes(json.dumps(document).encode())
        self.assertEqual(result["out_of_scope_rows"], 2)

    def test_unknown_activity_category_fails_closed_as_drift(self):
        document = json.loads(self.raw)
        document["features"][0]["properties"]["ACTIVITY"] = "New EPA Category"
        with self.assertRaisesRegex(ValueError, "schema drift"):
            self.adapter.parse_bytes(json.dumps(document).encode())

    def test_missing_source_property_fails_closed(self):
        document = json.loads(self.raw)
        del document["features"][0]["properties"]["EPALICENCE"]
        with self.assertRaisesRegex(ValueError, "missing required properties"):
            self.adapter.parse_bytes(json.dumps(document).encode())

    def test_live_acquisition_verifies_catalog_and_preserves_hash_provenance(self):
        package = {"success": True, "result": {
            "id": sa_epa.CATALOG_PACKAGE_ID,
            "title": sa_epa.SOURCE_TITLE, "license_title": sa_epa.LICENSE_TITLE,
            "license_url": sa_epa.LICENSE_URL, "metadata_modified": "2026-09-24T00:00:00Z",
            "resources": [{"id": sa_epa.RESOURCE_ID, "url": sa_epa.SOURCE_URL,
                           "name": sa_epa.SOURCE_TITLE + " (GeoJSON)", "last_modified": "2026-03-18T00:31:00Z"}],
        }}
        terms_json = json.dumps({"source_id": sa_epa.SOURCE_ID, "decision": "approved",
                                 "license": sa_epa.LICENSE_TITLE, "private_preview_only": True}).encode()
        opener = _Opener({sa_epa.CATALOG_URL: json.dumps(package).encode(),
                          sa_epa.SOURCE_URL: (sa_epa.SOURCE_URL, self.raw)})
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            review = _terms_file(root)
            result = sa_epa.fetch(output_root=root / "out", run_id="test-run",
                                  terms_review_path=review, opener=opener)
            self.assertEqual(result["sha256"], hashlib.sha256(self.raw).hexdigest())
            self.assertEqual(result["license"], sa_epa.LICENSE_TITLE)
            self.assertEqual(result["effective_date"], "2026-03-18T00:31:00Z")
            self.assertTrue(Path(result["artifact_path"]).is_file())
            self.assertTrue((Path(result["artifact_path"]).parent / "acquisition-metadata.json").is_file())


if __name__ == "__main__":
    unittest.main()
