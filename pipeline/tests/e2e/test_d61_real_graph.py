"""Mandatory real-data D6.1 Docker/Postgres rehearsal gate.

This suite is opt-in because retained authorized handoffs never live in Git.
When enabled, however, it is intentionally not skippable for missing or zero
inferred edges: a run that cannot prove a genuine inferred edge fails closed.
"""
from __future__ import annotations

import os
import unittest

import psycopg

from .fixture import E2EEnvironment
from .d61_rehearsal import assert_real_inferred_control


@unittest.skipUnless(
    os.environ.get("UEC_RUN_D61_REAL") == "1",
    "set UEC_RUN_D61_REAL=1 after loading an authorized retained handoff",
)
class D61RealGraphRehearsalTests(unittest.TestCase):
    """The real Docker/Postgres gate; synthetic rows are deliberately absent."""

    @classmethod
    def setUpClass(cls):
        cls.env = E2EEnvironment().start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    def test_real_inferred_connection_is_nonzero_and_public_projection_empty(self):
        # The matcher/persistence integration is responsible for loading the
        # operator-authorized real handoff into this disposable database.
        # This assertion is intentionally strict once UEC_RUN_D61_REAL=1.
        with psycopg.connect(self.env.database_url) as connection:
            result = assert_real_inferred_control(connection)
        self.assertGreater(result["genuine_inferred_connections"], 0)
        self.assertEqual(result["public_edges"], 0)


if __name__ == "__main__":
    unittest.main()
