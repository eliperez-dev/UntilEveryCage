import hashlib
import tempfile
import unittest
from pathlib import Path

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from .adapter import CfiaFederalMeatAdapter, OntarioMeatPlantsAdapter

FIXTURES = Path(__file__).parent / "fixtures"


class CanadaAdapterTests(unittest.TestCase):
    def test_ontario_is_provincial_and_privacy_safe(self):
        adapter = OntarioMeatPlantsAdapter(); result = adapter.parse_file(FIXTURES / "ontario.csv")
        self.assertEqual(len(result["accepted"]), 2); self.assertEqual(len(result["quarantined"]), 1)
        row = result["accepted"][0]
        self.assertEqual(row["normalized"]["jurisdiction_level"], "provincial"); self.assertEqual(row["normalized"]["jurisdiction"], "Ontario"); self.assertEqual(row["normalized"]["activity_categories"], ("slaughter",)); self.assertIsNone(row["normalized"]["coordinates"])
        self.assertEqual(row["source_values"]["Phone"], "555-0100")

    def test_cfia_function_codes_and_unknown_code_quarantine(self):
        adapter = CfiaFederalMeatAdapter(); result = adapter.parse_file(FIXTURES / "cfia.csv")
        self.assertEqual(len(result["accepted"]), 2); self.assertEqual(len(result["quarantined"]), 1); self.assertEqual(result["accepted"][0]["normalized"]["activity_categories"], ("slaughter", "cutting")); self.assertEqual(result["accepted"][1]["normalized"]["activity_categories"], ("logistics_and_storage",)); self.assertEqual(result["quarantined"][0]["reasons"], ("unknown_function_code",))

    def test_federal_and_provincial_lifecycles_are_separate(self):
        with tempfile.TemporaryDirectory() as d:
            for adapter, fixture in ((OntarioMeatPlantsAdapter(), "ontario.csv"), (CfiaFederalMeatAdapter(), "cfia.csv")):
                raw = (FIXTURES / fixture).read_bytes(); artifact = SourceArtifact(adapter.source_url, "2026-09-15T00:00:00Z", hashlib.sha256(raw).hexdigest(), len(raw), code_version=adapter.adapter_version, config_version=adapter.schema_version)
                status = run_private_lifecycle(FIXTURES / fixture, Path(d) / adapter.source_id, artifact, adapter)
                self.assertEqual(status["status"], "candidate-ready"); self.assertEqual(status["manifest"]["jurisdiction_level"], adapter.jurisdiction_level); self.assertTrue((Path(status["run_dir"]) / "release-candidate" / "records.jsonl").exists())


if __name__ == "__main__": unittest.main()
