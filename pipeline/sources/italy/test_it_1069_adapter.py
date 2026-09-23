import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import shutil

from pipeline.contracts.adapter_contract import SourceArtifact
from .it_1069_adapter import Italy1069Adapter


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_1069.csv"


class Italy1069Tests(unittest.TestCase):
    def test_synthetic_parse_keeps_abp_dimensions_and_link_unresolved(self):
        parsed = Italy1069Adapter().parse_bytes(FIXTURE.read_bytes())
        self.assertEqual(len(parsed["accepted"]), 2)
        first = parsed["accepted"][0]["normalized"]
        self.assertEqual(first["abp_category_code"], "CAT-A")
        self.assertEqual(first["activity_state"], "source-code-preserved-unmapped")
        second = parsed["accepted"][1]["normalized"]
        self.assertIsNone(second["linked_853_recognition_number"])
        self.assertEqual(second["cross_source_link_state"], "unreviewed-link-value-retained-only")
        self.assertEqual(first["facility_identity_state"], "source-id-only-unreviewed")
        self.assertEqual(first["establishment_id"], "SYNTH-ABP-001")

    def test_unknown_status_and_duplicate_id_quarantine(self):
        data = ("source_observation_id,abp_category_code,source_activity_code,source_status,effective_date,linked_853_recognition_number\n"
                "X,C,A,other,,\nX,C,A,active,,\n").encode()
        result = Italy1069Adapter().parse_bytes(data)
        self.assertEqual(len(result["quarantined"]), 2)
        self.assertIn("unknown_source_status", result["quarantined"][0]["reasons"])
        self.assertIn("repeated_source_observation_id", result["quarantined"][1]["reasons"])

    def test_schema_fails_closed_and_run_records_provenance(self):
        adapter = Italy1069Adapter()
        self.assertRaises(ValueError, adapter.parse_bytes, b"id,name\n1,test\n")
        raw = FIXTURE.read_bytes()
        artifact = SourceArtifact("https://www.dati.salute.gov.it/", "2026-01-01T00:00:00Z",
                                  hashlib.sha256(raw).hexdigest(), len(raw), code_version=adapter.adapter_version,
                                  config_version=adapter.schema_version)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as root:
            manifest = adapter.run(FIXTURE, root, artifact)
            self.assertEqual(manifest["source_id"], "it.1069-2009")
            self.assertEqual(manifest["input_rows"], 2)
            self.assertEqual(manifest["normalized_rows"], 2)
            self.assertTrue((Path(root) / "manifest.json").is_file())

    def test_shared_runner_fixture_and_candidate_import_handoff(self):
        from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
        from pipeline.contracts.refresh import RefreshRequest

        output = Path(__file__).with_name(".it1069-runner-tests")
        shutil.rmtree(output, ignore_errors=True)
        try:
            seen = []
            def importer(run_dir, database_url):
                seen.append((Path(run_dir), database_url))
                # Importers receive only the private source run directory.
                manifests = list(Path(run_dir).rglob("candidate-handoff/manifest.json"))
                self.assertTrue(manifests)
                return {"status": "imported", "inserted": 2, "release_created": False}

            catalog = RefreshCatalog()
            self.assertIn("it.1069-2009", catalog.adapters)
            runner = RefreshRunner(catalog, candidate_importer=importer)
            request = RefreshRequest(source_ids=("it.1069-2009",), mode="fixture",
                output_root=output, import_candidates=True,
                database_url="postgresql://127.0.0.1/uec-test")
            first = runner.run(request)
            self.assertEqual(first["counts"]["succeeded"], 1)
            self.assertEqual(first["results"][0]["summary"]["normalized_rows"], 2)
            self.assertEqual(first["results"][0]["summary"]["publication_state"], "human-gate-required")
            self.assertEqual(first["results"][0]["summary"]["candidate_import"]["inserted"], 2)
            self.assertEqual(len(seen), 1)
            resumed = runner.run(RefreshRequest(source_ids=("it.1069-2009",), mode="fixture",
                output_root=output, import_candidates=True,
                database_url="postgresql://127.0.0.1/uec-test", resume=True))
            self.assertEqual(resumed["counts"]["resumed"], 1)
            self.assertEqual(len(seen), 1)
            local_copy = output / "local-artifact.csv"
            raw = FIXTURE.read_bytes()
            local_copy.write_bytes(raw)
            (output / "acquisition-metadata.json").write_text(json.dumps({
                "source_url": "https://example.invalid/synthetic-abp.csv",
                "retrieved_at_utc": "2026-01-02T00:00:00Z",
                "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
                "terms_review_reference": "synthetic-test-reference",
            }), encoding="utf-8")
            local = runner.run(RefreshRequest(source_ids=("it.1069-2009",), mode="local-artifact",
                artifact_paths={"it.1069-2009": str(local_copy)}, output_root=output,
                import_candidates=True, database_url="postgresql://127.0.0.1/uec-test"))
            self.assertEqual(local["counts"]["succeeded"], 1)
            self.assertEqual(len(seen), 2)
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_invalid_local_artifact_fails_without_releasing_prior_state(self):
        from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
        from pipeline.contracts.refresh import RefreshRequest

        output = Path(__file__).with_name(".it1069-runner-failure-tests")
        shutil.rmtree(output, ignore_errors=True)
        output.mkdir(parents=True)
        bad = output / "wrong-schema.csv"
        bad.write_text("id,name\nsynthetic,not-abp\n", encoding="utf-8")
        bad_bytes = bad.read_bytes()
        (output / "acquisition-metadata.json").write_text(json.dumps({
            "source_url": "https://example.invalid/synthetic-abp.csv",
            "retrieved_at_utc": "2026-01-02T00:00:00Z",
            "sha256": hashlib.sha256(bad_bytes).hexdigest(), "byte_size": len(bad_bytes),
            "terms_review_reference": "synthetic-test-reference",
        }), encoding="utf-8")
        try:
            result = RefreshRunner(RefreshCatalog()).run(RefreshRequest(
                source_ids=("it.1069-2009",), mode="local-artifact",
                artifact_paths={"it.1069-2009": str(bad)}, output_root=output / "runs",
                options={"previous_valid_states": {"it.1069-2009": {"state": "validated-prior", "verified": True}}},
            ))
            item = result["results"][0]
            self.assertEqual(item["status"], "failed")
            self.assertEqual(item["operational"]["previous_valid_state"]["state"], "validated-prior")
            self.assertTrue(item["operational"]["previous_valid_state"]["verified"])
            self.assertNotIn("publication", item)
            self.assertEqual(item["acquisition_classification"], "schema-drift")
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_all_eligible_registration_and_live_acquisition_fail_closed(self):
        from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
        from pipeline.contracts.refresh import RefreshRequest

        catalog = RefreshCatalog()
        eligible = catalog.select(RefreshRequest(all_eligible=True, mode="fixture"))
        self.assertIn("it.1069-2009", eligible)
        output = Path(__file__).with_name(".it1069-live-block-tests")
        shutil.rmtree(output, ignore_errors=True)
        try:
            result = RefreshRunner(catalog).run(RefreshRequest(source_ids=("it.1069-2009",),
                mode="live-acquisition", output_root=output,
                options={"authorized_live_sources": ["it.1069-2009"], "terms_review_path": "synthetic-reference"}))
            self.assertEqual(result["counts"]["failed"], 1)
            self.assertEqual(result["results"][0]["acquisition_classification"], "assisted")
        finally:
            shutil.rmtree(output, ignore_errors=True)
