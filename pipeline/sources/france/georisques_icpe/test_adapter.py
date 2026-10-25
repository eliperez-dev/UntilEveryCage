from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import read_jsonl

from .acquire import acquire_snapshot
from .adapter import GeorisquesIcpeAnimalAdapter
from .config import CONFIG
from .refresh import refresh


def row(aiot: str, *, rubric: str = "2101", name: str = "Établissement Synthétique",
        lon: float = 2.0, lat: float = 48.0) -> dict:
    return {
        "codeAIOT": aiot, "siret": "12345678901234", "raisonSociale": name,
        "adresse1": "Adresse de test", "adresse2": None, "adresse3": None,
        "codePostal": "75000", "codeInsee": "75056", "commune": "Commune de test",
        "codeNaf": "01.41Z", "longitude": lon, "latitude": lat,
        "coordonneeXAIOT": 652469.0, "coordonneeYAIOT": 6862035.0,
        "systemeCoordonneesAIOT": "2154",
        "bovins": "500", "porcs": None, "volailles": "0", "etatActivite": "En fonctionnement",
        "date_maj": "2026-10-01", "regime": "Autorisation",
        "rubriques": [{"numeroRubrique": rubric, "nature": "synthetic",
                       "alinea": "test", "quantiteTotale": "500", "unite": "têtes"}],
        "inspections": [], "documentsHorsInspection": [],
    }


def write_snapshot(root: Path, pages: list[list[dict]], page_size: int) -> Path:
    pages_dir = root / "pages"
    pages_dir.mkdir(parents=True)
    total = sum(map(len, pages))
    serialized = []
    facts = []
    for number, rows in enumerate(pages, 1):
        payload = {"results": total, "page": number, "total_pages": len(pages),
                   "data": rows, "response_code": 200, "message": "ok"}
        content = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        path = pages_dir / f"page-{number:05d}.json"
        path.write_bytes(content)
        serialized.append(content)
        facts.append({"page": number, "rows": len(rows), "sha256": hashlib.sha256(content).hexdigest(), "byte_size": len(content)})
    aggregate = b"".join(serialized)
    (root / "snapshot-manifest.json").write_text(json.dumps({
        "source_id": CONFIG["source_id"], "retrieved_at_utc": "2026-10-20T12:00:00Z",
        "page_size": page_size, "pages": facts, "results": total,
        "total_pages": len(pages), "sha256": hashlib.sha256(aggregate).hexdigest(),
        "byte_size": len(aggregate), "artifact_path": str(pages_dir),
    }), encoding="utf-8")
    return pages_dir


