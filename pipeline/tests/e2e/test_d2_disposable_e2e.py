"""Docker-gated D2 private PostGIS insertion and public-boundary E2E."""
from __future__ import annotations

import json
import os
import unittest
import urllib.request

import psycopg

from pipeline.common.d2_e2e_readiness import D2_SOURCE_IDS, build_report
from pipeline.common.d2_postgres_sink import make_disposable_postgis_sink

try:
    from .fixture import E2EEnvironment
except ImportError:  # pragma: no cover
    from fixture import E2EEnvironment


class D2DisposablePostgisE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed D2 E2E tests")
        cls.env = E2EEnvironment().start()
        sink = make_disposable_postgis_sink(cls.env.database_url)
        cls.first = build_report(database_sink=sink)
        cls.second = build_report(database_sink=sink)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "env", None):
            cls.env.stop()

    def test_all_sources_insert_private_candidates_idempotently(self):
        self.assertEqual(self.first["aggregate"]["passed_sources"], len(D2_SOURCE_IDS))
        self.assertEqual(self.first["aggregate"]["database_candidate_rows"], 21)
        self.assertEqual(self.second["aggregate"]["database_candidate_rows"], 0)
        with psycopg.connect(self.env.database_url) as db:
            counts = db.execute(
                """SELECT
                    (SELECT count(*) FROM uec.source_records),
                    (SELECT count(*) FROM uec.facilities),
                    (SELECT count(*) FROM uec.observations),
                    (SELECT count(*) FROM uec.publication_review_events),
                    (SELECT count(*) FROM uec.releases)"""
            ).fetchone()
        self.assertEqual(counts, (35, 21, 21, 21, 0))

    def test_private_insert_never_reaches_public_api(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.env.api_port}/api/v2/locations?profile=official") as response:
            body = json.loads(response.read())
        self.assertEqual(body["data"], [])


if __name__ == "__main__":
    unittest.main()
