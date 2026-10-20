"""Synthetic contract tests for the EPA ECHO animal-production adapter."""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import urllib.parse
import zipfile
from pathlib import Path
from unittest.mock import patch

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.refresh import AdapterCapabilities, RefreshRequest
from pipeline.contracts.source_lifecycle import read_jsonl
from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
from pipeline.sources.us.epa_echo import SOURCE_ID
from pipeline.sources.us.epa_echo.acquire import FIELDS, SERVICE_URL, SIC_CODES, AcquisitionError, build_where, fetch
from pipeline.sources.us.epa_echo.adapter import EpaEchoAnimalAdapter
from pipeline.sources.us.epa_echo.refresh import EpaEchoAnimalRefreshAdapter


def _feature(object_id: int, registry_id: str = "SYNTHETIC-REGISTRY-1", **overrides):
    attrs = {field: None for field in FIELDS}
    attrs.update({
        "OBJECTID": object_id, "REGISTRY_ID": registry_id,
        "FAC_NAME": "Synthetic Example Facility", "FAC_STREET": "100 Example Road",
        "FAC_CITY": "Example City", "FAC_STATE": "ZZ", "FAC_ZIP": "00000",
        "FAC_LAT": 38.25, "FAC_LONG": -77.5, "FAC_COLLECTION_METHOD": "Synthetic",
        "FAC_REFERENCE_POINT": "Synthetic point", "FAC_ACCURACY_METERS": 999,
        "FAC_ACTIVE_FLAG": "Y", "NPDES_FLAG": "Y", "NPDES_IDS": "SYNTHETIC-PERMIT",
        "CWA_PERMIT_TYPES": "NPDES", "CWA_NAICS": "112112",
        "CWA_SICS": "0211", "FAC_NAICS_CODES": "112112", "FAC_SIC_CODES": "0211",
    })
    attrs.update(overrides)
    return {"attributes": attrs}


def _archive(features):
    buf = io.BytesIO()
    ids = [item["attributes"]["OBJECTID"] for item in features]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("result-count.json", json.dumps({"count": len(ids)}))
        archive.writestr("object-ids.json", json.dumps({"objectIds": ids}))
        if features:
            archive.writestr("response-0001.json", json.dumps({"features": features}))
    return buf.getvalue()


def _temporary_directory():
    return tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)


class _Response:
    def __init__(self, payload, url):
        self.status = 200
        self.headers = {"Content-Type": "application/json"}
        self._payload = json.dumps(payload).encode()
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, size=-1):
        return self._payload[:size]

    def geturl(self):
        return self._url


