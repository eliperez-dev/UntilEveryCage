import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.sources.us.aphis.preview import AphisPreviewError, project_registration
from pipeline.taxonomy_crosswalk import project_observation


ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "scripts" / "maintenance" / "import-aphis-research-preview.py"
SPEC = importlib.util.spec_from_file_location("aphis_preview", SCRIPT)
assert SPEC and SPEC.loader
PREVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREVIEW)


def _record(registration_type="Class R - Research Facility"):
    return {
        "source_id": "us.aphis", "source_row": 2, "source_record_key": "registrations:synthetic",
        "source_values": {"Account Name": "Synthetic Lab", "Customer Number": "22", "Certificate Number": "87-R-0022",
                          "Registration Type": registration_type, "Certificate Status": "Active", "Status Date": "2025-10-01",
                          "Address Line 1": "100 Synthetic Way", "Address Line 2": "Suite 4", "City-State-Zip": "Exampletown TX 78701", "County": "Example"},
        "normalized": {"profile": "registrations", "registration_or_license_type": registration_type, "status": "Active", "status_date": "2025-10-01",
                       "source_native_ids": {"aphis_license_number": "87-R-0022"},
                       "canonical_name": "Synthetic Lab", "dba_names": [], "mailing_city": "Exampletown", "mailing_state": "TX"},
    }


class AphisPreviewTests(unittest.TestCase):
    def test_explicit_native_classes_are_projected_as_private_directory_evidence(self):
        projected = project_registration(_record())
        normalized = projected["normalized"]
        self.assertEqual(normalized["aphis_registration_class"], "Class R")
        self.assertEqual(normalized["source_status"], "active_list_membership")
        self.assertEqual(normalized["private_location_evidence"]["city"], "Exampletown")
        taxonomy = project_observation(projected)
        self.assertEqual(taxonomy["taxonomy_display_category"], "research_and_animal_use")
        self.assertEqual(taxonomy["taxonomy_mapping_method"], "direct")

    def test_all_supported_native_classes_are_retained(self):
        for value in ("Class A - Breeder", "Class B - Dealer", "Class C - Exhibitor", "Class F - Federal Research Facility", "Class G - Agricultural Research Facility", "Class H - Intermediate Handler", "Class R - Research Facility", "Class T - Carrier", "Class V - VA Hospital"):
            with self.subTest(value=value):
                self.assertTrue(project_registration(_record(value))["normalized"]["aphis_registration_class"].startswith("Class "))

    def test_unknown_class_fails_closed(self):
        with self.assertRaisesRegex(AphisPreviewError, "known_native"):
            project_registration(_record("Class Z - Unknown"))

    def test_policy_registers_verified_private_e2e_without_public_release(self):
        policy = json.loads((ROOT / "preview-enabled-sources.json").read_text(encoding="utf-8"))["sources"]["us.aphis"]
        self.assertTrue(policy["enabled"])
        self.assertEqual(policy["runtime_classification"], "production-e2e")
        self.assertEqual(policy["activation"], "shared-private-registration-import")
        self.assertFalse(policy["public_release"])

    def test_prepare_hash_checks_and_writes_only_private_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            handoff = Path(directory) / "handoff"
            handoff.mkdir()
            payload = (json.dumps(_record(), sort_keys=True) + "\n").encode()
            (handoff / "records.jsonl").write_bytes(payload)
            (handoff / "manifest.json").write_text(json.dumps({
                "contract_version": "us-aphis-observation-handoff-v1", "source_id": "us.aphis", "profile": "registrations",
                "release_state": "not-created", "publication_state": "private-candidate", "normalized_sha256": hashlib.sha256(payload).hexdigest(),
                "normalized_rows": 1, "source_url": "https://example.invalid/aphis", "retrieved_at_utc": "2026-10-10T00:00:00Z",
                "checksum_sha256": "a" * 64, "byte_size": 123, "code_version": "us-aphis-candidate-v3", "config_version": "us-aphis-public-search-v2",
            }), encoding="utf-8")
            output = Path(directory) / "projection"
            result = PREVIEW.prepare(handoff, output)
            self.assertEqual(result["normalized_rows"], 1)
            self.assertEqual(result["bridge_handoff"]["manifest"], "bridge-handoff/manifest.json")
            self.assertTrue((output / "bridge-handoff/graph-candidates/manifest.json").is_file())
            self.assertEqual(result["geocode_queue"]["records_queued"], 1)
            self.assertEqual(result["geocode_queue"]["geocoder_status_policy"], "pending; no external geocoder has been called")
            manifest_text = (output / "manifest.json").read_text(encoding="utf-8")
            self.assertNotIn("Synthetic Lab", manifest_text)
            self.assertNotIn("100 Synthetic Way", manifest_text)


if __name__ == "__main__":
    unittest.main()
