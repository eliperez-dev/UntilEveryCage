from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from pipeline.contracts.adapter_contract import SourceArtifact

from .adapter import CfiaFederalMeatAdapter, OntarioMeatPlantsAdapter
from .geocode_queue import build_geocode_queue


class CanadaGeocodeQueueTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[3] / ".d2-canada-geocode-queue-test"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    @staticmethod
    def artifact(adapter, raw: bytes) -> SourceArtifact:
        import hashlib
        return SourceArtifact(adapter.source_url, "2026-10-01T00:00:00Z",
                              hashlib.sha256(raw).hexdigest(), len(raw),
                              code_version=adapter.adapter_version,
                              config_version=adapter.schema_version)

    def test_cfia_accepted_unmapped_rows_get_private_provider_neutral_jobs(self):
        adapter = CfiaFederalMeatAdapter()
        raw = (Path(__file__).parent / "fixtures" / "cfia.csv").read_bytes()
        parsed = adapter.parse_bytes(raw)
        result = build_geocode_queue(parsed["accepted"], self.artifact(adapter, raw), self.root)
        queue = [json.loads(line) for line in (self.root / "geocode-queue.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(result["records_seen"], 2)
        self.assertEqual(result["records_queued"], 2)
        self.assertEqual(result["provider_review_state"], "required")
        self.assertEqual(result["geocoder_status_policy"], "pending; no external geocoder has been called")
        self.assertEqual(queue[0]["status"], "pending-provider-review")
        self.assertIn("3 Federal Way", queue[0]["geocoder_query"])
        self.assertNotIn("Synthetic Federal Meats", queue[0]["geocoder_query"])
        self.assertNotIn("555-0100", json.dumps(queue))

    def test_source_coordinates_are_not_requeued_for_geocoding(self):
        adapter = OntarioMeatPlantsAdapter()
        raw = (Path(__file__).parent / "fixtures" / "ontario.csv").read_bytes()
        parsed = adapter.parse_bytes(raw)
        result = build_geocode_queue(parsed["accepted"], self.artifact(adapter, raw), self.root)
        self.assertEqual(result["records_with_source_coordinates"], 2)
        self.assertEqual(result["records_queued"], 0)


if __name__ == "__main__":
    unittest.main()
