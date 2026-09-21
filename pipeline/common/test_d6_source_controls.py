from __future__ import annotations

import json
import unittest
from pathlib import Path

from pipeline.common.d6_source_controls import (
    CONTROL_VERSION,
    derive_known_connection_controls,
    write_control_manifest,
)
from pipeline.common.graph_candidates import build_identifier_graph_candidate
from pipeline.contracts.graph_candidate_handoff import validate_graph_candidate
from pipeline.sources.us.aphis.adapter import AphisPublicSearchAdapter


class D6SourceControlTests(unittest.TestCase):
    def test_multiple_authoritative_identifiers_emit_nodes_and_signal_bundle(self):
        candidate = build_identifier_graph_candidate(
            source_id="it.853-2004",
            source_record_key="it-row-1",
            source_values={"p_iva": "IT-1", "cod_fiscale": "CF-1"},
            facility_identifier=("eu_recognition_number", "IT-FAC-1"),
            organization_identifier=None,
            organization_identifiers=[("italian_vat", "IT-1"), ("italian_fiscal_code", "CF-1")],
            observed_at="2026-01-01T00:00:00Z",
            artifact_sha256="a" * 64,
        )
        validate_graph_candidate(candidate)
        self.assertEqual(len(candidate["organizations"]), 2)
        self.assertEqual(len(candidate["relationships"]), 2)
        self.assertTrue(all(item["confidence"] is None for item in candidate["relationships"]))
        self.assertTrue(all(item["connection_type"] == "exact" for item in candidate["relationships"]))

    def test_aphis_fixture_emits_evidence_event_exact_links_only_within_aphis(self):
        fixture = Path(__file__).parents[1] / "sources" / "us" / "aphis" / "fixtures" / "registrations.csv"
        result = AphisPublicSearchAdapter().parse_bytes(fixture.read_bytes())
        self.assertTrue(result["accepted"])
        links = result["accepted"][0]["normalized"]["linkage_candidates"]
        self.assertTrue(links)
        self.assertTrue(all(link["target_source_id"] == "us.aphis" for link in links))
        self.assertTrue(all(link["match_method"] == "exact_source_identifier" for link in links))

    def test_known_source_assertion_is_positive_and_aphis_fsis_is_negative(self):
        controls = derive_known_connection_controls(
            graph_candidates={
                "it.853-2004": [{
                    "source_record_key": "it-row-1",
                    "relationships": [{"relationship_type": "operator", "assertion_status": "asserted"}],
                }],
            },
            evidence_rows={
                "us.aphis": [{
                    "source_record_key": "registrations|certificate=APHIS-1",
                    "normalized": {
                        "source_observation_key": "registrations|certificate=APHIS-1",
                        "linkage_candidates": [{
                            "target_source_id": "us.aphis",
                            "identifier_type": "certificate_number",
                            "value": "APHIS-1",
                        }],
                    },
                }],
            },
            facility_records={"us.fsis": [{"normalized": {"establishment_id": "FSIS-1"}}]},
        )
        self.assertEqual(controls["schema_version"], CONTROL_VERSION)
        self.assertEqual(controls["positive_controls"]["count"], 2)
        self.assertEqual(controls["negative_controls"]["count"], 1)
        self.assertEqual(controls["invariants"]["automatic_aphis_fsis_links"], 0)
        self.assertFalse(controls["invariants"]["control_payloads_included"])

    def test_distinct_source_identifiers_make_a_negative_control(self):
        controls = derive_known_connection_controls(facility_records={
            "dk.smiley": [
                {"normalized": {"establishment_id": "DK-1"}},
                {"normalized": {"establishment_id": "DK-2"}},
            ],
        })
        self.assertEqual(controls["negative_controls"]["count"], 1)
        self.assertEqual(
            controls["negative_controls"]["by_method"],
            {"distinct_source_identifiers_do_not_match": 1},
        )

    def test_manifest_is_row_free_and_rejects_payload_keys(self):
        manifest = derive_known_connection_controls()
        path = Path(__file__).with_name(".d6-control-test.json")
        try:
            path = write_control_manifest(path, manifest)
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("source_values", json.dumps(written))
        finally:
            path.unlink(missing_ok=True)
        with self.assertRaises(ValueError):
            write_control_manifest(Path("ignored.json"), {"raw_rows": [{"secret": "x"}]})


if __name__ == "__main__":
    unittest.main()
