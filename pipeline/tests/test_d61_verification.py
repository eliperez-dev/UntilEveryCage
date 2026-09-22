"""D6.1 aggregate report and private API contract tests."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from pipeline.common.d61_verification import D61_PAGE_MAX, D61_REPORT_SCHEMA_VERSION, D61ReportError, build_report, validate_report
from pipeline.common.d6_private_graph import ConnectionEdge, ConnectionStore


class D61VerificationReportTests(unittest.TestCase):
    def test_report_has_candidate_persisted_and_ambiguous_counts(self):
        report = build_report(
            execution="docker_postgres_real_private",
            authorized_handoffs=4,
            private_rows_consumed=120,
            candidate_count=17,
            candidate_exact_count=8,
            candidate_inferred_count=9,
            persisted_exact_count=8,
            persisted_inferred_count=3,
            skipped_ambiguous_count=6,
            skipped_reasons={"conflicting_identifiers": 4, "missing_anchor": 2},
            negative_controls=2,
            conflicting_controls=1,
            genuine_inferred_connections=3,
            real_rehearsal_executed=True,
            idempotent=True,
            api_pages={"exact": 8, "inferred": 3},
        )
        self.assertEqual(report["schema_version"], D61_REPORT_SCHEMA_VERSION)
        self.assertEqual(report["candidates"]["inferred"], 9)
        self.assertEqual(report["persisted"]["inferred"], 3)
        self.assertEqual(report["skipped"]["ambiguous_blocks"], 6)
        self.assertEqual(report["skipped"]["reasons"]["conflicting_identifiers"], 4)
        self.assertEqual(report["status"], "verified")
        self.assertFalse(report["scope"]["row_payloads_in_report"])
        self.assertEqual(report["publication"]["public_rows"], 0)
        validate_report(report)

    def test_checked_in_contract_fixture_is_row_free_and_pending(self):
        path = Path(__file__).parent / "fixtures" / "d61-report-contract.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        validate_report(report)
        self.assertEqual(report["status"], "pending-real-rehearsal")
        self.assertFalse(report["scope"]["row_payloads_in_report"])
        self.assertEqual(report["publication"]["public_edges"], 0)

    def test_real_rehearsal_is_mandatory_and_pending_is_explicit(self):
        report = build_report(execution="offline_private_root", candidate_inferred_count=4, candidate_count=4)
        self.assertEqual(report["status"], "pending-real-rehearsal")
        self.assertTrue(report["real_rehearsal"]["required"])
        self.assertFalse(report["real_rehearsal"]["executed"])
        self.assertTrue(any("Docker/Postgres" in reason for reason in report["blockers"]))

    def test_real_status_cannot_be_verified_without_authorized_and_negative_controls(self):
        report = build_report(
            execution="docker_postgres_real_private",
            candidate_count=1,
            candidate_inferred_count=1,
            persisted_inferred_count=1,
            genuine_inferred_connections=1,
            real_rehearsal_executed=True,
        )
        self.assertEqual(report["status"], "pending-real-rehearsal")
        self.assertTrue(any("authorized retained handoff" in reason for reason in report["blockers"]))
        self.assertTrue(any("negative control" in reason for reason in report["blockers"]))

    def test_page_max_does_not_claim_a_storage_cap(self):
        report = build_report(
            execution="docker_postgres_real_private",
            persisted_inferred_count=135,
            genuine_inferred_connections=135,
            real_rehearsal_executed=True,
            api_pages={"inferred": D61_PAGE_MAX},
        )
        self.assertEqual(report["api"]["page_max"], 100)
        self.assertIsNone(report["api"]["storage_cap"])
        self.assertIsNone(report["persisted"]["storage_cap"])

    def test_report_rejects_private_payloads_and_public_rows(self):
        with self.assertRaises(D61ReportError):
            build_report(execution="bad", public_rows=1)
        report = build_report(execution="offline")
        report["scope"]["private_path"] = "must-not-be-committed"
        with self.assertRaises(D61ReportError):
            validate_report(report)


class D61PrivateApiStoreTests(unittest.TestCase):
    def _edge(self, edge_id: str, *, kind: str = "inferred", conflicting: bool = False, suppressed: bool = False) -> ConnectionEdge:
        return ConnectionEdge(
            edge_id=edge_id,
            source_id="real.source",
            source_record_id=None,
            connection_type=kind,
            left_entity_type="facility",
            left_entity_id=f"facility:{edge_id}",
            right_entity_type="organization",
            right_entity_id=f"organization:{edge_id}",
            confidence=0.72 if kind == "inferred" else 1.0,
            conflicting=conflicting,
            suppressed=suppressed,
            evidence_refs=({"source_id": "real.source", "source_record_ref": "digest-only"},),
            score_contributions={"name_postal": 0.72},
            observed_at="2026-09-21",
        )

    def test_filter_matrix_and_inferred_metadata_are_safe(self):
        store = ConnectionStore()
        store.add(self._edge("inferred-a"))
        store.add(self._edge("inferred-b", conflicting=True))
        store.add(self._edge("inferred-c", suppressed=True))
        store.add(self._edge("exact-a", kind="exact"))
        self.assertEqual(len(store.query(connection_type="inferred")["data"]), 1)
        self.assertEqual(len(store.query(connection_type="inferred", include_conflicting=True)["data"]), 2)
        self.assertEqual(len(store.query(min_confidence=.72)["data"]), 2)
        self.assertEqual(len(store.query(source_id="real.source", entity_id="facility:inferred-a")["data"]), 1)
        self.assertEqual(len(store.query(suppressed=True)["data"]), 1)
        row = store.query(connection_type="inferred")["data"][0]
        self.assertEqual(row["inferred_metadata"]["review_state"], "review_required")
        self.assertEqual(row["inferred_metadata"]["confidence_kind"], "ruleset_estimate_not_probability")
        self.assertIn("not human verified", row["disclaimer"])

    def test_cursor_pages_at_100_without_storage_cap(self):
        store = ConnectionStore()
        for index in range(135):
            store.add(self._edge(f"edge-{index:03d}"))
        first = store.query(limit=D61_PAGE_MAX)
        self.assertEqual(len(first["data"]), D61_PAGE_MAX)
        self.assertEqual(first["meta"]["page_max"], D61_PAGE_MAX)
        self.assertIsNone(first["meta"]["storage_cap"])
        second = store.query(limit=D61_PAGE_MAX, cursor=first["meta"]["next_cursor"])
        self.assertEqual(len(second["data"]), 35)
        self.assertEqual(len({row["connection_edge_id"] for row in first["data"]}.intersection(row["connection_edge_id"] for row in second["data"])), 0)


class D61RustSurfaceTests(unittest.TestCase):
    ROOT = Path(__file__).parents[2]

    def test_rust_connection_api_exposes_filters_metadata_and_zero_public_projection(self):
        handler = (self.ROOT / "src" / "graph_private.rs").read_text(encoding="utf-8")
        for field in ("connection_type", "min_confidence", "source_id", "entity_id", "include_conflicting", "suppressed", "cursor", "page_max", "storage_cap", "inferred_metadata", "disclaimer"):
            self.assertIn(field, handler)
        self.assertIn('"public_projection": false', handler)
        self.assertIn("LIMIT $8", handler)

    def test_diagnostic_report_script_has_no_private_path_output(self):
        script = (self.ROOT / "pipeline" / "scripts" / "diagnostics" / "d61-verification.py").read_text(encoding="utf-8")
        self.assertIn("real-rehearsal-report", script)
        self.assertIn("private roots are operator-supplied", script)
        self.assertNotIn("path_recorded_private", script)


if __name__ == "__main__":
    unittest.main()
