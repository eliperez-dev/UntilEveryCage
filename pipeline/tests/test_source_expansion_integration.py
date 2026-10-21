from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import hashlib
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from pipeline.contracts.source_lifecycle import read_jsonl

from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
from pipeline.contracts.refresh import RefreshRequest
from pipeline.source_runtime_classification import require_production_preview_source
from pipeline.taxonomy_crosswalk import crosswalk_document, project_observation
from pipeline.sources.france.georisques_icpe.config import CONFIG as ICPE_CONFIG

ROOT = Path(__file__).parents[2]
IMPORTER_PATH = ROOT / "pipeline" / "scripts" / "maintenance" / "import-real-preview.py"
SPEC = importlib.util.spec_from_file_location("source_expansion_preview_importer", IMPORTER_PATH)
IMPORTER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(IMPORTER)


class SourceExpansionIntegrationTests(unittest.TestCase):
    def test_all_three_sources_dispatch_through_the_shared_refresh_catalog(self):
        catalog = RefreshCatalog()
        expected = {
            "no.fiskeridir.aquaculture": ("NorwayAquacultureRefreshAdapter", "no"),
            "gb.scot.marine.aquaculture": ("ScotlandAquacultureRefreshAdapter", "gb"),
            "us.epa.echo-animal-production": ("EpaEchoAnimalRefreshAdapter", "us"),
        }
        for source_id, (adapter_path, country) in expected.items():
            with self.subTest(source_id=source_id):
                registered = catalog.adapters[source_id]
                self.assertEqual(type(registered.adapter).__name__, adapter_path)
                self.assertEqual(registered.capabilities.country_code, country)
                self.assertTrue(registered.capabilities.live_callable)
                self.assertEqual(catalog.operation_metadata(source_id)["live_access"],
                                 "source-specific-acquisition-hook-registered")
                self.assertFalse(require_production_preview_source(source_id)["public_release"])

    def test_georisques_registers_with_private_live_terms_approval_and_publication_gate(self):
        catalog = RefreshCatalog()
        source_id = "fr.georisques.icpe.animal"
        registered = catalog.adapters[source_id]
        self.assertEqual(type(registered.adapter).__name__, "FirstWaveRefreshAdapter")
        self.assertEqual(registered.capabilities.country_code, "fr")
        self.assertTrue(registered.capabilities.live_callable)
        self.assertEqual(registered.capabilities.operational_classification, "live")
        self.assertEqual(catalog.operation_metadata(source_id)["live_access"],
                         "source-specific-acquisition-hook-registered")
        policy = json.loads((ROOT / "pipeline" / "preview-enabled-sources.json").read_text(encoding="utf-8"))["sources"][source_id]
        self.assertTrue(policy["enabled"])
        self.assertFalse(policy["public_release"])
        self.assertEqual(policy["runtime_classification"], "production-e2e")
        self.assertEqual(policy["terms_decision"], "approved")
        self.assertEqual(policy["terms_scope"], "private_acquisition_and_processing_only")
        self.assertEqual(policy["terms_review"], "pipeline/sources/france/georisques_icpe/terms-review.json")
        self.assertEqual(policy["freshness_max_days"], 14,
                         "14 days is the configured maximum age for a private acquired snapshot, not an upstream freshness guarantee")
        self.assertIs(type(policy["freshness_max_days"]), int)
        self.assertTrue({"name", "address", "coordinates", "activity_status_source",
                         "source_classification_codes"}.issubset(policy["allowed_preview_fields"]))

    def test_georisques_terms_policy_passes_shared_certifier_preflight_without_db_or_api(self):
        from scripts.certify_real_preview import CertificationError, certify

        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "incomplete-ledger.json"
            ledger.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(CertificationError, "runtime ledger is not an imported run"):
                certify("fr.georisques.icpe.animal", ledger,
                        "postgresql://127.0.0.1/unused", "http://127.0.0.1", "x" * 32)

    def test_enabled_preview_policies_have_importer_gate_metadata(self):
        policies = json.loads((ROOT / "pipeline" / "preview-enabled-sources.json").read_text(encoding="utf-8"))["sources"]
        enabled = {source_id: policy for source_id, policy in policies.items()
                   if policy.get("enabled") is True}
        self.assertTrue(enabled)
        for source_id, policy in enabled.items():
            with self.subTest(source_id=source_id):
                self.assertEqual(policy.get("terms_decision"), "approved")
                self.assertIs(policy.get("public_release"), False)
                max_age = policy.get("freshness_max_days")
                self.assertIs(type(max_age), int)
                self.assertGreaterEqual(max_age, 1)
                terms_path = policy.get("terms_review")
                self.assertIsInstance(terms_path, str)
                terms_file = (ROOT / terms_path).resolve()
                terms_file.relative_to(ROOT.resolve())
                self.assertTrue(terms_file.is_file())
                self.assertEqual(json.loads(terms_file.read_text(encoding="utf-8")).get("decision"), "approved")
                allowed_fields = policy.get("allowed_preview_fields")
                self.assertIsInstance(allowed_fields, list)
                self.assertTrue(allowed_fields)
                self.assertTrue(all(isinstance(field, str) and field for field in allowed_fields))

    def test_georisques_runs_through_normal_shared_fixture_dispatch(self):
        output = ROOT / ".georisques-shared-refresh-test"
        shutil.rmtree(output, ignore_errors=True)
        try:
            result = RefreshRunner().run(RefreshRequest(
                source_ids=("fr.georisques.icpe.animal",), mode="fixture", output_root=output,
                options={"run_id": "synthetic-contract"},
            ))
            source = result["results"][0]
            self.assertEqual(source["status"], "succeeded")
            self.assertEqual(source["summary"]["lifecycle_status"], "candidate-ready")
            self.assertTrue(source["summary"]["candidate_handoff"])
            self.assertFalse(source["publication"]["published"])
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_georisques_live_hook_builds_filtered_candidate_handoff_without_rows_in_summary(self):
        source_id = "fr.georisques.icpe.animal"
        raw_row = {
            "codeAIOT": "SYNTHETIC-AIOT", "siret": "11111111111111",
            "raisonSociale": "Nom synthétique privé", "adresse1": "Adresse synthétique",
            "codePostal": "01000", "codeInsee": "01001", "commune": "Commune synthétique",
            "longitude": 5.0, "latitude": 46.0, "codeNaf": "01.41Z",
            "etatActivite": "Synthetic status", "date_maj": "2026-10-20",
            "bovins": "12", "rubriques": [{"numeroRubrique": "2101", "nature": "synthetic"}],
            "inspections": [{"contact": "must not propagate"}],
        }

        def fake_fetch(**kwargs):
            query = parse_qs(urlparse(kwargs["url"]).query)
            self.assertEqual(query["nomenclature"], [",".join(ICPE_CONFIG["animal_rubrics"])])
            self.assertEqual(query["page"], ["1"])
            self.assertEqual(query["page_size"], ["100"])
            payload = {"results": 1, "page": 1, "total_pages": 1, "data": [raw_row]}
            content = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
            path = Path(kwargs["output_root"]) / source_id / kwargs["run_id"] / kwargs["artifact_name"]
            path.parent.mkdir(parents=True)
            path.write_bytes(content)
            kwargs["artifact_validator"](path, {"Content-Type": "application/json"})
            return {"artifact_path": str(path), "sha256": hashlib.sha256(content).hexdigest(),
                    "byte_size": len(content), "retrieved_at_utc": "2026-10-20T12:00:00Z",
                    "requested_url": kwargs["url"]}

        with tempfile.TemporaryDirectory() as temporary, patch(
                "pipeline.sources.france.georisques_icpe.acquire.fetch_source", fake_fetch):
            result = RefreshRunner().run(RefreshRequest(
                source_ids=(source_id,), mode="live-acquisition", output_root=Path(temporary), retries=0,
                options={"authorized_live_sources": [source_id],
                         "terms_review_paths": {source_id: str(ROOT / "pipeline/sources/france/georisques_icpe/terms-review.json")},
                         "timeout_seconds": 30.0},
            ))
            self.assertEqual(result["exit_status"], "ok")
            source = result["results"][0]
            self.assertEqual(source["status"], "succeeded")
            summary = source["summary"]
            self.assertTrue(summary["candidate_handoff"])
            self.assertEqual(summary["api_result_count"], 1)
            self.assertTrue(summary["animal_rubric_filter_only"])
            self.assertEqual(summary["native_name_retained_count"], 1)
            self.assertEqual(summary["source_address_retained_count"], 1)
            self.assertEqual(summary["source_coordinate_retained_count"], 1)
            self.assertNotIn("Nom synthétique privé", json.dumps(summary, ensure_ascii=False))
            source_root = Path(temporary) / result["run_id"] / "sources" / source_id
            handoff = read_jsonl(source_root / "candidate-handoff" / "normalized" / "records.jsonl")
            allowed = set(json.loads((ROOT / "pipeline" / "preview-enabled-sources.json").read_text(encoding="utf-8"))
                          ["sources"][source_id]["allowed_preview_fields"])
            unexpected_fields = set().union(*(set(record["normalized"]) for record in handoff)) - allowed
            self.assertFalse(unexpected_fields,
                             f"normalized source fields must satisfy the importer allowlist: {sorted(unexpected_fields)}")
            self.assertEqual(handoff[0]["normalized"]["name"], "Nom synthétique privé")
            self.assertEqual(handoff[0]["normalized"]["source_classification_codes"], ["2101"])
            self.assertEqual(handoff[0]["normalized"]["address"], "Adresse synthétique")
            self.assertFalse(handoff[0]["normalized"]["in_default_map_scope"])
            self.assertNotIn("inspections", json.dumps(handoff, ensure_ascii=False))

    def test_georisques_exact_rubric_taxonomy_has_no_mining_projection(self):
        source_id = "fr.georisques.icpe.animal"
        projected = project_observation({"source_id": source_id, "normalized": {
            "source_classification_codes": ["2101", "2210", "2510"]}})
        self.assertEqual(projected["taxonomy_mapping_status"], "mapped")
        self.assertEqual({item["primary"] for item in projected["taxonomy_assignments"]},
                         {"animal_keeping_and_production", "slaughter"})
        self.assertEqual(projected["taxonomy_mapping_method"], "direct")
        document = crosswalk_document(source_id)
        self.assertIn("2101", {code for rule in document["rules"] for code in rule["source_codes"]})
        self.assertNotIn("2510", {code for rule in document["rules"] for code in rule["source_codes"]})

    def test_preview_contracts_keep_source_specific_metadata_and_private_boundaries(self):
        policies = json.loads((ROOT / "pipeline" / "preview-enabled-sources.json").read_text(encoding="utf-8"))["sources"]
        for source_id in ("no.fiskeridir.aquaculture", "gb.scot.marine.aquaculture",
                          "us.epa.echo-animal-production"):
            policy = policies[source_id]
            self.assertTrue(policy["enabled"])
            self.assertFalse(policy["public_release"])
            self.assertTrue(policy["terms_review"])
            self.assertIn("coordinates", policy["allowed_preview_fields"])
        scotland = policies["gb.scot.marine.aquaculture"]["allowed_preview_fields"]
        self.assertTrue({"source_status_code", "source_status", "source_projected_coordinates",
                         "source_feature_count", "source_feature_rows"}.issubset(scotland))
        epa = policies["us.epa.echo-animal-production"]["allowed_preview_fields"]
        self.assertTrue({"industry_classification_basis", "regulated_program", "cafo_status",
                         "operating_status", "coordinate_provenance_state"}.issubset(epa))
        self.assertEqual(IMPORTER.SOURCE_MEDIA_TYPES["no.fiskeridir.aquaculture"], "application/geo+json")
        self.assertEqual(IMPORTER.SOURCE_MEDIA_TYPES["gb.scot.marine.aquaculture"], "application/geo+json")
        self.assertEqual(IMPORTER.SOURCE_MEDIA_TYPES["us.epa.echo-animal-production"], "application/zip")
        self.assertEqual(IMPORTER.SOURCE_MEDIA_TYPES["fr.georisques.icpe.animal"], "application/json")

    def test_georisques_private_parse_retains_native_name_address_and_unmapped_coordinates(self):
        source_id = "fr.georisques.icpe.animal"
        normalized = {
            "establishment_id": "SYNTHETIC-AIOT", "name": "Ferme privée synthétique",
            "trading_name": "Ferme privée synthétique", "address": "1 Rue Exemple",
            "postal_code": "01000", "municipality": "Commune Synthétique", "country_code": "FR",
            "coordinates": {"longitude": 5.0, "latitude": 46.0,
                            "precision": "source-coordinate-crs-unverified"},
            "source_classification_codes": ["2101"], "source_classification_labels": ["cattle holdings"],
            "activity_categories": ["animal_keeping"], "activity_status_source": "source value",
            "privacy_gate": "pending-review", "in_default_map_scope": False,
            "map_scope_reason": "pending coordinate CRS review",
        }
        parsed = IMPORTER.parse_row(source_id, {
            "source_id": source_id, "source_record_key": "SYNTHETIC-AIOT|row-1",
            "source_values": {"raisonSociale": "Ferme privée synthétique"}, "normalized": normalized,
        })
        self.assertEqual(parsed[11], "Ferme privée synthétique")
        self.assertEqual(parsed[18], "1 Rue Exemple")
        self.assertEqual((parsed[5], parsed[6]), (46.0, 5.0))
        self.assertFalse(parsed[16])


if __name__ == "__main__":
    unittest.main()
