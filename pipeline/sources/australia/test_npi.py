import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.sources.australia.npi import (
    ADAPTER_VERSION, SCHEMA_VERSION, NpiFacilitiesAdapter, SOURCE_ID, SOURCE_URL,
)


ROOT = Path(__file__).parent
FIXTURE = ROOT / "fixtures" / "npi_facilities.csv"


def artifact_for(raw: bytes) -> SourceArtifact:
    return SourceArtifact(
        source_url=SOURCE_URL,
        retrieved_at_utc="2026-09-22T00:00:00Z",
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        code_version=ADAPTER_VERSION,
        config_version=SCHEMA_VERSION,
        rights_caveat="synthetic fixture; source terms remain a human gate",
        privacy_caveat="private staging; privacy review required",
        coverage="NPI reporting facilities; no completeness claim",
    )


class NpiAdapterTests(unittest.TestCase):
    def test_fixture_parses_coordinates_and_quarantines_bad_identity_and_point(self):
        result = NpiFacilitiesAdapter().parse_bytes(FIXTURE.read_bytes())
        self.assertEqual(result["input_rows"], 5)
        self.assertEqual(len(result["accepted"]), 3)
        self.assertEqual(len(result["quarantined"]), 2)
        self.assertEqual(result["accepted"][0]["normalized"]["coordinate_state"], "source")
        self.assertEqual(result["accepted"][2]["normalized"]["coordinate_state"], "not-supplied-by-source")
        reasons = {reason for item in result["quarantined"] for reason in item["reasons"]}
        self.assertEqual(reasons, {"invalid_source_coordinate", "missing_facility_id"})

    def test_missing_column_is_schema_drift(self):
        raw = FIXTURE.read_bytes().replace(b",reports\r\n", b"\r\n", 1)
        with self.assertRaisesRegex(ValueError, "schema drift"):
            NpiFacilitiesAdapter().parse_bytes(raw)

    def test_private_lifecycle_is_deterministic_and_private(self):
        raw = FIXTURE.read_bytes()
        directory = Path(tempfile.mkdtemp(prefix="uec-e2-npi-adapter-"))
        try:
            result = run_private_lifecycle(FIXTURE, directory / "run", artifact_for(raw), NpiFacilitiesAdapter())
            self.assertEqual(result["status"], "candidate-ready")
            manifest = json.loads((Path(result["run_dir"]) / "manifest.json").read_text())
            self.assertEqual(manifest["source_id"], SOURCE_ID)
            self.assertEqual(manifest["input_rows"], 5)
            self.assertEqual(manifest["normalized_rows"], 3)
            self.assertEqual(manifest["quarantined_rows"], 2)
            self.assertEqual(manifest["release_state"], "not-created")
            self.assertFalse(manifest.get("published", False))
        finally:
            shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
