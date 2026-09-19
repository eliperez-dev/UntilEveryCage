import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pipeline.sources.us.aphis.adapter import AphisPublicSearchAdapter

from .aphis_evidence import (
    PACKET_VERSION,
    build_packet,
    verify_retained_artifacts,
    run_from_wave2,
    run_from_handoffs,
    write_packet,
)
from .aphis_wave2 import run_wave2


ROOT = Path(__file__).parents[1] / "aphis"


class AphisEvidencePacketTests(unittest.TestCase):
    def _records(self):
        adapter = AphisPublicSearchAdapter()
        records = {}
        for profile in ("registrations", "annual_reports", "inspections"):
            result = adapter.parse_bytes((ROOT / "fixtures" / f"{profile}.csv").read_bytes())
            records[profile] = result["accepted"]
        return records

    def test_year_is_a_year_period_and_dates_are_not_synthetic_events(self):
        packet = build_packet(
            records_by_profile=self._records(),
            provenance={
                ("us.aphis", profile): {
                    "artifact_sha256": "a" * 64,
                    "source_url": "https://example.invalid/" + profile,
                    "retrieved_at_utc": "2026-09-18T00:00:00Z",
                }
                for profile in ("registrations", "annual_reports", "inspections")
            },
        )
        annual = next(item for item in packet["timeline"] if item.get("profile") == "annual_reports")
        inspection = next(item for item in packet["timeline"] if item.get("profile") == "inspections")
        self.assertEqual(annual["period"], {"start": "2025-01-01", "end": "2025-12-31", "precision": "year"})
        self.assertEqual(inspection["period"]["precision"], "day")
        self.assertNotEqual(annual["period"]["precision"], "day")

    def test_expected_gap_failure_and_document_unavailable_remain_visible(self):
        records = self._records()
        key = records["annual_reports"][0]["source_record_key"]
        packet = build_packet(
            records_by_profile=records,
            provenance={},
            expected_rows={"inspections": 4},
            input_failures=[{"profile": "annual_reports", "state": "failed", "failure": "artifact_missing"}],
            document_refs={key: [{"document_key": "annual-report-2025", "captured": False, "url": "https://signed.invalid/secret"}]},
        )
        states = {item["state"] for item in packet["timeline"]}
        self.assertTrue({"not_observed", "failed", "document_not_captured"}.issubset(states))
        serialized = json.dumps(packet["row_free_summary"])
        self.assertNotIn("signed.invalid", serialized)
        self.assertEqual(packet["row_free_summary"]["publication_status"], "not_eligible")

    def test_duplicate_source_keys_are_quarantined_and_links_preserve_conflicts(self):
        records = self._records()
        duplicate = dict(records["inspections"][0])
        records["inspections"].append(duplicate)
        key = records["registrations"][0]["source_record_key"]
        graph = {
            "candidates": [{"candidate_id": "candidate-1", "left": {"source_record_key": key},
                            "right": {"source_record_key": records["annual_reports"][0]["source_record_key"]},
                            "matched_identifiers": {"aphis_certificate_number": "87-R-0001"},
                            "review_state": "review_required", "assertion_status": "candidate"}],
            "quarantined": [{"candidate_id": "candidate-2", "left_source_record_key": key,
                              "right_source_record_key": "inspections:conflict", "reason": "conflicting_official_identifiers"}],
        }
        packet = build_packet(records_by_profile=records, provenance={}, graph=graph, registration_key=key)
        self.assertTrue(any(item["state"] == "quarantined" and item.get("reason") == "duplicate_source_record_key" for item in packet["timeline"]))
        self.assertFalse(packet["links"])
        reasons = {item["reason"] for item in packet["link_quarantine"]}
        self.assertIn("link_missing_or_invalid_provenance", reasons)
        self.assertIn("conflicting_official_identifiers", reasons)

    def test_manifest_hash_and_size_fail_visibly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "annual.csv"
            artifact.write_bytes(b"retained")
            manifest = root / "manifest.json"
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            manifest.write_text(json.dumps({"profiles": {"annual_reports": {"artifacts": [{
                "artifact": artifact.name, "path": str(artifact), "sha256": digest, "byte_size": 99,
            }]}}}), encoding="utf-8")
            result = verify_retained_artifacts(manifest)
            self.assertFalse(result["all_verified"])
            self.assertEqual(result["artifacts"][0]["failure"], "artifact_size_mismatch")
            manifest.write_text(json.dumps({"profiles": {"annual_reports": {"artifacts": [{
                "artifact": artifact.name, "path": str(artifact), "sha256": digest,
            }]}}}), encoding="utf-8")
            result = verify_retained_artifacts(manifest)
            self.assertEqual(result["artifacts"][0]["failure"], "artifact_size_not_declared")
            artifact.write_bytes(b"changed")
            result = verify_retained_artifacts(manifest)
            self.assertEqual(result["artifacts"][0]["failure"], "artifact_hash_mismatch")

    def test_write_packet_has_separate_row_free_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            packet = build_packet(records_by_profile=self._records(), provenance={})
            manifest = write_packet(directory, packet)
            self.assertEqual(manifest["schema_version"], PACKET_VERSION)
            self.assertTrue((Path(directory) / "row-free-summary.json").exists())
            self.assertTrue((Path(directory) / "private" / "rows.jsonl").exists())
            self.assertNotIn("source_values", (Path(directory) / "row-free-summary.json").read_text(encoding="utf-8"))

    def test_source_local_handoffs_build_exact_private_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handoffs = {}
            records = json.loads((Path(__file__).parent / "fixtures" / "current_identity.json").read_text(encoding="utf-8"))["aphis"]
            for profile in ("registrations", "annual_reports", "inspections"):
                handoff = root / profile
                handoff.mkdir()
                payload = b"".join(
                    (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
                    for row in records[profile]
                )
                digest = hashlib.sha256(payload).hexdigest()
                (handoff / "records.jsonl").write_bytes(payload)
                (handoff / "manifest.json").write_text(json.dumps({
                    "contract_version": "us-aphis-observation-handoff-v1",
                    "source_id": "us.aphis", "profile": profile,
                    "source_url": f"https://example.invalid/{profile}",
                    "retrieved_at_utc": "2026-09-19T00:00:00Z",
                    "source_artifact_sha256": "a" * 64,
                    "normalized_rows": len(records[profile]), "normalized_sha256": digest,
                    "graph_candidate_emission": False, "auto_merge": False,
                    "release_state": "not-created", "publication_state": "private-candidate",
                    "review_state": "review_required", "privacy_gate": "pending",
                    "coordinate_gate": "review_required", "test_only": True,
                    "row_payloads_included": True,
                }), encoding="utf-8")
                handoffs[profile] = handoff
            result = run_from_handoffs(handoffs, root / "packet")
            summary = result["packet"]["row_free_summary"]
            self.assertEqual(result["input_failures"], [])
            self.assertGreater(summary["links"]["quarantined_count"], 0)
            self.assertNotIn("link_missing_or_invalid_provenance", summary["links"]["excluded_reasons"])
            self.assertEqual(summary["publication_status"], "not_eligible")

    def test_handoff_accounting_keeps_adapter_quarantine_distinct_from_missing_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = json.loads((Path(__file__).parent / "fixtures" / "current_identity.json").read_text(encoding="utf-8"))["aphis"]
            handoffs = {}
            for profile in ("registrations", "annual_reports", "inspections"):
                handoff = root / profile
                handoff.mkdir()
                payload = b"".join((json.dumps(row, sort_keys=True) + "\n").encode() for row in records[profile])
                (handoff / "records.jsonl").write_bytes(payload)
                (handoff / "manifest.json").write_text(json.dumps({
                    "contract_version": "us-aphis-observation-handoff-v1", "source_id": "us.aphis",
                    "profile": profile, "source_url": "https://example.invalid/" + profile,
                    "retrieved_at_utc": "2026-09-19T00:00:00Z", "source_artifact_sha256": "a" * 64,
                    "normalized_rows": len(records[profile]), "normalized_sha256": hashlib.sha256(payload).hexdigest(),
                    "graph_candidate_emission": False, "auto_merge": False, "release_state": "not-created",
                    "publication_state": "private-candidate", "review_state": "review_required",
                    "privacy_gate": "pending", "coordinate_gate": "review_required", "test_only": True,
                    "row_payloads_included": True,
                }), encoding="utf-8")
                handoffs[profile] = handoff
            quarantine = {"reasons": ["duplicate_observation_id"], "record": {"source_record_key": "inspections:quarantined"}}
            result = run_from_handoffs(
                handoffs, root / "packet", profile_input_rows={"inspections": len(records["inspections"]) + 1},
                quarantine_rows_by_profile={"inspections": [quarantine]},
            )
            summary = result["packet"]["row_free_summary"]
            inspections = summary["profiles"]["inspections"]
            self.assertEqual(inspections["input_rows"], len(records["inspections"]) + 1)
            self.assertEqual(inspections["quarantined_rows"], 1)
            self.assertNotIn("not_observed", summary["timeline_state_counts"])

    def test_aggregate_metadata_hash_cannot_be_link_provenance(self):
        records = self._records()
        registration_key = records["registrations"][0]["source_record_key"]
        graph = {"candidates": [{
            "candidate_id": "candidate-reviewed", "left": {"source_record_key": registration_key},
            "right": {"source_record_key": records["annual_reports"][0]["source_record_key"]},
            "matched_identifiers": {"aphis_certificate_number": "87-R-0001"},
            "review_state": "reviewed", "assertion_status": "candidate",
            "evidence": {"provenance": {
                "us.aphis:registrations": {"artifact_sha256": "a" * 64, "source_url": "https://example.invalid/r", "retrieved_at_utc": "2026-09-18T00:00:00Z"},
                "us.aphis:annual_reports": {"artifact_sha256": "b" * 64, "source_url": "https://example.invalid/a", "retrieved_at_utc": "2026-09-18T00:00:00Z"},
            }},
        }], "quarantined": []}
        packet = build_packet(
            records_by_profile=records, provenance={}, graph=graph, registration_key=registration_key,
            artifact_verification={"artifacts": [{"state": "verified", "actual_sha256": "c" * 64}]},
        )
        self.assertFalse(packet["links"])
        self.assertEqual(packet["link_quarantine"][0]["reason"], "link_missing_or_invalid_provenance")

    def test_cli_fails_closed_when_manifest_profile_disagrees_with_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "annual.csv"
            shutil.copyfile(ROOT / "fixtures" / "annual_reports.csv", artifact)
            manifest = root / "input-manifest.json"
            manifest.write_text(json.dumps({"profiles": {"registrations": {"artifacts": [{
                "artifact": artifact.name, "path": str(artifact),
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(), "byte_size": artifact.stat().st_size,
                "source_url": "https://example.invalid/registrations", "retrieved_at_utc": "2026-09-18T00:00:00Z",
            }]}}}), encoding="utf-8")
            run_dir = root / "run"
            completed = subprocess.run([
                sys.executable, "-m", "pipeline.sources.us.accountability.aphis_evidence",
                "--manifest", str(manifest), "--run-dir", str(run_dir),
            ], cwd=Path(__file__).parents[4], capture_output=True, text=True, check=True)
            output = json.loads(completed.stdout)
            summary = json.loads((run_dir / "row-free-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(output["input_failures"][0]["failure"], "manifest_profile_mismatch")
            self.assertEqual(summary["profiles"]["registrations"]["observed_rows"], 0)
            self.assertEqual(summary["profiles"]["registrations"]["coverage_state"], "failed")

    def test_documented_cli_parses_verified_exports_and_preserves_coverage_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = {}
            for profile in ("registrations", "annual_reports", "inspections"):
                source = ROOT / "fixtures" / f"{profile}.csv"
                target = root / f"ExportData_{profile}.csv"
                shutil.copyfile(source, target)
                artifacts[profile] = {"artifact": target.name, "path": str(target),
                                      "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                                      "byte_size": target.stat().st_size,
                                      "source_url": f"https://example.invalid/{profile}",
                                      "retrieved_at_utc": "2026-09-18T00:00:00Z"}
            manifest = root / "input-manifest.json"
            manifest.write_text(json.dumps({"profiles": {profile: {"artifacts": [item]} for profile, item in artifacts.items()},
                                            "expected_rows": {"inspections": 2}}), encoding="utf-8")
            run_dir = root / "run"
            completed = subprocess.run([
                sys.executable, "-m", "pipeline.sources.us.accountability.aphis_evidence",
                "--manifest", str(manifest), "--artifact-root", str(root), "--run-dir", str(run_dir),
            ], cwd=Path(__file__).parents[4], capture_output=True, text=True, check=True)
            output = json.loads(completed.stdout)
            summary = json.loads((run_dir / "row-free-summary.json").read_text(encoding="utf-8"))
            self.assertGreater(summary["profiles"]["annual_reports"]["observed_rows"], 0)
            self.assertIn("not_observed", summary["timeline_state_counts"])
            self.assertEqual(output["artifact_verification"]["artifacts"][0]["actual_sha256"], artifacts[output["artifact_verification"]["artifacts"][0]["profile"]]["sha256"])
            self.assertNotEqual(output["artifact_verification"]["artifacts"][0]["actual_sha256"], "")

    def test_wave2_replay_verifies_input_manifest_and_uses_row_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_root = root / "input"
            input_root.mkdir()
            (input_root / "ExportData_registrations.csv").write_text(
                "Account Name,Customer Number,Certificate Number,Registration Type,Certificate Status,Status Date\n"
                '"Synthetic Registrant","2","00-R-0002","Class R - Research Facility","Active","2026-01-01"\n',
                encoding="utf-8",
            )
            (input_root / "ExportData_annual_reports.csv").write_text(
                "Customer Number,Certificate Number,Year,Dogs,Cats\n"
                '"2","00-R-0002","2025","","1"\n',
                encoding="utf-8",
            )
            (input_root / "ExportData_inspections.csv").write_text(
                "Customer Number,Certificate Number,Inspection Date,Direct NCIs,Non-Critical NCIs,Critical NCIs,Teachable Moments,Site Name,Legal Name,License-Registration Type,City,State,Zip\n"
                '"2","00-R-0002","2026-02-01","","","","","Synthetic Site","Synthetic Registrant","Class R - Research Facility","Testville","TX","75001"\n',
                encoding="utf-8",
            )
            wave2_dir = root / "wave2"
            run_wave2(input_root=input_root, run_dir=wave2_dir)
            result = run_from_wave2(wave2_dir, root / "packet")
            summary = result["packet"]["row_free_summary"]
            self.assertGreater(summary["profiles"]["annual_reports"]["observed_rows"], 0)
            self.assertIn("not_observed", summary["timeline_state_counts"])
            hashes = [item.get("actual_sha256") for item in summary["artifact_verification"]["artifacts"]]
            self.assertTrue(all(hashes))
            self.assertNotIn("aggregate_artifact_sha256", json.dumps(summary))
            self.assertGreater(summary["links"]["quarantined_count"], 0)
            self.assertNotIn("link_missing_or_invalid_provenance", summary["links"]["excluded_reasons"])


if __name__ == "__main__":
    unittest.main()
