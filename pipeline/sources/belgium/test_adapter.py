import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from . import adapter as adapter_module
from .adapter import BelgiumOperatorsAdapter, BelgiumSchemaError, _categories


ROOT = Path(__file__).parent


class BelgiumAdapterTests(unittest.TestCase):
    def _adapter(self):
        return BelgiumOperatorsAdapter(ROOT / "fixtures" / "synthetic_activity_codes.csv", SourceArtifact("https://example.invalid/activity.csv", "2026-09-14T00:00:00Z", hashlib.sha256((ROOT / "fixtures" / "synthetic_activity_codes.csv").read_bytes()).hexdigest(), (ROOT / "fixtures" / "synthetic_activity_codes.csv").stat().st_size))

    def test_join_classifies_scope_without_exposing_private_fields(self):
        adapter = self._adapter()
        result = adapter.parse_bytes((ROOT / "fixtures" / "synthetic_operators.csv").read_bytes())
        self.assertEqual(len(result["accepted"]), 3)
        self.assertEqual(len(result["quarantined"]), 2)
        mixed = next(row for row in result["accepted"] if row["source_id"] == "be.locations" and row["normalized"]["establishment_id"] == "BE-SYN-003")
        self.assertEqual(mixed["normalized"]["activity_categories"], ("slaughter", "cutting"))
        self.assertTrue(mixed["normalized"]["scope_flags"]["slaughterhouse"])
        self.assertIsNone(mixed["normalized"]["address"])
        self.assertIsNone(mixed["normalized"]["name"])
        self.assertNotIn("address", mixed["source_values"])
        self.assertNotIn("operator_id", mixed["source_values"])

    def test_unknown_activity_and_privacy_risk_quarantine(self):
        result = self._adapter().parse_bytes((ROOT / "fixtures" / "synthetic_operators.csv").read_bytes())
        reasons = [set(item["reasons"]) for item in result["quarantined"]]
        self.assertIn("address_privacy_risk", set().union(*reasons))
        self.assertIn("unresolved_activity_code", set().union(*reasons))

    def test_row_length_is_checked_per_row_not_from_previous_row(self):
        raw = (ROOT / "fixtures" / "synthetic_operators.csv").read_text(encoding="utf-8")
        lines = raw.splitlines()
        lines[1] += ",unexpected-extra-field"
        result = self._adapter().parse_bytes(("\n".join(lines) + "\n").encode())
        malformed = next(item for item in result["quarantined"] if item["record"]["source_row"] == 2)
        self.assertIn("malformed_row", malformed["reasons"])

    def test_ambiguous_codebook_key_is_not_silently_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            codebook = Path(directory) / "codes.csv"
            codebook.write_text("lap_code,place_code,activity_code,product_code\n593,PL1,AC2,PR40\n593,PL9,AC2,PR40\n", encoding="utf-8")
            adapter = BelgiumOperatorsAdapter(codebook)
            result = adapter.parse_bytes((ROOT / "fixtures" / "synthetic_operators.csv").read_bytes())
            first = next(item for item in result["quarantined"] if item["record"]["normalized"]["establishment_id"] == "BE-SYN-001")
            self.assertIn("unresolved_activity_code", first["reasons"])

    def test_scope_classifier_requires_approved_pap_id_and_code_signature(self):
        self.assertEqual(_categories([{"lap_code": "593", "place_code": "PL1", "activity_code": "AC2", "product_code": "PR40", "product_description": "Anything"}]), ("slaughter",))
        self.assertEqual(_categories([{"lap_code": "593", "place_code": "PL1", "activity_code": "AC2", "product_code": "wrong", "place_description": "Slaughterhouse"}]), ())
        self.assertEqual(_categories([{"lap_code": "99999", "place_code": "PL1", "activity_code": "AC2", "product_code": "PR40", "product_description": "Animal by-products"}]), ())

    def test_live_schema_fingerprints_fail_closed_on_drift(self):
        adapter = self._adapter()
        adapter.strict_schema = True
        with self.assertRaisesRegex(BelgiumSchemaError, "activity-code schema drift"):
            adapter.parse_bytes((ROOT / "fixtures" / "synthetic_operators.csv").read_bytes())

    def test_live_codebook_signature_drift_fails_closed_after_header_validation(self):
        codebook_bytes = (ROOT / "fixtures" / "synthetic_activity_codes.csv").read_bytes()
        headers = adapter_module._csv(codebook_bytes)[0]
        signatures = dict(adapter_module.CONFIG["animal_scope_pap_signatures"])
        signatures["593"] = {**signatures["593"], "product_code": "PR-DRIFT"}
        with patch.dict(adapter_module.CONFIG, {
            "expected_activity_code_schema_fingerprint": adapter_module._fingerprint(headers),
            "animal_scope_pap_signatures": signatures,
        }):
            adapter = self._adapter()
            adapter.strict_schema = True
            with self.assertRaisesRegex(BelgiumSchemaError, "approved animal-scope PAP signature changed"):
                adapter._codebook()

    def test_source_record_key_is_stable_when_rows_reorder(self):
        content = (ROOT / "fixtures" / "synthetic_operators.csv").read_bytes()
        lines = content.decode("utf-8").splitlines()
        reordered = ("\n".join([lines[0], *reversed(lines[1:])] + [""])).encode()
        adapter = self._adapter()
        first = adapter.parse_bytes(content)
        second = adapter.parse_bytes(reordered)
        first_keys = {row["normalized"]["establishment_id"]: row["source_record_key"] for row in first["accepted"]}
        second_keys = {row["normalized"]["establishment_id"]: row["source_record_key"] for row in second["accepted"]}
        self.assertEqual(first_keys, second_keys)

    def test_run_is_deterministic_and_shared_health_is_private(self):
        raw = ROOT / "fixtures" / "synthetic_operators.csv"
        code = ROOT / "fixtures" / "synthetic_activity_codes.csv"
        adapter = self._adapter()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = SourceArtifact("https://example.invalid/operators.csv", "2026-09-14T00:00:00Z", hashlib.sha256(raw.read_bytes()).hexdigest(), raw.stat().st_size, publication_date="2026-09-13", code_version=adapter.adapter_version, config_version=adapter.schema_version)
            status = run_private_lifecycle(raw, root / "runs", artifact, adapter)
            run_dir = Path(status["run_dir"])
            self.assertEqual(status["status"], "candidate-ready")
            self.assertEqual(status["manifest"]["codebook_sha256"], hashlib.sha256(code.read_bytes()).hexdigest())
            self.assertTrue((run_dir / "source-health.json").exists())
            self.assertTrue((run_dir / "release-candidate" / "records.jsonl").exists())
            self.assertFalse(json.loads((run_dir / "source-health.json").read_text())["public_exposure"])
            self.assertNotIn("source_values", (run_dir / "qa.json").read_text())


if __name__ == "__main__":
    unittest.main()
