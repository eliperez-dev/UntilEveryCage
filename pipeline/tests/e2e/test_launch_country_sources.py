"""Read-only country acceptance on the assigned V0 development copy."""
import json
import os
from pathlib import Path
import unittest
import urllib.error
import urllib.parse
import urllib.request

import psycopg
from pipeline.scripts.release_baseline import load_contract, verify_connection

ROOT = Path(__file__).resolve().parents[3]
DATABASE = "uec_launch_sources_test_20261025"
COHORTS = {
    "fsa_approved_establishments": (4289, False),
    "fss_approved_establishments": (595, False),
    "mx.locations": (5377, True),
    "nz.locations": (1638, False),
}


class LaunchCountrySources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.origin = os.environ.get("UEC_COUNTRY_API_ORIGIN", "").rstrip("/")
        cls.token = os.environ.get("UEC_DEV_PREVIEW_TOKEN", "")
        database_url = os.environ.get("UEC_DATABASE_URL", "")
        if not cls.origin or not cls.token or not database_url:
            raise unittest.SkipTest("requires the opt-in local country API and V0 database")
        api_url, db_url = urllib.parse.urlsplit(cls.origin), urllib.parse.urlsplit(database_url)
        if (api_url.hostname not in {"localhost", "127.0.0.1"}
                or db_url.hostname not in {"localhost", "127.0.0.1"}
                or db_url.path.strip("/") != DATABASE):
            raise RuntimeError("country acceptance requires the assigned loopback V0 copy")
        cls.connection = psycopg.connect(database_url, autocommit=True)
        cls.connection.execute("SET default_transaction_read_only=on")
        verify_connection(cls.connection, load_contract(ROOT / "pipeline/contracts/development-baseline.json"))

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "connection"):
            cls.connection.close()

    def request(self, path):
        request = urllib.request.Request(self.origin + path, headers={
            "X-Uec-Dev-Preview-Token": self.token,
        })
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except (OSError, ValueError, urllib.error.HTTPError):
            raise AssertionError("country API request failed; response content withheld") from None

    def test_current_cohorts_list_search_detail_and_map(self):
        for source, (expected_count, mapped) in COHORTS.items():
            with self.subTest(source=source):
                latest = self.connection.execute("""SELECT facility_count,map_visible_count
                    FROM real_preview.source_preview_runs WHERE source_id=%s
                    ORDER BY created_at DESC,run_id DESC LIMIT 1""", (source,)).fetchone()
                self.assertTrue(latest is not None, "current source run is missing")
                self.assertTrue(latest[0] == expected_count, "cohort count differs from captured run")
                self.assertTrue((latest[1] > 0) == mapped, "map eligibility differs from source evidence")
                # A repeated source snapshot can retain accepted geocoding.
                # The source file's coordinate count is not the enriched map count.
                displayed = self.connection.execute("""SELECT EXISTS (
                    SELECT 1 FROM real_preview.candidates candidate
                    WHERE candidate.source_id=%s AND candidate.snapshot_sha256=(
                        SELECT snapshot_sha256 FROM real_preview.source_preview_runs
                        WHERE source_id=%s ORDER BY created_at DESC,run_id DESC LIMIT 1)
                    AND candidate.default_map_scope=true
                    AND ((candidate.location_class='numeric_source_coordinate'
                          AND candidate.latitude BETWEEN -90 AND 90
                          AND candidate.longitude BETWEEN -180 AND 180
                          AND (candidate.latitude<>0 OR candidate.longitude<>0))
                         OR (candidate.display_geometry_source IS NOT NULL
                             AND candidate.display_latitude BETWEEN -90 AND 90
                             AND candidate.display_longitude BETWEEN -180 AND 180)))""",
                    (source, source)).fetchone()[0]
                query = urllib.parse.urlencode({"source_id": source, "limit": 1})
                listing = self.request("/dev/real-preview/locations?" + query)
                rows = listing.get("data")
                self.assertTrue(isinstance(rows, list) and len(rows) == 1, "source list is empty")
                item = rows[0]
                self.assertTrue(item.get("source_id") == source, "source list crossed a source boundary")
                candidate = item.get("candidate_id")
                self.assertTrue(isinstance(candidate, str), "candidate link is missing")
                detail = self.request("/dev/real-preview/locations/" + urllib.parse.quote(candidate, safe=""))
                self.assertTrue(detail.get("data", {}).get("source_id") == source, "detail source differs")
                term = item.get("city") or item.get("activity_label") or item.get("source_name")
                if term:
                    search = self.request("/dev/real-preview/locations?" + urllib.parse.urlencode({
                        "source_id": source, "q": term, "limit": 1,
                    }))
                    self.assertTrue(bool(search.get("data")), "source search returned no matching record")
                viewport = self.request("/dev/real-preview/viewport?" + urllib.parse.urlencode({
                    "source_id": source, "west": -180, "south": -90,
                    "east": 180, "north": 90, "limit": 1,
                }))
                points = viewport.get("data")
                self.assertTrue(isinstance(points, list), "map response is malformed")
                self.assertTrue(bool(points) == displayed, "map eligibility was not preserved by the API")
                self.assertTrue(all(point.get("source_id") == source for point in points),
                                "map response crossed a source boundary")

    def test_v0_remains_unchanged(self):
        verify_connection(self.connection, load_contract(ROOT / "pipeline/contracts/development-baseline.json"))


if __name__ == "__main__":
    unittest.main()
