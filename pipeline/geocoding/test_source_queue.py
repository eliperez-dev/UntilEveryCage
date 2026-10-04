from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.geocoding.source_queue import build_geocode_queue


class SourceLocationQueueTests(unittest.TestCase):
    def test_shared_queue_uses_normalized_facility_address_and_excludes_contacts(self):
        records = [{
            "source_id": "fr.test.facilities", "source_record_key": "source-key",
            "source_values": {"Name": "Private Test Name", "Phone": "555-0100"},
            "normalized": {"facility_address": "12 Example Road", "city": "Example City",
                           "province": "ON", "postal_code": "A1A 1A1", "nation": "Canada"},
        }]
        artifact = SourceArtifact("https://example.test/source", "2026-10-01T00:00:00Z",
                                 hashlib.sha256(b"fixture").hexdigest(), 7)
        with tempfile.TemporaryDirectory() as directory:
            summary = build_geocode_queue(records, artifact, directory)
            queue_path = Path(directory) / "geocode-queue.jsonl"
            queued = json.loads(queue_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["records_queued"], 1)
            self.assertEqual(queued["geocoder_query"], "12 Example Road, Example City, ON, A1A 1A1, Canada")
            self.assertNotIn("Private Test Name", queued["geocoder_query"])
            self.assertNotIn("555-0100", queued["geocoder_query"])
            first_hash = summary["queue_sha256"]
            self.assertEqual(build_geocode_queue(records, artifact, directory)["queue_sha256"], first_hash)

    def test_source_coordinate_suppresses_address_queue(self):
        artifact = SourceArtifact("https://example.test/source", "2026-10-01T00:00:00Z",
                                 hashlib.sha256(b"fixture").hexdigest(), 7)
        record = {"source_id": "ca.ontario.meat-plants", "source_record_key": "source-key",
                  "normalized": {"facility_address": "12 Example Road",
                                 "coordinates": {"latitude": 43.1, "longitude": -79.1}}}
        with tempfile.TemporaryDirectory() as directory:
            summary = build_geocode_queue([record], artifact, directory)
        self.assertEqual(summary["records_with_source_coordinates"], 1)
        self.assertEqual(summary["records_queued"], 0)

    def test_invalid_coordinates_fall_back_to_address(self):
        artifact = SourceArtifact("https://example.test/source", "2026-10-01T00:00:00Z",
                                 hashlib.sha256(b"fixture").hexdigest(), 7)
        for coordinates in (
            {"latitude": 0, "longitude": 0},
            {"latitude": 91, "longitude": -80},
            {"latitude": "not-a-coordinate", "longitude": -80},
            {"latitude": 43, "longitude": None},
        ):
            with self.subTest(coordinates=coordinates), tempfile.TemporaryDirectory() as directory:
                record = {"source_id": "ca.ontario.meat-plants", "source_record_key": "source-key",
                          "normalized": {"facility_address": "12 Example Road",
                                         "coordinates": coordinates}}
                summary = build_geocode_queue([record], artifact, directory)
                self.assertEqual(summary["records_with_source_coordinates"], 0)
                self.assertEqual(summary["records_queued"], 1)

    def test_fsa_unverified_source_axes_do_not_become_points_or_block_address_query(self):
        artifact = SourceArtifact("https://example.test/fsa", "2026-10-01T00:00:00Z",
                                 hashlib.sha256(b"fixture").hexdigest(), 7)
        record = {"source_id": "fsa_approved_establishments", "source_record_key": "England|A-1",
                  "source_values": {"Phone": "555-0100"},
                  "normalized": {"coordinates": None, "private_location_evidence": {
                      "country_code": "GB", "address_lines": ["10 Example Road"],
                      "city": "Exampleton", "postal_code": "AB1 2CD",
                      "coordinates": {"x": "430000", "y": "780000",
                                      "coordinate_reference_system": "unverified",
                                      "precision": "unverified-source-semantics"},
                  }}}
        with tempfile.TemporaryDirectory() as directory:
            summary = build_geocode_queue([record], artifact, directory)
            queued = json.loads((Path(directory) / "geocode-queue.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(summary["records_with_source_coordinates"], 0)
        self.assertEqual(summary["records_queued"], 1)
        self.assertEqual(queued["geocoder_query"], "10 Example Road, Exampleton, AB1 2CD, United Kingdom")
        self.assertNotIn("555-0100", queued["geocoder_query"])


if __name__ == "__main__":
    unittest.main()