class EpaEchoAnimalTests(unittest.TestCase):
    def test_query_is_narrow_and_excludes_non_livestock_sic_groups(self):
        where = build_where()
        self.assertEqual(where, "NPDES_FLAG = 'Y' AND (CWA_NAICS LIKE '112%' OR CWA_SICS IN (" + ",".join(f"'{code}'" for code in SIC_CODES) + "))")
        self.assertNotIn("02%", where)
        self.assertNotIn("mining", where.lower())

    def test_parse_preserves_native_codes_and_does_not_claim_cafo_or_operation(self):
        adapter = EpaEchoAnimalAdapter()
        parsed = adapter.parse_bytes(_archive([_feature(1)]))
        self.assertEqual(parsed["input_rows"], 1)
        row = parsed["accepted"][0]
        normalized = row["normalized"]
        self.assertEqual(row["source_id"], SOURCE_ID)
        self.assertEqual(row["source_values"]["cwa_naics"], "112112")
        self.assertEqual(row["source_values"]["cwa_sics"], "0211")
        self.assertEqual(normalized["cafo_status"], "not-established")
        self.assertEqual(normalized["operating_status"], "not-established")
        self.assertEqual(normalized["coordinates"]["precision"], "source-precision-unknown")

    def test_missing_and_duplicate_registry_ids_quarantine_without_inventing_identity(self):
        adapter = EpaEchoAnimalAdapter()
        parsed = adapter.parse_bytes(_archive([_feature(1, None), _feature(2), _feature(3)]))
        self.assertEqual(len(parsed["accepted"]), 1)
        self.assertEqual(len(parsed["quarantined"]), 2)
        self.assertEqual(parsed["quarantined"][0]["reasons"], ["missing_epa_registry_id"])
        self.assertEqual(parsed["quarantined"][1]["reasons"], ["duplicate_epa_registry_id"])
        self.assertEqual(parsed["input_rows"], len(parsed["accepted"]) + len(parsed["quarantined"]))

    def test_rejects_wrong_scope_schema_and_id_mismatch(self):
        adapter = EpaEchoAnimalAdapter()
        with self.assertRaisesRegex(ValueError, "does not satisfy"):
            adapter.parse_bytes(_archive([_feature(1, CWA_NAICS="311611", CWA_SICS="2033")]))
        feature = _feature(1)
        del feature["attributes"]["FAC_NAME"]
        bad = _archive([feature])
        with self.assertRaisesRegex(ValueError, "schema drift"):
            adapter.parse_bytes(bad)
        broken = io.BytesIO()
        with zipfile.ZipFile(broken, "w") as archive:
            archive.writestr("result-count.json", json.dumps({"count": 2}))
            archive.writestr("object-ids.json", json.dumps({"objectIds": [1, 2]}))
            archive.writestr("response-0001.json", json.dumps({"features": [_feature(1)]}))
        with self.assertRaisesRegex(ValueError, "do not reconcile|reconcile"):
            adapter.parse_bytes(broken.getvalue())

    def test_lifecycle_manifest_reconciles_and_handoff_omits_duplicate_source_values(self):
        adapter = EpaEchoAnimalAdapter()
        raw = _archive([_feature(1)])
        artifact = SourceArtifact(
            source_url=SERVICE_URL, retrieved_at_utc="2026-10-20T00:00:00Z",
            sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw),
            code_version=adapter.adapter_version, config_version=adapter.schema_version,
            rights_caveat="synthetic test only", privacy_caveat="synthetic test only",
            coverage="synthetic test only",
        )
        refresh = EpaEchoAnimalRefreshAdapter()
        with _temporary_directory() as temporary:
            root = Path(temporary)
            capture = root / "capture.zip"
            capture.write_bytes(raw)
            status = run_private_lifecycle(capture, root / "lifecycle", artifact, adapter,
                                           health_as_of_utc=artifact.retrieved_at_utc)
            self.assertEqual(status["status"], "candidate-ready")
            manifest = status["manifest"]
            self.assertEqual((manifest["input_rows"], manifest["normalized_rows"], manifest["quarantined_rows"]), (1, 1, 0))
            bridge = refresh.refresh(mode="local-artifact", run_dir=root / "bridge", artifact=capture,
                                     options={"acquisition": {"retrieved_at_utc": artifact.retrieved_at_utc,
                                                               "sha256": artifact.sha256, "byte_size": artifact.byte_size,
                                                               "source_url": SERVICE_URL}})
            self.assertEqual(bridge["lifecycle_status"], "candidate-ready")
            self.assertEqual(bridge["candidate_observation_rows"], 1)
            handoff = read_jsonl(root / "bridge" / "candidate-handoff" / "normalized" / "records.jsonl")
            self.assertEqual(handoff[0]["source_values"], {})
            self.assertEqual(handoff[0]["normalized"]["cafo_status"], "not-established")

    def test_shared_runner_local_artifact_bridge_returns_only_aggregate_summary(self):
        raw = _archive([_feature(1)])
        adapter = EpaEchoAnimalRefreshAdapter()
        capabilities = AdapterCapabilities(
            source_id=SOURCE_ID, adapter_version=adapter.adapter_version,
            schema_version=EpaEchoAnimalAdapter.schema_version,
            acquisition="bounded_private_fetch", geocoding="disabled",
            publication="human_gate_required", adapter_path="synthetic-test-adapter",
            country_code="us", source_kind="facility_master",
            operational_classification="live", live_callable=True,
        )
        with _temporary_directory() as temporary:
            root = Path(temporary)
            capture = root / "capture.zip"
            capture.write_bytes(raw)
            facts = {
                "source_id": SOURCE_ID, "source_url": SERVICE_URL,
                "retrieved_at_utc": "2026-10-20T00:00:00Z",
                "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
            }
            catalog = RefreshCatalog()
            catalog.sources.setdefault(SOURCE_ID, {
                "source_id": SOURCE_ID, "adapter_status": "implemented",
                "access_method": "bounded_private_fetch", "cadence": "on-demand",
            })
            catalog.register(adapter, capabilities)
            result = RefreshRunner(catalog).run(RefreshRequest(
                source_ids=(SOURCE_ID,), mode="local-artifact", output_root=root / "runner",
                artifact_paths={SOURCE_ID: str(capture)}, options={"acquisition": facts},
            ))
            self.assertEqual(result["exit_status"], "ok")
            summary = result["results"][0]["summary"]
            self.assertEqual(summary["input_rows"], 1)
            self.assertEqual(summary["normalized_rows"], 1)
            self.assertTrue(summary["candidate_handoff"])
            encoded = json.dumps(result)
            self.assertNotIn("Synthetic Example Facility", encoded)
            self.assertNotIn("100 Example Road", encoded)

    def test_shared_runner_fixture_mode_is_synthetic_and_row_free(self):
        adapter = EpaEchoAnimalRefreshAdapter()
        capabilities = AdapterCapabilities(
            source_id=SOURCE_ID, adapter_version=adapter.adapter_version,
            schema_version=EpaEchoAnimalAdapter.schema_version,
            acquisition="bounded_private_fetch", geocoding="disabled",
            publication="human_gate_required", adapter_path="synthetic-test-adapter",
            country_code="us", source_kind="facility_master",
            operational_classification="live", live_callable=True,
        )
        with _temporary_directory() as temporary:
            root = Path(temporary)
            catalog = RefreshCatalog()
            catalog.sources.setdefault(SOURCE_ID, {
                "source_id": SOURCE_ID, "adapter_status": "implemented",
                "access_method": "bounded_private_fetch", "cadence": "on-demand",
            })
            catalog.register(adapter, capabilities)
            result = RefreshRunner(catalog).run(RefreshRequest(
                source_ids=(SOURCE_ID,), mode="fixture", output_root=root / "fixture-run",
            ))
            self.assertEqual(result["exit_status"], "ok")
            summary = result["results"][0]["summary"]
            self.assertEqual(summary["input_rows"], 1)
            self.assertTrue(summary["candidate_handoff"])
            self.assertNotIn("Synthetic Example Facility", json.dumps(result))

    def test_fetch_uses_terms_gate_and_preserves_bounded_official_response_pages(self):
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url)
            params = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
            if params.get("returnCountOnly") == ["true"]:
                payload = {"count": 1}
            elif params.get("returnIdsOnly") == ["true"]:
                payload = {"objectIds": [17]}
            else:
                payload = {"features": [_feature(17)]}
            return _Response(payload, request.full_url)

        with _temporary_directory() as temporary:
            root = Path(temporary)
            review = root / "review.json"
            review.write_text(json.dumps({
                "reviewer": "synthetic test", "reference": "EPA public data license page",
                "reviewed_at": "2026-10-20T00:00:00Z", "decision": "approved",
                "notes": "Synthetic test approval; not a source publication decision.",
            }), encoding="utf-8")
            metadata = fetch(output_root=root / "capture", run_id="synthetic", terms_review_path=review,
                            opener=opener, page_size=1)
            artifact = Path(metadata["artifact_path"])
            self.assertTrue(artifact.is_file())
            self.assertEqual(metadata["input_rows"], 1)
            self.assertEqual(metadata["response_pages"], 1)
            self.assertEqual(len(calls), 3)
            query = urllib.parse.parse_qs(urllib.parse.urlparse(calls[2]).query)
            self.assertIn("NPDES_FLAG", query["where"][0])
            self.assertEqual(query["returnGeometry"], ["false"])
            with zipfile.ZipFile(artifact) as archive:
                self.assertEqual(len(archive.namelist()), 3)
            self.assertNotIn("Synthetic Example Facility", json.dumps(metadata))

    def test_fetch_rejects_unreviewed_terms_before_network(self):
        called = False

        def opener(*_args, **_kwargs):
            nonlocal called
            called = True
            raise AssertionError("network should not be called")

        with _temporary_directory() as temporary:
            root = Path(temporary)
            review = root / "review.json"
            review.write_text(json.dumps({
                "reviewer": "synthetic", "reference": "synthetic", "reviewed_at": "2026-10-20T00:00:00Z",
                "decision": "blocked", "notes": "synthetic block",
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "approved"):
                fetch(output_root=root / "capture", run_id="blocked", terms_review_path=review, opener=opener)
        self.assertFalse(called)


if __name__ == "__main__":
    unittest.main()
