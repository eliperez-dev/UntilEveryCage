import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipeline.contracts.adapter_contract import SourceArtifact

from .adapter import AccountabilityContractError, REQUIRED_HEADERS, UsAccountabilityAdapter
from .refresh import refresh

ROOT = Path(__file__).parent
FIXTURE = ROOT / "fixtures" / "synthetic_link_ledger.csv"


def rows_from_fixture() -> list[dict[str, str]]:
    with FIXTURE.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def content_for(rows: list[dict[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=REQUIRED_HEADERS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


class UsAccountabilityAdapterTests(unittest.TestCase):
    def test_fixture_emits_distinct_nodes_and_provenance_complete_relationships(self):
        result = UsAccountabilityAdapter().parse_bytes(FIXTURE.read_bytes())
        self.assertEqual(result["input_rows"], 12)
        self.assertEqual(len(result["accepted"]), 12)
        self.assertEqual(len(result["quarantined"]), 0)
        self.assertEqual({row["relationship_type"] for row in result["accepted"]}, {
            "establishment_approval_for", "operates", "operator_is_legal_entity", "parent_of",
            "brand_of", "inspection_observes", "violation_observed_in", "enforcement_for",
            "laboratory_supports", "aggregate_describes",
        })
        for relation in result["accepted"]:
            self.assertTrue(relation["source_id"])
            self.assertEqual(set(relation["source_native_ids"]), {"subject", "object", "evidence"})
            self.assertTrue(relation["observation_date"])
            self.assertTrue(relation["retrieved_at_utc"])
            self.assertTrue(relation["evidence"]["url"])
            self.assertTrue(relation["evidence"]["excerpt"])
            self.assertEqual(relation["publication_gate"], "blocked")
        types = {entity["entity_type"] for entity in result["entities"]}
        self.assertTrue({"facility", "establishment_approval", "operator", "legal_entity", "parent", "brand", "inspection", "violation", "enforcement", "laboratory", "aggregate_observation"}.issubset(types))

    def test_name_only_link_is_quarantined_and_no_identity_is_inferred(self):
        rows = rows_from_fixture()
        rows[1]["match_method"] = "name_only"
        result = UsAccountabilityAdapter().parse_bytes(content_for(rows))
        self.assertIn("non_defensible_match_method", result["quarantined"][0]["reasons"])
        self.assertNotIn("candidate-relationship-", json.dumps(result["quarantined"][0]))
        self.assertEqual(len(result["accepted"]), 11)

    def test_conflicting_identifier_and_duplicate_name_are_quarantined(self):
        rows = rows_from_fixture()
        conflicting = dict(rows[1])
        conflicting["object_name"] = "A different facility name"
        rows.append(conflicting)
        duplicate_a = dict(rows[0])
        duplicate_a.update({"object_source_native_id": "FSIS-100", "object_name": "Duplicate Facility"})
        duplicate_b = dict(rows[0])
        duplicate_b.update({"object_source_native_id": "FSIS-101", "object_name": "Duplicate Facility"})
        ambiguous = dict(rows[0])
        ambiguous.update({"object_source_native_id": "FSIS-102", "object_name": "Duplicate Facility", "evidence_source_native_id": "M004", "observation_date": "2026-09-02", "match_method": "explicit_reviewed_link"})
        rows.extend((duplicate_a, duplicate_b, ambiguous))
        result = UsAccountabilityAdapter().parse_bytes(content_for(rows))
        reasons = [reason for item in result["quarantined"] for reason in item["reasons"]]
        self.assertIn("conflicting_source_identifier", reasons)
        self.assertIn("ambiguous_duplicate_name", reasons)

    def test_stale_and_suppressed_evidence_quarantine(self):
        rows = rows_from_fixture()
        rows[0]["observation_date"] = "2024-01-01"
        rows[1]["suppression_state"] = "suppressed"
        result = UsAccountabilityAdapter().parse_bytes(content_for(rows))
        reasons = [reason for item in result["quarantined"] for reason in item["reasons"]]
        self.assertIn("stale_evidence", reasons)
        self.assertIn("suppressed_or_restricted", reasons)

    def test_non_overlapping_ownership_is_retained_but_overlap_is_quarantined(self):
        rows = rows_from_fixture()
        overlap = dict(rows[1])
        overlap.update({
            "subject_source_native_id": "registrations:customer:overlap",
            "subject_name": "Synthetic Overlap Operator",
            "evidence_source_native_id": "registrations:00-B-OVERLAP",
            "valid_from": "2026-08-01",
            "valid_to": "",
        })
        rows.append(overlap)
        result = UsAccountabilityAdapter().parse_bytes(content_for(rows))
        self.assertEqual(sum(item["reasons"] == ("overlapping_ownership_conflict",) for item in result["quarantined"]), 2)
        operators = [row for row in result["accepted"] if row["relationship_type"] == "operates"]
        self.assertEqual(len(operators), 2)
        self.assertEqual({row["subject"]["source_native_id"] for row in operators}, {"registrations:customer:old", "registrations:customer:1"})

    def test_run_and_assisted_refresh_are_private_and_deterministic(self):
        raw = FIXTURE.read_bytes()
        artifact = SourceArtifact("https://example.invalid/accountability.csv", "2026-09-15T00:00:00Z", hashlib.sha256(raw).hexdigest(), len(raw), effective_date="2026-09-15", code_version="test", config_version="test")
        with tempfile.TemporaryDirectory() as directory:
            first = UsAccountabilityAdapter().run(FIXTURE, Path(directory) / "one", artifact)
            second = UsAccountabilityAdapter().run(FIXTURE, Path(directory) / "two", artifact)
            self.assertEqual(first["normalized_sha256"], second["normalized_sha256"])
            self.assertEqual(first["parsed_sha256"], second["parsed_sha256"])
            self.assertTrue(first["test_only"])
            self.assertFalse(first["graph_migration"])
            refreshed = refresh(raw_path=FIXTURE, run_dir=Path(directory) / "refresh", retrieved_at_utc="2026-09-15T00:00:00Z")
            self.assertEqual(refreshed["status"]["status"], "candidate-ready")
            packet = json.loads((Path(directory) / "refresh" / "review-packet.json").read_text(encoding="utf-8"))
            self.assertFalse(packet["row_payloads_included"])
            self.assertEqual(packet["counts"]["relationships"], 12)

    def test_schema_drift_fails_closed(self):
        with self.assertRaises(AccountabilityContractError):
            UsAccountabilityAdapter().parse_bytes(b"subject_type,object_type\nfacility,operator\n")

    def test_exact_duplicate_relationship_is_quarantined(self):
        rows = rows_from_fixture()
        rows.append(dict(rows[0]))
        result = UsAccountabilityAdapter().parse_bytes(content_for(rows))
        self.assertEqual(result["input_rows"], 13)
        self.assertEqual(len(result["accepted"]), 12)
        self.assertEqual(len(result["quarantined"]), 1)
        self.assertEqual(result["quarantined"][0]["reasons"], ("duplicate_relationship_observation",))


if __name__ == "__main__":
    unittest.main()
