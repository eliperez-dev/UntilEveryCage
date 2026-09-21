import copy
import json
import tempfile
import unittest
from pathlib import Path

from .current_identity import build_current_identity_graph, write_current_identity_graph


ROOT = Path(__file__).parent


def load_fixture():
    return json.loads((ROOT / "fixtures" / "current_identity.json").read_text(encoding="utf-8"))


class CurrentIdentityGraphTests(unittest.TestCase):
    def build(self, payload=None):
        payload = payload or load_fixture()
        return build_current_identity_graph(
            aphis_records=payload["aphis"],
            fsis_records=payload["fsis"],
            fsis_observations=payload["fsis_observations"],
            provenance=payload["provenance"],
        )

    def test_exact_official_ids_link_each_observation_family(self):
        graph = self.build()
        self.assertEqual(len(graph["candidates"]), 3)
        self.assertEqual({candidate["match_method"] for candidate in graph["candidates"]}, {"exact_official_identifier"})
        self.assertEqual({candidate["relationship_type"] for candidate in graph["candidates"]}, {"observation_of_registration", "observation_of_establishment"})
        for candidate in graph["candidates"]:
            self.assertEqual(candidate["publication"]["publication_status"], "not_eligible")
            self.assertEqual(candidate["review_state"], "review_required")
            self.assertTrue(candidate["evidence"]["provenance"])
        aphis_link = next(candidate for candidate in graph["candidates"] if candidate["right"]["profile"] == "annual_reports")
        self.assertEqual(set(aphis_link["evidence"]["provenance"]), {"us.aphis:registrations", "us.aphis:annual_reports"})
        self.assertEqual(len(graph["entities"]), 5)
        self.assertTrue(all(candidate["confidence_explanation"] for candidate in graph["candidates"]))

    def test_row_specific_provenance_overrides_profile_fallback(self):
        payload = load_fixture()
        registration = payload["aphis"]["registrations"][0]
        report = payload["aphis"]["annual_reports"][0]
        payload["provenance"][("us.aphis", "registrations", registration["source_record_key"])] = {
            "artifact_sha256": "c" * 64,
            "source_url": "https://example.invalid/registration-page.csv",
            "retrieved_at_utc": "2026-09-19T00:00:00Z",
        }
        payload["provenance"][("us.aphis", "annual_reports", report["source_record_key"])] = {
            "artifact_sha256": "d" * 64,
            "source_url": "https://example.invalid/annual-page.csv",
            "retrieved_at_utc": "2026-09-19T00:01:00Z",
        }
        graph = self.build(payload)
        link = next(item for item in graph["candidates"] if item["right"]["profile"] == "annual_reports")
        self.assertEqual(link["evidence"]["provenance"]["us.aphis:registrations"]["artifact_sha256"], "c" * 64)
        self.assertEqual(link["evidence"]["provenance"]["us.aphis:annual_reports"]["artifact_sha256"], "d" * 64)

    def test_amended_annual_reports_remain_source_versioned_and_linkable(self):
        payload = load_fixture()
        amendment = copy.deepcopy(payload["aphis"]["annual_reports"][0])
        amendment["source_record_key"] = "amendments:00-B-TEST-001:2025:2"
        amendment["normalized"]["evidence_type"] = "amendments"
        payload["aphis"]["annual_reports"].append(amendment)
        graph = self.build(payload)
        amendment_links = [candidate for candidate in graph["candidates"] if candidate["right"]["profile"] == "amendments"]
        self.assertEqual(len(amendment_links), 1)
        self.assertEqual(amendment_links[0]["assertion_status"], "candidate")
        self.assertTrue(any(entity["entity_type"] == "amendments" for entity in graph["entities"]))

    def test_amendment_row_uses_exact_annual_artifact_provenance_before_profile_fallback(self):
        payload = load_fixture()
        amendment = copy.deepcopy(payload["aphis"]["annual_reports"][0])
        amendment["source_record_key"] = "amendments:00-B-TEST-001:2025:2"
        amendment["normalized"]["evidence_type"] = "amendments"
        payload["aphis"]["annual_reports"].append(amendment)
        payload["provenance"][("us.aphis", "annual_reports", amendment["source_record_key"])] = {
            "artifact_sha256": "e" * 64,
            "source_url": "https://example.invalid/annual-page.csv",
            "retrieved_at_utc": "2026-09-19T00:02:00Z",
        }
        graph = self.build(payload)
        link = next(item for item in graph["candidates"] if item["right"]["profile"] == "amendments")
        self.assertEqual(link["evidence"]["provenance"]["us.aphis:amendments"]["artifact_sha256"], "e" * 64)

    def test_same_name_different_address_is_not_a_join(self):
        payload = load_fixture()
        payload["aphis"]["annual_reports"][0]["normalized"]["certificate_number"] = ""
        payload["aphis"]["annual_reports"][0]["normalized"]["customer_number"] = ""
        payload["aphis"]["annual_reports"][0]["source_values"]["Address Line 1"] = "99 Other Way"
        graph = self.build(payload)
        self.assertEqual(len([c for c in graph["candidates"] if c["right"]["profile"] == "annual_reports"]), 0)

    def test_conflicting_official_ids_block_name_address_rescue(self):
        payload = load_fixture()
        report = payload["aphis"]["annual_reports"][0]
        report["normalized"]["certificate_number"] = "00-R-CONFLICT"
        report["normalized"]["customer_number"] = "9999"
        graph = self.build(payload)
        self.assertFalse(any(candidate["match_method"] == "alternate_name_address_exact" for candidate in graph["candidates"]))
        self.assertTrue(any(item["reason"] == "conflicting_official_identifiers" for item in graph["quarantined"]))

    def test_unrelated_official_ids_are_not_false_conflicts(self):
        payload = load_fixture()
        report = payload["aphis"]["annual_reports"][0]
        report["normalized"]["certificate_number"] = "00-R-UNRELATED"
        report["normalized"]["customer_number"] = "999999"
        report["normalized"]["account_name"] = "Unrelated report"
        report["source_values"]["Account Name"] = "Unrelated report"
        graph = self.build(payload)
        annual = [item for item in graph["quarantined"] if item["right"]["profile"] == "annual_reports"]
        self.assertFalse(any(item.get("reason") == "conflicting_official_identifiers" for item in annual))
        self.assertFalse(any(item["right"]["profile"] == "annual_reports" for item in graph["candidates"]))

    def test_dated_inspections_sharing_an_id_are_not_ambiguous(self):
        payload = load_fixture()
        second = copy.deepcopy(payload["aphis"]["inspections"][0])
        second["source_record_key"] = "inspections:00-R-TEST-001:2026-03-01"
        second["normalized"]["status_date"] = "2026-03-01"
        payload["aphis"]["inspections"].append(second)
        graph = self.build(payload)
        inspections = [item for item in graph["candidates"] if item["right"]["profile"] == "inspections"]
        self.assertEqual(len(inspections), 2)
        self.assertFalse(any(item.get("reason") == "ambiguous_official_identifier" for item in graph["quarantined"]))

    def test_ambiguous_alternate_match_is_quarantined(self):
        payload = load_fixture()
        duplicate = copy.deepcopy(payload["aphis"]["annual_reports"][0])
        duplicate["source_record_key"] = "annual_reports:00-B-TEST-001:2024"
        duplicate["normalized"]["certificate_number"] = ""
        duplicate["normalized"]["customer_number"] = ""
        payload["aphis"]["annual_reports"].append(duplicate)
        payload["aphis"]["annual_reports"][0]["normalized"]["certificate_number"] = ""
        payload["aphis"]["annual_reports"][0]["normalized"]["customer_number"] = ""
        graph = self.build(payload)
        self.assertTrue(any(item["reason"] == "ambiguous_alternate_name_address" for item in graph["quarantined"]))
        self.assertFalse(any(candidate["match_method"] == "alternate_name_address_exact" for candidate in graph["candidates"]))

    def test_unique_name_and_address_is_only_a_review_candidate(self):
        payload = load_fixture()
        report = payload["aphis"]["annual_reports"][0]
        report["normalized"]["certificate_number"] = ""
        report["normalized"]["customer_number"] = ""
        graph = self.build(payload)
        alternate = [candidate for candidate in graph["candidates"] if candidate["match_method"] == "alternate_name_address_exact"]
        self.assertEqual(len(alternate), 1)
        self.assertEqual(alternate[0]["confidence"], 0.45)
        self.assertEqual(alternate[0]["review_state"], "review_required")
        self.assertEqual(alternate[0]["assertion_status"], "candidate")

    def test_missing_provenance_is_quarantined_without_raw_payload(self):
        payload = load_fixture()
        del payload["provenance"]["us.fsis.observations"]
        graph = self.build(payload)
        candidates = [c for c in graph["quarantined"] if c["right"]["profile"] == "fsis_observations"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["assertion_status"], "quarantined")
        self.assertEqual(candidates[0]["quarantine_reason"], "missing_or_invalid_provenance")
        self.assertNotIn("source_values", json.dumps(candidates[0]))

    def test_suppressed_records_never_enter_accepted_candidates(self):
        payload = load_fixture()
        payload["aphis"]["inspections"][0]["normalized"]["privacy_gate"] = "suppressed"
        graph = self.build(payload)
        inspection = [c for c in graph["quarantined"] if c["right"]["profile"] == "inspections"][0]
        self.assertEqual(inspection["assertion_status"], "quarantined")
        self.assertEqual(inspection["quarantine_reason"], "suppressed_or_restricted")

    def test_write_is_idempotent_and_private(self):
        graph = self.build()
        with tempfile.TemporaryDirectory() as directory:
            first = write_current_identity_graph(Path(directory) / "one", graph)
            second = write_current_identity_graph(Path(directory) / "two", graph)
            self.assertEqual(first["idempotency_key"], second["idempotency_key"])
            self.assertEqual(first["candidate_sha256"], second["candidate_sha256"])
            self.assertEqual(first["storage_state"], "private")
            self.assertFalse(first["publication_status"] == "released")
            self.assertEqual(
                (Path(directory) / "one" / "candidate" / "identity-links.jsonl").read_bytes(),
                (Path(directory) / "two" / "candidate" / "identity-links.jsonl").read_bytes(),
            )

    def test_write_rejects_a_promoted_or_non_test_only_graph(self):
        graph = self.build()
        graph["manifest"]["test_only"] = False
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                write_current_identity_graph(Path(directory) / "blocked", graph)


if __name__ == "__main__":
    unittest.main()
