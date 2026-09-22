from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from pipeline.common.d5_connection_analysis import (
    RULESET_VERSION,
    _observed_from_row,
    _iter_probabilistic_candidates,
    classify_collision_observations,
    analyze,
    iter_candidate_batches,
    iter_probabilistic_candidates,
    load_private_rows,
    read_aggregate_manifests,
    write_report,
)


class D5ConnectionAnalysisTests(unittest.TestCase):
    scratch = Path(__file__).with_name(".d5-test-work")

    @classmethod
    def setUpClass(cls):
        cls.scratch.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def row(self, source_id: str, key: str, *, name: str, city: str, postal: str, facility: str, org: str, source_kind: str = "facility_master") -> dict:
        return {
            "source_id": source_id,
            "source_kind": source_kind,
            "source_record_key": key,
            "source_values": {"safe_test_marker": "synthetic-only"},
            "source_artifact_sha256": "a" * 64,
            "normalized": {
                "establishment_id": facility,
                "name": name,
                "city": city,
                "postal_code": postal,
                "cvr": org,
            },
        }

    def test_real_shape_counts_exact_and_probabilistic_edges_without_payload(self):
        rows = [
            _observed_from_row(self.row("dk.smiley", "dk-1", name="North Foods", city="Aarhus", postal="8000", facility="DK1", org="12345678")),
            _observed_from_row(self.row("dk.smiley", "dk-2", name="North Foods", city="Aarhus", postal="8000", facility="DK2", org="12345678")),
            _observed_from_row({**self.row("it.853-2004", "it-1", name="North Foods", city="Aarhus", postal="8000", facility="IT1", org=""), "normalized": {"establishment_id": "IT1", "name": "North Foods", "city": "Aarhus", "postal_code": "8000", "p_iva": "ITVAT1"}}),
        ]
        report = analyze(manifests={}, rows=rows, sample_size=20)
        exact = report["deterministic_connections"]["counts"]
        self.assertEqual(exact["denmark_cvr_facility_organization"], 2)
        self.assertEqual(exact["italy_vat_or_fiscal_organization"], 1)
        self.assertGreaterEqual(report["probabilistic_candidates"]["count"], 1)
        self.assertEqual(report["probabilistic_candidates"]["automatic_merge_count"], 0)
        self.assertEqual(report["connectivity"]["aphis_fsis_automatic_links"], 0)
        self.assertNotIn("North Foods", json.dumps(report))
        self.assertNotIn("12345678", json.dumps(report))
        self.assertFalse(report["scope"]["row_payloads_in_report"])

    def test_aphis_and_fsis_are_separate_and_explicit_relationships_are_counted(self):
        fsis = self.row("us.fsis", "fsis-1", name="Plant", city="Austin", postal="70000", facility="FS1", org="", source_kind="facility_master")
        aphis = {
            "source_id": "us.aphis", "source_kind": "evidence_event", "source_record_key": "aphis-1",
            "source_values": {"safe_test_marker": "synthetic-only"}, "source_artifact_sha256": "b" * 64,
            "normalized": {"source_native_ids": {"certificate_number": "CERT1", "customer_number": "CUST1"}, "establishment_id": None},
        }
        cfia = {
            "source_id": "ca.cfia.federal-meat", "source_record_key": "cfia-1",
            "source_values": {"safe_test_marker": "synthetic-only"}, "source_artifact_sha256": "c" * 64,
            "facilities": [{"local_ref": "facility:1", "source_identifier": {"identifier_type": "establishment-number", "value": "CF1"}}],
            "organizations": [{"local_ref": "organization:1", "source_identifier": {"identifier_type": "operator-name", "value": "Operator"}}],
            "relationships": [{"relationship_type": "operator", "assertion_status": "asserted"}],
        }
        report = analyze(manifests={}, rows=[_observed_from_row(fsis), _observed_from_row(aphis), _observed_from_row(cfia)])
        self.assertEqual(report["connectivity"]["aphis_fsis_automatic_links"], 0)
        self.assertEqual(report["connectivity"]["aphis_fsis_review_candidates"], 0)
        self.assertEqual(report["deterministic_connections"]["counts"]["explicit_graph_relationships:ca.cfia.federal-meat"], 1)
        self.assertGreaterEqual(report["quality_metrics"]["unresolved_rows"], 1)

    def test_collision_classifier_distinguishes_repeat_fanout_conflict_malformed_and_missing(self):
        rows = [
            {"source_id": "synthetic", "source_record_key": "one", "normalized": {"establishment_id": "F1", "cvr": "ORG1"}},
            {"source_id": "synthetic", "source_record_key": "two", "normalized": {"establishment_id": "F1", "cvr": "ORG1"}},
            {"source_id": "synthetic", "source_record_key": "three", "normalized": {"establishment_id": "F2", "cvr": "ORG1"}},
            {"source_id": "synthetic", "source_record_key": "four", "normalized": {"establishment_id": "F1", "cvr": "ORG2"}},
            {"source_id": "synthetic", "source_record_key": "five", "normalized": {"establishment_id": "###", "cvr": "ORG3"}},
            {"source_id": "synthetic", "source_record_key": "six", "normalized": {"name": "no identifiers"}},
        ]
        classified = classify_collision_observations(rows)
        self.assertEqual(classified["repeated_observations"], 1)
        self.assertEqual(classified["expected_org_many_facility_fanout"], 1)
        self.assertEqual(classified["true_conflicts"], 1)
        self.assertEqual(classified["collision_count"], 1)
        self.assertEqual(classified["malformed"], 1)
        self.assertEqual(classified["missing"], 1)
        report = analyze(manifests={}, rows=[_observed_from_row(row) for row in rows])
        self.assertEqual(report["deterministic_connections"]["collision_count"], 1)
        self.assertEqual(report["deterministic_connections"]["collision_classification"]["expected_org_many_facility_fanout"], 1)

    def test_manifest_is_aggregate_only_and_latest_source_wins(self):
        directory = self.scratch / "manifest"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            first.write_text(json.dumps({"as_of_utc": "2026-09-16T00:00:00Z", "sources": [{"source_id": "dk.smiley", "input_rows": 10, "normalized_rows": 9, "quarantined_rows": 1}]}), encoding="utf-8")
            second.write_text(json.dumps({"as_of_utc": "2026-09-17T00:00:00Z", "sources": [{"source_id": "dk.smiley", "input_rows": 11, "normalized_rows": 10, "quarantined_rows": 1}]}), encoding="utf-8")
            manifests = read_aggregate_manifests([first, second])
            self.assertEqual(manifests["dk.smiley"]["input_rows"], 11)
            self.assertNotIn("raw", json.dumps(manifests).casefold())
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_private_jsonl_loader_never_emits_rows_and_report_can_be_written(self):
        directory = self.scratch / "rows"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        try:
            rows_path = Path(directory) / "rows.jsonl"
            rows_path.write_text(json.dumps(self.row("us.fsis", "fsis-1", name="Private Name", city="Town", postal="1", facility="FS1", org="")) + "\n", encoding="utf-8")
            rows = load_private_rows({"us.fsis": rows_path})
            report = analyze(manifests={}, rows=rows)
            output = Path(directory) / "report.json"
            write_report(output, report)
            text = output.read_text(encoding="utf-8")
            self.assertNotIn("Private Name", text)
            self.assertNotIn("source_values", text)
            self.assertIn(RULESET_VERSION, text)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_candidates_have_real_source_qualified_endpoints_and_no_placeholders(self):
        left = self.row("source-a", "left-1", name="Stable Name", city="Town", postal="1000", facility="A-1", org="ORG-A")
        right = self.row("source-b", "right-1", name="Stable Name", city="Town", postal="1000", facility="B-1", org="ORG-B")
        candidates = list(iter_probabilistic_candidates([_observed_from_row(right), _observed_from_row(left)]))
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual([item["source_id"] for item in candidate["endpoints"]], ["source-a", "source-b"])
        self.assertEqual([item["source_identifier"] for item in candidate["endpoints"]], ["a1", "b1"])
        self.assertTrue(all(item["identity_scope"] == "source_scoped" for item in candidate["endpoints"]))
        self.assertNotIn(":left", json.dumps(candidate))
        self.assertNotIn(":right", json.dumps(candidate))

    def test_candidate_order_is_deterministic_and_resumable(self):
        rows = []
        for index in range(6):
            rows.append(_observed_from_row(self.row(f"source-{index}", f"row-{index}", name="Same", city="Town", postal="1000", facility=f"F-{index}", org=f"O-{index}")))
        first = list(iter_probabilistic_candidates(rows))
        second = list(iter_probabilistic_candidates(list(reversed(rows))))
        self.assertEqual([item["candidate_digest"] for item in first], [item["candidate_digest"] for item in second])
        resumed = list(iter_probabilistic_candidates(rows, start_after=first[1]["candidate_digest"]))
        self.assertEqual([item["candidate_digest"] for item in resumed], [item["candidate_digest"] for item in first[2:]])
        self.assertEqual(sum(len(batch) for batch in iter_candidate_batches(rows, batch_size=2)), len(first))

    def test_ambiguous_block_is_counted_instead_of_global_truncation(self):
        rows = [_observed_from_row(self.row(f"source-{index}", f"row-{index}", name="Crowded", city="Town", postal="1000", facility=f"F-{index}", org=f"O-{index}")) for index in range(4)]
        report = analyze(manifests={}, rows=rows, max_block_size=3)
        generation = report["probabilistic_candidates"]["candidate_generation"]
        self.assertGreater(generation["blocks_ambiguous"], 0)
        self.assertEqual(report["probabilistic_candidates"]["count"], 0)
        self.assertFalse(report["probabilistic_candidates"]["candidate_generation_capped"])

    def test_iterator_has_no_global_five_thousand_candidate_cap(self):
        rows = []
        for index in range(5001):
            name = f"Facility {index}"
            rows.extend((
                _observed_from_row(self.row("source-a", f"a-{index}", name=name, city="Town", postal=str(index), facility=f"A-{index}", org=f"OA-{index}")),
                _observed_from_row(self.row("source-b", f"b-{index}", name=name, city="Town", postal=str(index), facility=f"B-{index}", org=f"OB-{index}")),
            ))
        candidates = list(iter_probabilistic_candidates(rows))
        self.assertEqual(len(candidates), 5001)
        self.assertEqual(len({item["candidate_digest"] for item in candidates}), 5001)

    def test_contradictory_address_is_retained_and_downgrades_score(self):
        left = _observed_from_row({**self.row("source-a", "left-1", name="Stable Name", city="Town", postal="1000", facility="A-1", org="ORG-A"), "normalized": {"establishment_id": "A-1", "name": "Stable Name", "city": "Town", "postal_code": "1000", "address": "Main Street", "cvr": "ORG-A"}})
        right = _observed_from_row({**self.row("source-b", "right-1", name="Stable Name", city="Town", postal="1000", facility="B-1", org="ORG-B"), "normalized": {"establishment_id": "B-1", "name": "Stable Name", "city": "Town", "postal_code": "1000", "address": "Different Street", "cvr": "ORG-B"}})
        clean = list(iter_probabilistic_candidates([left, _observed_from_row({**self.row("source-c", "right-2", name="Stable Name", city="Town", postal="1000", facility="C-1", org="ORG-A"), "normalized": {"establishment_id": "C-1", "name": "Stable Name", "city": "Town", "postal_code": "1000", "address": "Main Street", "cvr": "ORG-A"}})]))[0]
        conflict = list(iter_probabilistic_candidates([left, right]))[0]
        self.assertTrue(any(item["signal"] == "conflicting_address" for item in conflict["contradictory_evidence"]))
        self.assertLess(conflict["confidence"], clean["confidence"])
        self.assertFalse(conflict["automatic_merge"])

    def test_repeated_source_native_identifier_is_not_inferred_as_a_pair(self):
        first = _observed_from_row(self.row("source-a", "row-1", name="Stable Name", city="Town", postal="1000", facility="A-1", org="ORG-A"))
        repeat = _observed_from_row(self.row("source-a", "row-2", name="Stable Name", city="Town", postal="1000", facility="A-1", org="ORG-A"))
        iterator, counters = _iter_probabilistic_candidates([first, repeat])
        self.assertEqual(list(iterator), [])
        self.assertEqual(counters["pairs_exact_equivalent"], 1)


if __name__ == "__main__":
    unittest.main()
