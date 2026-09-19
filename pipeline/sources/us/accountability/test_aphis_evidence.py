import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.sources.us.aphis.adapter import AphisPublicSearchAdapter

from .aphis_evidence import (
    PACKET_VERSION,
    build_packet,
    verify_retained_artifacts,
    write_packet,
)


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
        self.assertEqual(packet["links"][0]["matched_identifiers"]["aphis_certificate_number"], "87-R-0001")
        self.assertEqual(packet["link_quarantine"][0]["reason"], "conflicting_official_identifiers")

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


if __name__ == "__main__":
    unittest.main()