class GeorisquesIcpeAnimalTests(unittest.TestCase):
    def test_exact_rubric_allowlist_and_projected_coordinates(self):
        rows = [
            row("A-1", name="Ferme Éléonore — test"),
            row("A-2", rubric="2102"),
            row("A-3", rubric="2510"),
        ]
        parsed = GeorisquesIcpeAnimalAdapter().normalize(rows)
        self.assertEqual(len(parsed["accepted"]), 2)
        self.assertEqual(len(parsed["quarantined"]), 1)
        first_record, corroboration_record = parsed["accepted"]
        first, corroboration_case = first_record["normalized"], corroboration_record["normalized"]
        self.assertEqual(first["name"], "Ferme Éléonore — test")
        self.assertEqual(first["activity_status_source"], "En fonctionnement")
        self.assertEqual(first["capacity_indicators_source"]["bovins"], "500")
        self.assertEqual(first["coordinates"]["jurisdiction_extent"], "metropolitan-france")
        self.assertEqual(first["coordinates"]["coordinate_reference_system"], "EPSG:4326")
        self.assertEqual(first["coordinates"]["precision"], "source-provided-unspecified")
        self.assertEqual(first["coordinates"]["source_coordinate_reference_system"], "EPSG:2154")
        self.assertTrue(first["in_default_map_scope"])
        self.assertEqual(first_record["source_values"]["coordonneeXAIOT"], 652469.0)
        self.assertEqual(first_record["source_values"]["systemeCoordonneesAIOT"], "2154")
        self.assertEqual(corroboration_case["coordinates"]["api_lonlat_corroboration"], "differs-over-100m")
        self.assertIn("no_allowed_animal_rubric", parsed["quarantined"][0]["reasons"])
        self.assertEqual(parsed["input_rows"], 3)

    def test_missing_crs_keeps_source_values_but_never_uses_api_lonlat_as_map_point(self):
        source = row("NO-CRS")
        source["systemeCoordonneesAIOT"] = None
        normalized = GeorisquesIcpeAnimalAdapter().normalize([source])["accepted"][0]
        self.assertIsNone(normalized["normalized"]["coordinates"])
        self.assertFalse(normalized["normalized"]["in_default_map_scope"])
        self.assertEqual(normalized["source_values"]["longitude"], 2.0)
        self.assertEqual(normalized["source_values"]["coordonneeXAIOT"], 652469.0)

    def test_unsupported_crs_is_unmapped_and_api_pair_cannot_override_it(self):
        source = row("UNKNOWN-CRS")
        source["systemeCoordonneesAIOT"] = "999999"
        normalized = GeorisquesIcpeAnimalAdapter().normalize([source])["accepted"][0]
        self.assertIsNone(normalized["normalized"]["coordinates"])
        self.assertFalse(normalized["normalized"]["in_default_map_scope"])
        self.assertEqual(normalized["normalized"]["coordinate_state"], "source-coordinate-transform-failed")

    def test_declared_overseas_crs_transforms_to_configured_french_extent(self):
        source = row("GUYANE-CRS", lon=-52.5, lat=4.5)
        source.update({"coordonneeXAIOT": 500000, "coordonneeYAIOT": 500000,
                      "systemeCoordonneesAIOT": "2972"})
        normalized = GeorisquesIcpeAnimalAdapter().normalize([source])["accepted"][0]["normalized"]
        self.assertEqual(normalized["coordinates"]["jurisdiction_extent"], "french-guiana")
        self.assertTrue(normalized["in_default_map_scope"])

    def test_non_animal_rubrics_on_a_qualifying_row_do_not_enter_normalized_scope(self):
        source = row("ANIMAL-AND-INDUSTRIAL")
        source["rubriques"].append({"numeroRubrique": "2510", "nature": "mining"})
        normalized = GeorisquesIcpeAnimalAdapter().normalize([source])["accepted"][0]
        self.assertEqual([item["numeroRubrique"] for item in normalized["normalized"]["rubriques_source"]], ["2101"])
        self.assertEqual([item["numeroRubrique"] for item in normalized["source_values"]["rubriques"]], ["2101"])

    def test_distinct_observations_with_same_aiot_preserve_multiplicity(self):
        parsed = GeorisquesIcpeAnimalAdapter().normalize([
            row("SAME", rubric="2101"), row("SAME", rubric="2102", name="Second observation")])
        self.assertEqual(len(parsed["accepted"]), 2)
        self.assertEqual(len(parsed["quarantined"]), 0)
        self.assertEqual([item["normalized"]["name"] for item in parsed["accepted"]],
                         ["Établissement Synthétique", "Second observation"])

    def test_exact_duplicate_source_observation_is_quarantined_without_losing_row(self):
        source = row("SAME")
        parsed = GeorisquesIcpeAnimalAdapter().normalize([source, dict(source)])
        self.assertEqual(len(parsed["accepted"]), 1)
        self.assertEqual(len(parsed["quarantined"]), 1)
        self.assertIn("duplicate_identical_source_observation", parsed["quarantined"][0]["reasons"])
        self.assertEqual(parsed["quarantined"][0]["record"]["normalized"]["name"], "Établissement Synthétique")

    def test_private_handoff_allowlist_excludes_inspection_contacts_and_unknown_fields(self):
        source = row("SAFE")
        source["inspections"] = [{"inspectorName": "must not propagate", "phone": "private"}]
        source["documentsHorsInspection"] = [{"url": "https://example.invalid/private"}]
        source["unmodeledContact"] = "must not propagate"
        normalized = GeorisquesIcpeAnimalAdapter().normalize([source])["accepted"][0]
        self.assertNotIn("inspections", normalized["source_values"])
        self.assertNotIn("documentsHorsInspection", normalized["source_values"])
        self.assertNotIn("unmodeledContact", normalized["source_values"])
        self.assertNotIn("inspectorName", json.dumps(normalized, ensure_ascii=False))

    def test_page_count_identity_and_candidate_handoff_are_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pages = write_snapshot(root / "snapshot", [[row("ID-1"), row("ID-2", lon=55.5, lat=-21.1)]], 100)
            adapter = GeorisquesIcpeAnimalAdapter()
            result = adapter.parse_path(pages)
            self.assertEqual(result["input_rows"], 2)
            self.assertEqual(len(result["accepted"]), 2)
            raw = b"".join(path.read_bytes() for path in sorted(pages.glob("page-*.json")))
            artifact = SourceArtifact(CONFIG["source_url"], "2026-10-20T12:00:00Z",
                                      hashlib.sha256(raw).hexdigest(), len(raw),
                                      code_version=adapter.adapter_version, config_version=CONFIG["config_version"])
            status = run_private_lifecycle(pages, root / "runs", artifact, adapter)
            run_root = Path(status["run_dir"])
            self.assertEqual(status["status"], "candidate-ready")
            self.assertEqual(len(status["manifest"]["schema_fingerprint"]), 64)
            records = read_jsonl(run_root / "normalized" / "records.jsonl")
            self.assertEqual(records[0]["normalized"]["name"], "Établissement Synthétique")
            handoff = write_handoff(run_root / "candidate-handoff", records, artifact, source_id=adapter.source_id)
            self.assertEqual(handoff["normalized_rows"], 2)
            self.assertEqual(handoff["release_state"], "not-created")
            location = read_jsonl(run_root / "candidate-handoff" / "normalized" / "records.jsonl")[1]["normalized"]["private_location_evidence"]
            self.assertNotEqual(location["coordinates"]["longitude"], 55.5)

    def test_snapshot_parser_rejects_modified_page_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pages = write_snapshot(root / "snapshot", [[row("HASHED")]], 100)
            manifest_path = pages.parent / "snapshot-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["pages"][0]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "snapshot-manifest provenance"):
                GeorisquesIcpeAnimalAdapter().parse_pages(pages)

    def test_refresh_requires_explicit_terms_decision_and_emits_only_private_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pages = write_snapshot(root / "snapshot", [[row("REFRESH-1")]], 100)
            terms = root / "terms.json"
            terms.write_text(json.dumps({
                "reviewer": "synthetic operator", "reference": "https://www.georisques.gouv.fr/cgu",
                "reviewed_at": "2026-10-20T12:00:00Z", "decision": "approved",
                "notes": "Synthetic test only; not actual legal acceptance.",
            }), encoding="utf-8")
            result = refresh(run_dir=root / "refresh", terms_review_path=terms,
                             raw_path=pages, fetch=False)
            self.assertEqual(result["report"]["lifecycle_status"], "candidate-ready")
            lifecycle_root = Path(result["lifecycle"]["run_dir"])
            self.assertTrue((lifecycle_root / "candidate-handoff" / "manifest.json").is_file())
            self.assertFalse((lifecycle_root / "released").exists())

    def test_pagination_validation_rejects_repeated_wrong_page_or_incomplete_snapshot(self):
        adapter = GeorisquesIcpeAnimalAdapter()
        with self.assertRaisesRegex(ValueError, "page number"):
            adapter._parse_payload_for_size({"results": 2, "page": 2, "total_pages": 1, "data": [row("A"), row("B")]}, 1, 100, 100)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pages = write_snapshot(root / "snapshot", [[row("A")], [row("B")]], 2)
            # The fixture's total says two pages, but each page is short for
            # its declared page_size and therefore cannot masquerade as complete.
            with self.assertRaisesRegex(ValueError, "expected"):
                adapter.parse_pages(pages)

    def test_acquisition_uses_bounded_filtered_api_pages_and_reconciles_counts(self):
        responses = {
            1: {"results": 3, "page": 1, "total_pages": 2, "data": [row("A"), row("B")]},
            2: {"results": 3, "page": 2, "total_pages": 2, "data": [row("C")]},
        }
        calls: list[dict] = []

        def fake_fetch(**kwargs):
            parsed = parse_qs(urlparse(kwargs["url"]).query)
            page = int(parsed["page"][0])
            calls.append(parsed)
            content = (json.dumps(responses[page], ensure_ascii=False) + "\n").encode()
            path = Path(kwargs["output_root"]) / CONFIG["source_id"] / kwargs["run_id"] / kwargs["artifact_name"]
            path.parent.mkdir(parents=True)
            path.write_bytes(content)
            kwargs["artifact_validator"](path, {"Content-Type": "application/json"})
            return {"artifact_path": str(path), "sha256": hashlib.sha256(content).hexdigest(),
                    "byte_size": len(content), "retrieved_at_utc": f"2026-10-20T12:00:0{page}Z",
                    "requested_url": kwargs["url"]}

        with tempfile.TemporaryDirectory() as temporary, patch(
                "pipeline.sources.france.georisques_icpe.acquire.fetch_source", fake_fetch):
            result = acquire_snapshot(output_root=temporary, terms_review_path="unused", run_id="test-run",
                                      page_size=2, max_pages=2, max_records=3,
                                      sleep_fn=lambda _seconds: None)
            self.assertEqual(result["results"], 3)
            self.assertEqual(result["total_pages"], 2)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]["nomenclature"], [",".join(CONFIG["animal_rubrics"])])
            self.assertEqual(calls[1]["page"], ["2"])
            self.assertTrue((Path(result["artifact_path"]) / "page-00002.json").is_file())

    def test_acquisition_rejects_duplicate_rows_and_record_bound_overrides(self):
        responses = {
            1: {"results": 2, "page": 1, "total_pages": 2, "data": [row("SAME")]},
            2: {"results": 2, "page": 2, "total_pages": 2, "data": [row("SAME")]},
        }

        def fake_fetch(**kwargs):
            page = int(parse_qs(urlparse(kwargs["url"]).query)["page"][0])
            content = (json.dumps(responses[page], ensure_ascii=False) + "\n").encode()
            path = Path(kwargs["output_root"]) / CONFIG["source_id"] / kwargs["run_id"] / kwargs["artifact_name"]
            path.parent.mkdir(parents=True)
            path.write_bytes(content)
            kwargs["artifact_validator"](path, {"Content-Type": "application/json"})
            return {"artifact_path": str(path), "sha256": hashlib.sha256(content).hexdigest(),
                    "byte_size": len(content), "retrieved_at_utc": "2026-10-20T12:00:00Z",
                    "requested_url": kwargs["url"]}

        with tempfile.TemporaryDirectory() as temporary, patch(
                "pipeline.sources.france.georisques_icpe.acquire.fetch_source", fake_fetch):
            with self.assertRaisesRegex(ValueError, "repeated an identical"):
                acquire_snapshot(output_root=temporary, terms_review_path="unused", run_id="dupe-run",
                                 page_size=1, max_pages=2, max_records=2,
                                 sleep_fn=lambda _seconds: None)
            with self.assertRaisesRegex(ValueError, "safety bounds"):
                acquire_snapshot(output_root=temporary, terms_review_path="unused", run_id="oversized-run",
                                 max_records=CONFIG["max_records"] + 1)


if __name__ == "__main__":
    unittest.main()
