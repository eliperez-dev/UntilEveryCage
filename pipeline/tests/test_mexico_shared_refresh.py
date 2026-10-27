"""Synthetic shared-runner integration for the INEGI DENUE source hook."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
from pipeline.contracts.refresh import RefreshRequest
from pipeline.sources.mexico.refresh import DenueRefreshAdapter
from pipeline.sources.scotland_aquaculture.refresh import ScotlandAquacultureRefreshAdapter


def _payload() -> bytes:
    row = {
        "CLEE": "01001731161100091", "Id": "91", "Nombre": "Synthetic facility",
        "Razon_social": "Synthetic operator", "Clase_actividad": "Synthetic slaughter",
        "Tipo_vialidad": "CALLE", "Calle": "Synthetic Road", "Num_Exterior": "1",
        "Colonia": "Test", "CP": "00000", "Ubicacion": "Synthetic municipality",
        "Latitud": "19.4", "Longitud": "-99.1", "CLASE_ACTIVIDAD_ID": "311611",
        "AreaGeo": "010010001",
    }
    envelope = {
        "source_id": "mx.locations", "schema_version": "denue-api-v1",
        "activity_codes": ["311611", "311612", "311613", "311614"],
        "retrieved_at_utc": "2026-10-26T00:00:00Z", "records": [row],
        "preflight_counts": [{"activity_code": "31161", "state_code": "01", "count": 1}],
    }
    return (json.dumps(envelope, sort_keys=True) + "\n").encode("utf-8")


class MexicoSharedRefreshTests(unittest.TestCase):
    def test_catalog_registers_mexico_and_preserves_existing_refresh_adapters(self):
        catalog = RefreshCatalog()
        self.assertIsInstance(catalog.adapters["mx.locations"].adapter, DenueRefreshAdapter)
        self.assertTrue(catalog.capabilities["mx.locations"].live_callable)
        self.assertEqual(catalog.capabilities["mx.locations"].operational_classification, "live")
        self.assertIsInstance(catalog.adapters["gb.scot.marine.aquaculture"].adapter,
                              ScotlandAquacultureRefreshAdapter)

    def test_local_artifact_runs_through_standard_refresh_runner(self):
        raw = _payload()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "denue.json"
            artifact.write_bytes(raw)
            facts = {"retrieved_at_utc": "2026-10-26T00:00:00Z",
                     "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
                     "preflight_rows": 1, "request_count": 5, "response_bytes": 800,
                     "activity_counts": {"31161": 1}}
            result = RefreshRunner(RefreshCatalog()).run(RefreshRequest(
                source_ids=("mx.locations",), mode="local-artifact",
                artifact_paths={"mx.locations": str(artifact)}, output_root=root / "runs",
                options={"acquisition": facts},
            ))
            summary = result["results"][0]["summary"]
            self.assertEqual(result["exit_status"], "ok")
            self.assertEqual(result["results"][0]["acquisition_classification"], "assisted")
            self.assertEqual(summary["source_artifact_sha256"], facts["sha256"])
            self.assertTrue(summary["candidate_handoff"])
            self.assertEqual(summary["candidate_observation_rows"], 1)
            self.assertFalse(any("records" in key or "rows" == key for key in summary))

    def test_live_runner_path_uses_approved_terms_and_source_scoped_authorization(self):
        raw = _payload()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            review = root / "approved-terms.json"
            review.write_text(json.dumps({"source_id": "mx.locations", "decision": "approved",
                                          "private_preview_only": True}), encoding="utf-8")

            def synthetic_acquire(*, output_root: Path, **_options):
                artifact = output_root / "raw" / "denue-api.json"
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_bytes(raw)
                return {"artifact_path": str(artifact), "retrieved_at_utc": "2026-10-26T00:00:00Z",
                        "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
                        "preflight_rows": 1, "request_count": 5, "response_bytes": 800,
                        "activity_counts": {"31161": 1}}

            with patch("pipeline.sources.mexico.refresh.fetch", side_effect=synthetic_acquire):
                result = RefreshRunner(RefreshCatalog()).run(RefreshRequest(
                    source_ids=("mx.locations",), mode="live-acquisition",
                    output_root=root / "runs",
                    options={"authorized_live_sources": ["mx.locations"],
                             "terms_review_paths": {"mx.locations": str(review)}},
                ))
            summary = result["results"][0]["summary"]
            self.assertEqual(result["exit_status"], "ok")
            self.assertEqual(result["results"][0]["acquisition_classification"], "live")
            self.assertTrue(summary["candidate_handoff"])
            self.assertEqual(summary["input_rows"], 1)
            self.assertNotIn("artifact_path", summary)
            self.assertNotIn(str(review), json.dumps(result))
            self.assertNotIn("synthetic-secret", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
