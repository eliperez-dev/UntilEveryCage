from __future__ import annotations

import shutil
import unittest
from pathlib import Path
import hashlib

from .first_wave import FIRST_WAVE, FirstWaveRefreshAdapter, descriptor_for, readiness_report, run_fixture


class FirstWaveDescriptorTests(unittest.TestCase):
    def test_expected_sources_are_registered(self):
        self.assertEqual(
            {item.source_id for item in FIRST_WAVE},
            {"dk.smiley", "be.locations", "ca.ontario.meat-plants", "ca.cfia.federal-meat", "fsa_approved_establishments", "fr.dgal.section-i", "fr.dgal.section-ii", "it.853-2004", "it.1069-2009", "es.cat.feed-sandach", "au.npi.facilities", "au.sa.epa.licensed-activities", "br.sif.registered"},
        )

    def test_fsa_descriptor_version_matches_the_pinned_adapter_contract(self):
        from .uk.fsa_approved.adapter import CONFIG

        descriptor = next(item for item in FIRST_WAVE if item.source_id == "fsa_approved_establishments")
        self.assertEqual(descriptor.adapter_version, CONFIG["adapter_version"])
        self.assertEqual(descriptor.schema_version, CONFIG["contract_version"])

    def test_descriptors_are_fixture_and_local_artifact_ready(self):
        for item in FIRST_WAVE:
            self.assertEqual(item.readiness()["fixture_ready"], bool(item.fixture_paths))
            self.assertTrue(all(path.is_file() for path in item.fixture_paths), item.source_id)
            self.assertEqual(item.readiness()["local_artifact_ready"], item.source_id != "it.1069-2009")
            self.assertTrue(item.readiness()["review_required"])
            self.assertEqual(item.readiness()["publication"], "human_gate_required")

    def test_fixture_runs_emit_private_aggregate_and_candidate_handoff(self):
        # The hosted Windows runner may deny ACL changes under temporary
        # directories. Use a fixed disposable workspace directory instead.
        directory = Path(__file__).resolve().parents[2] / ".d2-adapter-test"
        directory.mkdir(exist_ok=True)
        try:
            try:
                for item in FIRST_WAVE:
                    if not item.fixture_paths:
                        continue
                    result = run_fixture(item.source_id, Path(directory) / item.source_id.replace(".", "_"))
                    self.assertEqual(result["status"], "candidate-ready", item.source_id)
                    self.assertEqual(result["publication_state"], "human-gate-required", item.source_id)
                    self.assertFalse(result["release_promoted"], item.source_id)
                    self.assertTrue(result["candidate_handoff"], item.source_id)
                    self.assertTrue(result["health_written"], item.source_id)
                    self.assertIsInstance(result["input_rows"], int)
                    self.assertNotIn("source_values", result)
            except PermissionError as error:
                self.skipTest(f"Windows temporary-file ACL blocks atomic private-run test: {error}")
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_descriptor_lookup_fails_closed(self):
        with self.assertRaises(KeyError):
            descriptor_for("uk.fsa.approved-establishments")

    def test_canada_refresh_summary_reports_provenance_and_queue_counts(self):
        directory = Path(__file__).resolve().parents[2] / ".d2-canada-refresh-adapter-test"
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(exist_ok=True)
        try:
            descriptor = descriptor_for("ca.cfia.federal-meat")
            fixture = descriptor.fixture_paths[0]
            result = FirstWaveRefreshAdapter(descriptor).refresh(
                mode="local-artifact", run_dir=directory / "run", artifact=fixture, options={})
            self.assertEqual(result["source_artifact"]["sha256"], hashlib.sha256(fixture.read_bytes()).hexdigest())
            self.assertEqual(result["source_artifact"]["byte_size"], fixture.stat().st_size)
            self.assertEqual(result["geocode_queue"]["records_queued"], 2)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_readiness_report_keeps_live_state_separate(self):
        report = readiness_report()
        self.assertEqual(len(report), 13)
        italy = next(item for item in report if item["source_id"] == "it.853-2004")
        self.assertEqual(italy["private_pipeline"], "one_action_preview_import_ready")
        ready = {"it.853-2004", "it.1069-2009", "es.cat.feed-sandach", "au.sa.epa.licensed-activities", "au.npi.facilities", "fsa_approved_establishments", "br.sif.registered", "ca.ontario.meat-plants"}
        self.assertTrue(all(item["private_pipeline"] == "one_action_preview_import_ready" for item in report if item["source_id"] in ready))
        self.assertTrue(all(item["private_pipeline"] == "fixture_contract_ready" for item in report if item["source_id"] not in ready))
        self.assertTrue(all(item["publication"] == "human_gate_required" for item in report))
        self.assertTrue({item["live_acquisition"] for item in report} <= {"verified", "bounded_private_fetch"})


if __name__ == "__main__":
    unittest.main()
