from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from pipeline.common.evidence_sink import import_private_evidence
from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner, RefreshRunnerError
from pipeline.contracts.refresh import AdapterCapabilities, RegisteredAdapter, RefreshRequest
from pipeline.sources.us.evidence import EvidenceEventAdapter


class EvidenceEventTests(unittest.TestCase):
    def _root(self, name: str) -> Path:
        root = Path(__file__).parents[3] / "data" / "staging" / f".d3-evidence-{name}"
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def test_mixed_facility_and_evidence_plan_keeps_kinds_separate(self):
        root = self._root("mixed")
        catalog = RefreshCatalog()
        class FixtureFacility:
            source_id = "fixture.facility"
            adapter_version = "fixture-facility-v1"
            source_kind = "facility_master"
            def refresh(self, **_kwargs):
                return {"input_rows": 1, "normalized_rows": 1, "quarantined_rows": 0}
        facility = FixtureFacility()
        facility_caps = AdapterCapabilities(
            source_id=facility.source_id, adapter_version=facility.adapter_version,
            schema_version="fixture-facility-v1", acquisition="fixture",
            geocoding="disabled", publication="human_gate_required",
            source_kind="facility_master",
        )
        catalog.sources[facility.source_id] = {"source_id": facility.source_id, "adapter_status": "implemented_partial"}
        catalog.capabilities[facility.source_id] = facility_caps
        catalog.adapters[facility.source_id] = RegisteredAdapter(facility_caps, facility)
        result = RefreshRunner(catalog).run(RefreshRequest(
            source_ids=("fixture.facility", "us.aphis", "us.inspections"),
            mode="fixture", output_root=root,
        ))
        self.assertEqual(result["exit_status"], "ok")
        self.assertEqual(
            [(item["source_id"], item["source_kind"]) for item in result["results"]],
            [("fixture.facility", "facility_master"), ("us.aphis", "evidence_event"), ("us.inspections", "evidence_event")],
        )
        self.assertEqual(result["results"][1]["summary"]["facility_identity_state"], "not_asserted")
        self.assertFalse(result["results"][1]["summary"]["public_surfaces"]["api"])

    def test_evidence_sink_is_idempotent_and_private(self):
        root = self._root("sink")
        result = RefreshRunner(RefreshCatalog()).run(RefreshRequest(
            source_ids=("us.inspections",), mode="fixture", output_root=root,
        ))
        self.assertEqual(result["exit_status"], "ok")
        handoff = root / result["results"][0]["source_id"]
        # The deterministic run ID is kept in the plan directory, not source ID.
        run_dir = next(root.glob("refresh-*/sources/us.inspections/evidence-handoff"))
        first = import_private_evidence(run_dir)
        second = import_private_evidence(run_dir)
        self.assertEqual(first["status"], "completed")
        self.assertEqual(second["status"], "already_present")
        self.assertEqual(second["inserted_events"], 0)
        self.assertFalse(second["public_exposure"])

    def test_facility_adapter_cannot_register_as_evidence(self):
        class FacilityAdapter:
            source_id = "test.source"
            adapter_version = "test-v1"
            source_kind = "facility_master"

            def refresh(self, **_kwargs):
                return {}

        catalog = RefreshCatalog.__new__(RefreshCatalog)
        catalog.sources = {"test.source": {"source_id": "test.source", "adapter_status": "implemented_partial"}}
        catalog.capabilities = {}
        catalog.adapters = {}
        with self.assertRaises(RefreshRunnerError):
            catalog.register(FacilityAdapter(), AdapterCapabilities(
                source_id="test.source", adapter_version="test-v1", schema_version="test-v1",
                acquisition="fixture", geocoding="disabled", publication="human_gate_required",
                source_kind="evidence_event",
            ))

    def test_sink_rejects_facility_handoff_schema(self):
        root = self._root("reject")
        (root / "manifest.json").write_text(json.dumps({
            "contract_version": "candidate-handoff-v1", "entity_scope": "facility_master",
            "normalized_sha256": "bad", "normalized_rows": 0,
        }), encoding="utf-8")
        (root / "records.jsonl").write_text("", encoding="utf-8")
        with self.assertRaises(ValueError):
            import_private_evidence(root)


if __name__ == "__main__":
    unittest.main()
