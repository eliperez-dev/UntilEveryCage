from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "maintenance" / "carry-forward-aphis-reference-clearance.py"
SPEC = importlib.util.spec_from_file_location("carry_forward_aphis", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def eligible_row():
    return (
        "record-id", "us.aphis.annual-reports", "artifact-id", "a" * 64,
        "prior-clearance-id", "original-operator", MODULE.DECISION_REFERENCE,
        "prior-review-id", "reviewed", "passed", "approved", True,
        "maintainer", "prior human note", None,
        None, None, None, None, None, None,
        None, None, None, None, None, None,
    )


def complete_row():
    row = list(eligible_row())
    prefix = MODULE._provenance_prefix(tuple(row))
    row[14] = "target-review-id"
    row[15:21] = ["reviewed", "passed", "approved", True, "maintainer",
                  prefix + " Operator recording carry-forward: release-operator."]
    row[21:27] = ["target-clearance-id", "approved", MODULE.APPROVED_FIELDS,
                  "a" * 64, MODULE.SCOPE_VERSION, MODULE.DECISION_REFERENCE]
    return tuple(row)


def prepared_row(source_record_id="record-id", prior_review_id="prior-review-id"):
    row = list(eligible_row())
    row[0] = source_record_id
    row[7] = prior_review_id
    prefix = MODULE._provenance_prefix(tuple(row))
    row[14] = "target-review-id"
    row[15:21] = ["reviewed", "passed", "approved", True, "maintainer",
                  prefix + " Operator recording carry-forward: release-operator."]
    return tuple(row)


class FakeConnection:
    def __init__(self, rows=None, database=MODULE.TARGET_DATABASE, releases=None, scope_ok=True):
        self.rows = list(rows if rows is not None else [prepared_row()])
        self.database = database
        self.releases = releases or [
            (MODULE.SOURCE_RELEASE, "official", False, "promoted", True, None, None),
            (MODULE.TARGET_RELEASE, "official", False, "promoted", True, None, None),
        ]
        self.scope_ok = scope_ok
        self.calls = []
        self.executed_writes = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if sql.strip() == "SELECT current_database()":
            return FakeCursor([(self.database,)])
        if "to_regclass('uec.publication_review_release_scopes')" in sql:
            return FakeCursor([(True, True, True)])
        if "WITH eligible_release AS" in sql:
            return FakeCursor(self.rows)
        if "FROM uec.releases release" in sql and "public_release_history" in sql:
            return FakeCursor(self.releases)
        if "SELECT EXISTS(" in sql and "publication_review_release_scopes scope" in sql:
            return FakeCursor([(self.scope_ok,)])
        if "INSERT INTO uec.publication_review_events" in sql:
            self.executed_writes.append((sql, params))
            return FakeCursor([("synthetic-review-event",)])
        if "INSERT INTO uec.graph_public_evidence_metadata_clearance_events" in sql:
            self.executed_writes.append((sql, params))
        return FakeCursor([])


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return self.rows


class CarryForwardAphisReferenceClearanceTests(unittest.TestCase):
    def test_url_is_pinned_to_local_test_database_without_routing_options(self):
        url = "postgresql://user:secret@127.0.0.1:55433/uec_country_release_test_20261027"
        MODULE.validate_database_url(url, MODULE.TARGET_DATABASE)
        for bad_url, expected_error in (
            (url.replace("127.0.0.1", "example.com"), "database_url_host_not_loopback"),
            (url + "?host=remote", "database_url_routing_options_forbidden"),
            (url.replace(MODULE.TARGET_DATABASE, "uec"), "database_url_database_mismatch"),
        ):
            with self.subTest(expected_error=expected_error):
                with self.assertRaisesRegex(MODULE.CarryForwardError, expected_error):
                    MODULE.validate_database_url(bad_url, MODULE.TARGET_DATABASE)

    def test_dry_run_is_default_and_only_reports_aggregates(self):
        connection = FakeConnection()
        result = MODULE.carry_forward(connection, actor="release-operator")
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["would_copy_records"], 1)
        self.assertEqual(result["would_insert_clearance_artifacts"], 1)
        self.assertEqual(connection.executed_writes, [])
        query = next(sql for sql, _ in connection.calls if "WITH eligible_release AS" in sql)
        self.assertIn("event.event_period ~ '^[0-9]{4}$'", query)
        for required_gate in (
            "graph_public_evidence_metadata_clearance_events",
            "decision.approved_fields=%s::text[]",
            "decision.artifact_sha256",
            "public_access_restricted",
            "release_members",
            "factual_review_status<>'rejected'",
            "target_clearance",
        ):
            self.assertIn(required_gate, query)

    def test_apply_copies_only_exact_scope_and_retains_prior_provenance(self):
        connection = FakeConnection()
        result = MODULE.carry_forward(connection, actor="release-operator", apply=True)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["would_copy_records"], 1)
        self.assertEqual(len(connection.executed_writes), 1)
        clearance_sql, clearance_params = connection.executed_writes[0]
        self.assertIn("graph_public_evidence_metadata_clearance_events", clearance_sql)
        self.assertEqual(clearance_params[1], MODULE.TARGET_RELEASE)
        self.assertEqual(clearance_params[-1], MODULE.DECISION_REFERENCE)

    def test_existing_conflicting_target_decision_is_not_overwritten(self):
        row = list(eligible_row())
        row[14] = "existing-target-review"
        row[15:21] = ["rejected", "failed", "denied", False, "maintainer", "existing note"]
        connection = FakeConnection(rows=[tuple(row)])
        with self.assertRaisesRegex(MODULE.CarryForwardError, "target_review_conflict_exists"):
            MODULE.carry_forward(connection, actor="release-operator", apply=True)
        self.assertEqual(connection.executed_writes, [])

    def test_repeated_run_recognizes_exact_provenance_and_is_idempotent(self):
        connection = FakeConnection(rows=[complete_row()])
        result = MODULE.carry_forward(connection, actor="release-operator", apply=True)
        self.assertEqual(result["already_identical"], 1)
        self.assertEqual(result["would_copy_records"], 0)
        self.assertEqual(connection.executed_writes, [])

    def test_multiple_records_sharing_artifact_create_one_clearance(self):
        first = list(prepared_row())
        second = list(prepared_row("another-record-id", "another-prior-review"))
        connection = FakeConnection(rows=[tuple(first), tuple(second)])
        result = MODULE.carry_forward(connection, actor="release-operator", apply=True)
        clearance_inserts = [sql for sql, _ in connection.executed_writes
                             if "graph_public_evidence_metadata_clearance_events" in sql]
        review_inserts = [sql for sql, _ in connection.executed_writes
                          if "INSERT INTO uec.publication_review_events" in sql]
        self.assertEqual(result["would_copy_records"], 2)
        self.assertEqual(len(clearance_inserts), 1)
        self.assertEqual(len(review_inserts), 0)

    def test_existing_target_withdrawal_is_a_conflict(self):
        row = list(eligible_row())
        row[21:27] = ["target-withdrawal", "withdrawn", MODULE.APPROVED_FIELDS,
                      "a" * 64, MODULE.SCOPE_VERSION, MODULE.DECISION_REFERENCE]
        connection = FakeConnection(rows=[tuple(row)])
        with self.assertRaisesRegex(MODULE.CarryForwardError, "target_review_conflict_exists"):
            MODULE.carry_forward(connection, actor="release-operator", apply=True)
        self.assertEqual(connection.executed_writes, [])

    def test_partial_completion_adds_only_missing_side(self):
        row = list(complete_row())
        row[21:27] = [None, None, None, None, None, None]
        connection = FakeConnection(rows=[tuple(row)])
        MODULE.carry_forward(connection, actor="release-operator", apply=True)
        self.assertEqual(len(connection.executed_writes), 1)
        self.assertIn("graph_public_evidence_metadata_clearance_events", connection.executed_writes[0][0])

        row = list(complete_row())
        row[14:21] = [None, None, None, None, None, None, None]
        connection = FakeConnection(rows=[tuple(row)])
        with self.assertRaisesRegex(MODULE.CarryForwardError, "target_publication_reviews_not_prepared"):
            MODULE.carry_forward(connection, actor="release-operator", apply=True)
        self.assertEqual(connection.executed_writes, [])

    def test_missing_trigger_created_scope_aborts_apply(self):
        releases = [
            (MODULE.SOURCE_RELEASE, "official", False, "promoted", True, None, None),
            (MODULE.TARGET_RELEASE, "official", False, "candidate", False, "true",
             MODULE.TARGET_FREEZE_SHA256),
        ]
        connection = FakeConnection(rows=[eligible_row()], releases=releases, scope_ok=False)
        with self.assertRaisesRegex(MODULE.CarryForwardError, "release_scoped_review_not_created"):
            MODULE.carry_forward(connection, actor="release-operator", prepare_reviews_only=True)

    def test_non_public_or_test_release_is_rejected(self):
        connection = FakeConnection(releases=[
            (MODULE.SOURCE_RELEASE, "official", False, "promoted", True, None, None),
            (MODULE.TARGET_RELEASE, "official", True, "candidate", False, "true",
             MODULE.TARGET_FREEZE_SHA256),
        ])
        with self.assertRaisesRegex(MODULE.CarryForwardError, "release_not_historically_public_official"):
            MODULE.carry_forward(connection, actor="release-operator")

    def test_prepromotion_stage_writes_reviews_only_for_exact_candidate(self):
        releases = [
            (MODULE.SOURCE_RELEASE, "official", False, "promoted", True, None, None),
            (MODULE.TARGET_RELEASE, "official", False, "candidate", False, "true",
             MODULE.TARGET_FREEZE_SHA256),
        ]
        connection = FakeConnection(rows=[eligible_row()], releases=releases)
        result = MODULE.carry_forward(connection, actor="release-operator", prepare_reviews_only=True)
        self.assertEqual(result["stage"], "prepare_reviews_only")
        self.assertEqual(result["status"], "prepared_reviews")
        self.assertEqual(result["would_insert_clearance_artifacts"], 0)
        _, parameters = next((sql, params) for sql, params in connection.calls
                             if "WITH eligible_release AS" in sql)
        self.assertEqual(parameters[6:9], (MODULE.SOURCE_RELEASE,
                                         MODULE.TARGET_RELEASE,
                                         MODULE.TARGET_FREEZE_SHA256))
        self.assertEqual(len(connection.executed_writes), 1)
        self.assertIn("INSERT INTO uec.publication_review_events", connection.executed_writes[0][0])
        note = connection.executed_writes[0][1][-1]
        self.assertIn("original-operator", note)
        self.assertIn("prior-review-id", note)
        self.assertNotIn("prior human note", note)
        self.assertIn("release-operator", note)

    def test_default_final_stage_rejects_candidate_target(self):
        releases = [
            (MODULE.SOURCE_RELEASE, "official", False, "promoted", True, None, None),
            (MODULE.TARGET_RELEASE, "official", False, "candidate", False, "true",
             MODULE.TARGET_FREEZE_SHA256),
        ]
        with self.assertRaisesRegex(MODULE.CarryForwardError, "release_not_historically_public_official"):
            MODULE.carry_forward(FakeConnection(releases=releases), actor="release-operator")

    def test_prepromotion_stage_rejects_wrong_candidate_freeze(self):
        releases = [
            (MODULE.SOURCE_RELEASE, "official", False, "promoted", True, None, None),
            (MODULE.TARGET_RELEASE, "official", False, "candidate", False, "true", "0" * 64),
        ]
        with self.assertRaisesRegex(MODULE.CarryForwardError, "target_candidate_identity_mismatch"):
            MODULE.carry_forward(FakeConnection(releases=releases), actor="release-operator",
                                 prepare_reviews_only=True)

    def test_actor_and_fixed_decision_reference_are_required(self):
        with self.assertRaisesRegex(MODULE.CarryForwardError, "operator_actor_invalid"):
            MODULE.carry_forward(FakeConnection(), actor="operator\nmalicious")


if __name__ == "__main__":
    unittest.main()
