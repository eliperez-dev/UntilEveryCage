import importlib
import unittest
from datetime import datetime, timezone


MODULE = importlib.import_module("pipeline.common.source_rights")


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, required, decisions=()):
        self.required = required
        self.decisions = decisions

    def execute(self, query, params):
        if "FROM uec.release_members" in query:
            return _Result(self.required)
        return _Result(self.decisions)


def required(source="source-a", artifact="00000000-0000-0000-0000-000000000001", digest="a" * 64):
    return (source, "official", "release-a", artifact, digest)


def decision(source, artifact, digest, status, when, decision_id="10000000-0000-0000-0000-000000000001"):
    return (decision_id, source, "official", "release-a", artifact, digest, status, "synthetic-owner", "synthetic-reference", when)


class SourceRightsTests(unittest.TestCase):
    def setUp(self):
        self.when = datetime(2026, 9, 18, tzinfo=timezone.utc)
        self.artifact = "00000000-0000-0000-0000-000000000001"
        self.digest = "a" * 64

    def test_missing_decision_blocks_even_when_source_has_attribution(self):
        result = MODULE.evaluate(_Connection([required()]), "release-a")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blockers"][0]["reason"], "missing exact decision")

    def test_every_distinct_artifact_needs_its_own_clearance(self):
        second_artifact = "00000000-0000-0000-0000-000000000002"
        result = MODULE.evaluate(
            _Connection(
                [required(), required(artifact=second_artifact, digest="b" * 64)],
                [decision("source-a", self.artifact, self.digest, "cleared", self.when)],
            ),
            "release-a",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(len(result["blockers"]), 1)
        self.assertEqual(result["blockers"][0]["artifact_id"], second_artifact)

    def test_newer_restricted_decision_overrides_older_clearance(self):
        result = MODULE.evaluate(
            _Connection(
                [required()],
                [
                    decision("source-a", self.artifact, self.digest, "restricted", self.when, "20000000-0000-0000-0000-000000000001"),
                    decision("source-a", self.artifact, self.digest, "cleared", datetime(2026, 9, 17, tzinfo=timezone.utc)),
                ],
            ),
            "release-a",
        )
        self.assertEqual(result["blockers"][0]["reason"], "redistribution decision is restricted")

    def test_conflicting_latest_decisions_fail_closed(self):
        result = MODULE.evaluate(
            _Connection(
                [required()],
                [
                    decision("source-a", self.artifact, self.digest, "cleared", self.when, "30000000-0000-0000-0000-000000000001"),
                    decision("source-a", self.artifact, self.digest, "unknown", self.when, "40000000-0000-0000-0000-000000000001"),
                ],
            ),
            "release-a",
        )
        self.assertEqual(result["blockers"][0]["reason"], "conflicting decisions at the latest decision time")

    def test_same_status_latest_duplicates_are_deterministically_clear(self):
        result = MODULE.evaluate(
            _Connection(
                [required()],
                [
                    decision("source-a", self.artifact, self.digest, "cleared", self.when, "50000000-0000-0000-0000-000000000001"),
                    decision("source-a", self.artifact, self.digest, "cleared", self.when, "60000000-0000-0000-0000-000000000001"),
                ],
            ),
            "release-a",
        )
        self.assertEqual(result["status"], "cleared")
        self.assertEqual(len(result["requirements"][0]["decision_ids"]), 2)


if __name__ == "__main__":
    unittest.main()
