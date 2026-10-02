import hashlib, json, tempfile, unittest
from pathlib import Path
from .adapter_contract import SourceArtifact
from .candidate_handoff import write_handoff, CONTRACT_VERSION
from .private_location_evidence import project_private_location_evidence

class CandidateHandoffTests(unittest.TestCase):
    def artifact(self):
        return SourceArtifact("https://example.test/source", "2026-01-01T00:00:00Z", "a" * 64, 12, code_version="c1", config_version="v1", coverage="synthetic")
    def test_emits_private_importer_contract(self):
        row = {"source_id":"test.source", "source_row":2, "source_values":{"id":"A"}, "normalized":{"establishment_id":"A", "privacy_gate":"pending", "coordinate_gate":"review_required"}}
        with tempfile.TemporaryDirectory() as d:
            m = write_handoff(d, [row], self.artifact(), source_id="test.source")
            self.assertEqual(m["contract_version"], CONTRACT_VERSION); self.assertEqual(m["release_state"], "not-created")
            data = (Path(d) / "normalized/records.jsonl").read_bytes(); self.assertEqual(m["normalized_sha256"], hashlib.sha256(data).hexdigest())
    def test_rejects_guessed_or_missing_identity(self):
        bad = {"source_id":"test.source", "source_row":2, "normalized":{"name":"guess"}}
        with self.assertRaisesRegex(ValueError, "establishment_id"):
            write_handoff(tempfile.mkdtemp(), [bad], self.artifact(), source_id="test.source")

    def test_private_location_evidence_projection_excludes_contact_fields(self):
        row = {"source_id": "test.source", "source_row": 2, "source_values": {
            "address": "Correspondence address", "Phone": "private-contact",
            "Email": "person@example.test", "Contact Name": "Private Person",
            "contact": {"address": "Private Person's home"},
        }, "normalized": {"establishment_id": "A", "address": "10 Example Road",
            "postal_code": "A1A 1A1", "city": "Exampleton",
            "coordinates": {"latitude": "45.0", "longitude": "-75.0"}}}
        evidence = project_private_location_evidence(row)
        self.assertEqual(evidence["address"], "10 Example Road")
        self.assertEqual(evidence["postal_code"], "A1A 1A1")
        self.assertEqual(evidence["city"], "Exampleton")
        self.assertEqual(evidence["coordinates"], {"latitude": "45.0", "longitude": "-75.0", "precision": None})
        self.assertEqual(set(evidence), {"address", "postal_code", "city", "coordinates"})
        self.assertNotIn("Private Person's home", json.dumps(evidence))
        with tempfile.TemporaryDirectory() as directory:
            write_handoff(directory, [row], self.artifact(), source_id="test.source")
            handoff = (Path(directory) / "normalized/records.jsonl").read_text(encoding="utf-8")
            self.assertIn("private_location_evidence", handoff)
            for private_contact in ("private-contact", "person@example.test", "Private Person"):
                self.assertNotIn(private_contact, json.dumps(evidence))

    def test_explicit_withheld_location_projection_is_not_refilled_from_raw_source(self):
        row = {"source_id": "test.source", "source_row": 2, "source_values": {
            "Address1": "Withheld Facility Address", "Latitude": "45.0", "Longitude": "-75.0",
        }, "normalized": {
            "establishment_id": "A", "privacy_gate": "restricted-withheld-address",
            "coordinate_gate": "restricted-withheld-address",
            "private_location_evidence": {"city": "Exampleton"},
        }}
        self.assertEqual(project_private_location_evidence(row), {"city": "Exampleton"})

if __name__ == "__main__": unittest.main()
