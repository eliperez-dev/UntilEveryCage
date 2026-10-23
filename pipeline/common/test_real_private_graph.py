from __future__ import annotations

import json
import hashlib
import shutil
import unittest
from unittest import mock
from pathlib import Path

from pipeline.common.d5_connection_analysis import _iter_probabilistic_candidates, _observed_from_row
from pipeline.common.real_private_graph import (_MatcherStage, _handoffs, build_report,
    discover_graph_handoffs, discover_manifests, graph_corpus_materialization_fingerprint, materialize_graph_corpus,
    run_rehearsal, write_report)
from pipeline.common.graph_candidate import write_graph_candidates
from pipeline.common.graph_candidate import build_graph_candidate
from pipeline.contracts.graph_candidate_handoff import canonical_json_bytes, validate_graph_candidate
from pipeline.common.graph_persistence import build_candidate_connection_edges, load_graph_candidate_handoff


class RealPrivateGraphTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(".tmp") / "d5-real-private-graph-tests"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_manifest_discovery_is_row_free_and_deduplicated(self):
        root = self.root
        payload = {
                "source_id": "test.real",
                "normalized_rows": 4,
                "quarantined_rows": 1,
                "graph_candidate_summary": {
                    "candidate_count": 4,
                    "facility_identifier_candidates": 3,
                    "organization_identifier_candidates": 2,
                    "operator_relationship_candidates": 2,
                },
                "review_metrics": {"geospatial": {"coordinate_state_counts": {"exact": 3, "unmapped": 1}}},
                "release_state": "not-created",
                "publication_state": "private-candidate",
            }
        (root / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
        (root / "copy.json").write_text(json.dumps(payload), encoding="utf-8")
        records = discover_manifests([root])
        self.assertEqual(len(records), 1)
        report = build_report([root])
        self.assertEqual(report["source_count"], 1)
        self.assertEqual(report["totals"]["normalized_rows"], 4)
        self.assertEqual(report["sources"][0]["coordinate_state_counts"], {"exact": 3, "unmapped": 1})
        self.assertEqual(report["sources"][0]["integrity_status"], "missing-provenance")
        self.assertNotIn("records", json.dumps(report))

    def test_source_list_expands_without_payload(self):
        root = self.root
        (root / "aggregate-report.json").write_text(json.dumps({"sources": [{"source_id": "a.real", "normalized_rows": 2}, {"source_id": "b.real", "normalized_rows": 3}]}), encoding="utf-8")
        report = build_report([root])
        self.assertEqual(report["source_count"], 2)
        self.assertEqual(report["totals"]["normalized_rows"], 5)

    def test_selection_prefers_detailed_quarantine_counts(self):
        root = self.root
        (root / "run-a-manifest.json").write_text(json.dumps({"source_id": "a.real", "normalized_rows": 10, "quarantined_rows": 0}), encoding="utf-8")
        (root / "run-b-manifest.json").write_text(json.dumps({"source_id": "a.real", "normalized_rows": 10, "quarantined_rows": 2}), encoding="utf-8")
        report = build_report([root])
        self.assertEqual(report["sources"][0]["quarantined_rows"], 2)

    def test_real_handoff_discovery_and_private_report(self):
        root = self.root
        handoff = root / "source" / "graph-candidates"
        handoff.mkdir(parents=True)
        (handoff / "manifest.json").write_text(json.dumps({"source_id": "a.real", "release_state": "not-created", "publication_state": "private-candidate", "records_sha256": ""}), encoding="utf-8")
        (handoff / "records.jsonl").write_text("", encoding="utf-8")
        report = run_rehearsal([root])
        self.assertEqual(report["handoffs"]["facility"], 1)
        self.assertFalse(report["publication"]["approval_inferred"])
        digest = write_report(report, root / "report.json")
        self.assertEqual(len(digest), 64)

    def test_real_handoff_discovery_accepts_standard_graph_candidates_jsonl(self):
        for folder in ("standard-export", "nested-standard-export"):
            with self.subTest(folder=folder):
                root = self.root / folder
                root.mkdir(parents=True)
                (root / "manifest.json").write_text(json.dumps({
                    "source_id": f"test.{folder}", "release_state": "not-created",
                    "publication_state": "private-candidate", "source_kind": "facility_master",
                }), encoding="utf-8")
                payload = root / "graph-candidates.jsonl" if folder == "standard-export" else root / "graph-candidates" / "graph-candidates.jsonl"
                payload.parent.mkdir(parents=True, exist_ok=True)
                payload.write_text("", encoding="utf-8")
                handoffs = _handoffs([self.root], {f"test.{folder}"})
                self.assertEqual([(source_id, kind) for source_id, kind, _ in handoffs],
                                 [(f"test.{folder}", "facility")])
                discovered = discover_graph_handoffs([self.root], selected_sources=[f"test.{folder}"])
                self.assertEqual([(source_id, kind) for source_id, kind, _ in discovered],
                                 [(f"test.{folder}", "facility")])

    def test_corpus_fingerprint_and_dispatch_include_evidence_without_staging_it(self):
        facility = self.root / "facility"
        write_graph_candidates(facility, [{
            "source_id": "test.facility", "source_row": 1,
            "source_record_key": "facility-key-1", "source_values": {"id": "A-1"},
            "normalized": {"establishment_id": "A-1", "name": "Example Works"},
        }], artifact_sha256="a" * 64, observed_at="2026-01-01T00:00:00Z")
        facility_manifest = json.loads((facility / "manifest.json").read_text(encoding="utf-8"))
        facility_manifest.update({"source_id": "test.facility", "source_artifact_sha256": "a" * 64})
        (facility / "manifest.json").write_text(json.dumps(facility_manifest), encoding="utf-8")
        evidence = self.root / "evidence"
        evidence.mkdir()
        event = {"source_id": "test.evidence", "source_record_key": "event-key-1",
                 "normalized": {"source_observation_key": "event-key-1", "event_type": "inspection"}}
        records = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode()
        (evidence / "records.jsonl").write_bytes(records)
        digest = __import__("hashlib").sha256(records).hexdigest()
        (evidence / "manifest.json").write_text(json.dumps({
            "source_id": "test.evidence", "source_kind": "evidence_event",
            "contract_version": "us-aphis-observation-handoff-v1", "entity_scope": "evidence_event",
            "source_artifact_sha256": "b" * 64,
            "normalized_rows": 1, "normalized_sha256": digest,
            "release_state": "not-created", "publication_state": "private-candidate",
        }), encoding="utf-8")
        first_fingerprint = graph_corpus_materialization_fingerprint([facility, evidence])

        class Stage:
            def __init__(self):
                self.added = []
            def add_handoff(self, path):
                self.added.append(Path(path))
            def build_candidates(self):
                return {"rows_staged": 1, "blocks_ambiguous": 0, "rows_in_ambiguous_blocks": 0}
            def edge_builder(self, _candidate, _manifest):
                return ()
            def close(self):
                pass

        stage = Stage()
        with mock.patch("pipeline.common.real_private_graph._MatcherStage", return_value=stage), \
             mock.patch("pipeline.common.real_private_graph.completed_edge_materialization", return_value=None), \
             mock.patch("pipeline.common.real_private_graph.import_graph_candidates", return_value={
                 "source_id": "test.facility", "status": "completed", "item_count": 1,
             }) as import_facility, \
             mock.patch("pipeline.common.real_private_graph.import_evidence_events", return_value={
                 "source_id": "test.evidence", "status": "already_present", "item_count": 1,
             }) as import_evidence:
            result = materialize_graph_corpus(
                "postgresql://localhost/test", [facility, evidence],
                private_target=("uec_graph_test", "private-graph-materialization-v1"),
            )
        self.assertEqual(stage.added, [facility])
        self.assertEqual(result["status"], "completed")
        self.assertEqual({item["kind"] for item in result["imports"]}, {"facility", "evidence"})
        import_facility.assert_called_once()
        import_evidence.assert_called_once_with(
            "postgresql://localhost/test", evidence,
            private_target=("uec_graph_test", "private-graph-materialization-v1"),
            batch_size=250, on_batch_committed=None,
        )
        self.assertEqual(result["materialization_fingerprint"], first_fingerprint)
        event["normalized"]["event_type"] = "revised-inspection"
        records = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode()
        (evidence / "records.jsonl").write_bytes(records)
        manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
        manifest["normalized_sha256"] = __import__("hashlib").sha256(records).hexdigest()
        (evidence / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertNotEqual(first_fingerprint, graph_corpus_materialization_fingerprint([facility, evidence]))

    def test_fsis_alias_matcher_stage_produces_supported_inferred_edge(self):
        handoff = self.root / "fsis" / "graph-candidates"
        write_graph_candidates(handoff, [
            {"source_id": "us.fsis", "source_row": 1, "source_record_key": "fsis-a",
             "normalized": {"establishment_id": "FS-001", "dba_names": ["Synthetic Business Name"]}},
            {"source_id": "us.fsis", "source_row": 2, "source_record_key": "fsis-b",
             "normalized": {"establishment_id": "FS-002", "alternate_names": ["synthetic business name"]}},
        ], artifact_sha256="a" * 64, observed_at="2026-01-01T00:00:00Z")
        stage = _MatcherStage()
        try:
            stage.add_handoff(handoff)
            stats = stage.build_candidates()
            first = next(row for row in load_graph_candidate_handoff(handoff)[1]
                         if row["source_record_key"] == "fsis-a")
            manifest = {"source_id": "us.fsis", "retrieved_at_utc": "2026-01-02T00:00:00Z"}
            edges = build_candidate_connection_edges(first, manifest, edge_builder=stage.edge_builder)
            self.assertEqual(stats["shared_business_name_pairs_emitted"], 1)
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0]["relationship_type"], "shared_business_name")
            self.assertEqual(edges[0]["connection_type"], "inferred")
            self.assertEqual({ref["source_record_key"] for ref in edges[0]["supporting_source_refs"]}, {"fsis-a", "fsis-b"})
        finally:
            stage.close()

    def test_typed_business_names_join_operating_site_signals_without_promoting_brands(self):
        def row(source_id, record_key, identifier, role="legal"):
            return _observed_from_row({
                "source_id": source_id,
                "source_record_key": record_key,
                "contract_version": "graph-candidate-handoff-v1",
                "location_role": "operating",
                "facilities": [{"source_identifier": {
                    "identifier_type": "site_registration", "value": identifier,
                }}],
                # These are field names present in the full private corpus;
                # the asserted business name intentionally is not duplicated
                # in normalized_values.name.
                "normalized_values": {
                    "address": "100 Example Road",
                    "city": "Exampletown",
                    "postal_code": "12345",
                },
                "name_assertions": [{
                    "value": "North Star Foods Limited",
                    "source_field": "facility_display_name",
                    "role": role,
                }],
            })

        left = row("test.registry_a", "record-a", "A-001")
        right = row("test.registry_b", "record-b", "B-002")
        self.assertEqual(left.signals["name"], "north star foods limited")
        candidates, counters = _iter_probabilistic_candidates([left, right])
        emitted = list(candidates)
        self.assertEqual(counters["pairs_emitted"], 1)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(set(emitted[0]["contributing_features"]), {"address", "city", "name", "postal"})
        self.assertFalse(emitted[0]["automatic_merge"])

        brand_left = row("test.brand_a", "record-c", "C-003", role="brand")
        brand_right = row("test.brand_b", "record-d", "D-004", role="brand")
        self.assertNotIn("name", brand_left.signals)
        brand_candidates, brand_counters = _iter_probabilistic_candidates([brand_left, brand_right])
        self.assertEqual(list(brand_candidates), [])
        self.assertEqual(brand_counters["pairs_emitted"], 0)

    def test_matcher_stage_keeps_same_native_record_key_separate_by_artifact_version(self):
        def write_version(folder, source_id, native_key, identifier, artifact_sha):
            root = self.root / folder
            candidate = build_graph_candidate({
                "source_id": source_id,
                "source_record_key": native_key,
                "source_row": 1,
                "source_values": {"id": identifier},
                "normalized": {"establishment_id": identifier},
            }, artifact_sha256=artifact_sha, observed_at="2026-01-01T00:00:00Z")
            candidate["location_role"] = "operating"
            candidate["normalized_values"] = {
                "address": "100 Example Road",
                "city": "Exampletown",
                "postal_code": "12345",
            }
            candidate["name_assertions"] = [{
                "value": "North Star Foods Limited",
                "source_field": "facility_display_name",
                "role": "business",
            }]
            candidate["facilities"][0]["source_identifier"].update({
                "identifier_type": "site_registration", "value": identifier,
            })
            validate_graph_candidate(candidate)
            payload = canonical_json_bytes(candidate)
            root.mkdir(parents=True, exist_ok=True)
            (root / "records.jsonl").write_bytes(payload)
            manifest = {
                "source_id": source_id,
                "contract_version": "graph-candidate-handoff-v1",
                "source_artifact_sha256": artifact_sha,
                "records_sha256": hashlib.sha256(payload).hexdigest(),
                "candidate_count": 1,
                "release_state": "not-created",
                "publication_state": "private-candidate",
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        first = self.root / "version-a"
        second = self.root / "version-b"
        corroborator = self.root / "other-source"
        write_version("version-a", "test.registry_a", "same-native-key", "A-001", "a" * 64)
        write_version("version-b", "test.registry_a", "same-native-key", "A-002", "b" * 64)
        write_version("other-source", "test.registry_b", "other-key", "B-001", "c" * 64)

        stage = _MatcherStage()
        try:
            stage.add_handoff(first)
            stage.add_handoff(second)
            stage.add_handoff(corroborator)
            stage.add_handoff(corroborator)  # identical upstream copy is not a second observation
            staged = list(stage.observed())
            self.assertEqual(sum(bool(item.signals.get("name")) for item in staged), 3)
            self.assertEqual(sum(bool(item.shared_business_name_aliases) for item in staged), 3)
            self.assertTrue(all({"address", "city", "postal"}.issubset(item.signals) for item in staged))
            self.assertTrue(all(item.facility_ids and item.facility_endpoint_ids for item in staged))
            summary = stage.build_candidates()
            self.assertEqual(summary["pairs_emitted"], 2, summary)
            self.assertEqual(summary["rows_staged"], 3)
            first_manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
            second_manifest = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
            candidate_input = {"source_id": "test.registry_a", "source_record_key": "same-native-key"}
            first_edges = list(stage.edge_builder(candidate_input, first_manifest))
            second_edges = list(stage.edge_builder(candidate_input, second_manifest))
            self.assertEqual({item["method"] for item in first_edges}, {
                "multi_signal_intersection", "exact_declared_business_name_equality",
            })
            self.assertEqual({item["method"] for item in second_edges}, {
                "multi_signal_intersection", "exact_declared_business_name_equality",
            })  # distinct support versions retain separate, stable candidates
            self.assertNotEqual({item["candidate_digest"] for item in first_edges},
                                {item["candidate_digest"] for item in second_edges})
            self.assertEqual(first_edges[0]["endpoints"][0]["source_record_key"], "same-native-key")
            self.assertEqual(first_edges[0]["endpoints"][0]["artifact_sha256"], "a" * 64)
            self.assertEqual(second_edges[0]["endpoints"][0]["source_record_key"], "same-native-key")
            self.assertEqual(second_edges[0]["endpoints"][0]["artifact_sha256"], "b" * 64)
        finally:
            stage.close()


if __name__ == "__main__":
    unittest.main()
