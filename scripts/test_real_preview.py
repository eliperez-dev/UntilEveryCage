"""Offline safety tests for the real-preview lifecycle."""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("real_preview", ROOT / "scripts" / "real_preview.py")
rp = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(rp)


class LifecycleTests(unittest.TestCase):
    def test_private_map_readiness_uses_scope_aware_importer_count(self):
        map_visible, readiness = rp._private_map_readiness(
            "fr.georisques.icpe.animal",
            {"map_visible_count": 0, "numeric_coordinate_count": 12_478,
             "coarse_placeable_facility_count": 0},
            None,
        )
        self.assertEqual(map_visible, 0)
        self.assertEqual(readiness, "unmapped")

    def test_graph_opt_in_reports_missing_handoff_as_not_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            result = rp._materialize_private_graph(Path(directory))
        self.assertEqual(result, {"status": "not_supported", "reason": "validated_graph_handoff_missing"})

    def test_graph_materializer_uses_separate_database_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            handoff = Path(directory)
            (handoff / "graph-candidates.jsonl").write_text("", encoding="utf-8")
            (handoff / "graph-candidates-manifest.json").write_text("{}", encoding="utf-8")
            completed = rp.subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps({
                "status": "completed", "source_assertion_rows": 2, "edge_counts_by_type": {"exact": 1},
            }), stderr="")
            env = {"UEC_GRAPH_DATABASE_URL": "postgresql://graph-writer@localhost/private",
                   "UEC_GRAPH_DATABASE_NAME": "uec_private_graph_test",
                   "UEC_GRAPH_DATABASE_PURPOSE": "private-graph-materialization-v1",
                   "UEC_DATABASE_URL": "postgresql://serving@localhost/preview"}
            with patch.object(rp, "ROOT", Path(directory)), patch.dict(rp.os.environ, env, clear=True), \
                    patch.object(rp.subprocess, "run", return_value=completed) as run:
                result = rp._materialize_private_graph(handoff)
            self.assertEqual(result["status"], "materialized")
            child_env = run.call_args.kwargs["env"]
            self.assertNotIn("UEC_DATABASE_URL", child_env)
            self.assertEqual(child_env["UEC_GRAPH_DATABASE_URL"], env["UEC_GRAPH_DATABASE_URL"])

    def test_graph_materializer_failure_is_separate_from_source_import(self):
        with tempfile.TemporaryDirectory() as directory:
            handoff = Path(directory)
            (handoff / "graph-candidates.jsonl").touch()
            (handoff / "graph-candidates-manifest.json").touch()
            env = {"UEC_GRAPH_DATABASE_URL": "postgresql://graph-writer@localhost/private",
                   "UEC_GRAPH_DATABASE_NAME": "uec_private_graph_test",
                   "UEC_GRAPH_DATABASE_PURPOSE": "private-graph-materialization-v1"}
            failed = rp.subprocess.CompletedProcess(args=[], returncode=2,
                stdout=json.dumps({"status": "blocked", "error_type": "PermissionDenied"}), stderr="")
            with patch.dict(rp.os.environ, env, clear=True), patch.object(rp.subprocess, "run", return_value=failed):
                result = rp._materialize_private_graph(handoff)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error_type"], "PermissionDenied")

    def test_source_lock_is_nonblocking_and_reusable(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(rp, "ROOT", Path(directory)):
            with rp.source_lock("it.853-2004"):
                with self.assertRaisesRegex(rp.PreviewError, "already running"):
                    with rp.source_lock("it.853-2004"):
                        pass
            with rp.source_lock("it.853-2004"):
                pass

    def test_refresh_database_url_requires_loopback_when_explicit(self):
        with patch.dict(rp.os.environ, {"UEC_DATABASE_URL": "postgresql://user:secret@remote.example/db"}, clear=False):
            with self.assertRaisesRegex(rp.PreviewError, "loopback"):
                rp._local_database_url()

    def test_italy_runtime_ledger_evidence_is_row_free_and_exact_run_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            source_dir = Path(directory) / "source"
            metadata_dir = source_dir / "acquisition" / "it.853-2004" / "run-1"
            metadata_dir.mkdir(parents=True)
            (metadata_dir / "acquisition-metadata.json").write_text(json.dumps({
                "source_id": "it.853-2004", "run_id": "run-1",
                "catalog_url": "https://www.dati.salute.gov.it/catalog/",
                "catalog_final_url": "https://www.dati.salute.gov.it/catalog/",
                "catalog_sha256": "a" * 64, "final_url": "https://www.dati.salute.gov.it/current.csv",
                "retrieved_at_utc": "2026-09-23T00:00:00Z", "requested_at_utc": "2026-09-23T00:00:00Z",
                "sha256": "b" * 64, "byte_size": 42, "filename_publication_date": "20260923",
                "adapter_version": "it-853-candidate-v2", "config_version": "it-853-csv-v2.0",
            }), encoding="utf-8")
            evidence = rp._italy_acquisition_evidence(source_dir, "it.853-2004", "run-1")
            self.assertEqual(evidence["raw_sha256"], "b" * 64)
            self.assertEqual(evidence["catalog_sha256"], "a" * 64)
            self.assertNotIn("raw_rows", evidence)
            self.assertNotIn("token", evidence)
            with self.assertRaises(rp.PreviewError):
                rp._italy_acquisition_evidence(source_dir, "it.853-2004", "different-run")

    def test_dispatcher_accepts_only_lifecycle_actions(self):
        for action in ("up", "status", "probe", "down", "reset"):
            with self.subTest(action=action), patch.object(rp, action, return_value={"ok": True}):
                self.assertEqual(rp.main([action]), 0)
        with self.assertRaises(SystemExit) as raised:
            rp.main(["import"])
        self.assertEqual(raised.exception.code, 2)
        with patch.object(rp, "refresh_source") as refresh:
            self.assertEqual(rp.main(["refresh"]), 2)
            refresh.assert_not_called()

    def test_graph_option_is_opt_in_only_on_refresh(self):
        with patch.object(rp, "refresh_source", return_value={"status": "imported", "ok": True}) as refresh:
            self.assertEqual(rp.main(["refresh", "--source", "it.1069-2009", "--materialize-private-graph"]), 0)
            refresh.assert_called_once_with("it.1069-2009", None, materialize_private_graph=True)
        self.assertEqual(rp.main(["status", "--materialize-private-graph"]), 2)

    def test_fresh_source_refresh_binds_evidence_root_before_source_validation(self):
        source_id = "no.fiskeridir.aquaculture"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_root = root / "runs"
            runner_run_id = "canonical-refresh-run"
            source_root = output_root / runner_run_id / "sources" / source_id
            acquisition_dir = source_root / "acquisition" / source_id / runner_run_id
            acquisition_dir.mkdir(parents=True)
            (acquisition_dir / "acquisition-metadata.json").write_text(json.dumps({
                "source_id": source_id, "run_id": runner_run_id, "feature_count": 1,
                "object_id_count": 1, "retrieved_unique_object_id_count": 1,
                "page_count": 1, "coordinates_checked": 1, "artifact_sha256": "a" * 64,
                "artifact_byte_size": 1,
            }), encoding="utf-8")
            (source_root / "candidate-handoff").mkdir()
            policy_path = root / "pipeline" / "preview-enabled-sources.json"
            policy_path.parent.mkdir(parents=True)
            policy_path.write_text(json.dumps({"contract_version": "test-v1", "sources": {
                source_id: {"enabled": True, "terms_review": "terms.json",
                            "allowed_preview_fields": ["facility_name", "coordinates"]}
            }}), encoding="utf-8")
            refresh_result = {"exit_status": "ok", "run_id": runner_run_id,
                              "completed_at_utc": "2026-10-20T00:00:00Z",
                              "results": [{"source_id": source_id, "status": "succeeded", "summary": {
                                  "input_rows": 1, "candidate_observation_rows": 1, "quarantined_rows": 0,
                                  "source_object_id_count": 1, "source_coordinate_count_checked": 1,
                                  "candidate_handoff_sha256": "b" * 64, "schema_fingerprint": "c" * 64,
                              }}], "publication": {"release_created": False}}
            importer_result = {"status": "imported", "normalized_sha256": "d" * 64,
                               "observation_count": 1, "facility_candidate_count": 1,
                               "numeric_coordinate_count": 1, "map_visible_count": 1,
                               "public_release_count": 0, "public_projection_count": 0}
            completed = rp.subprocess.CompletedProcess(args=[], returncode=0,
                stdout=json.dumps(refresh_result), stderr="")
            imported = rp.subprocess.CompletedProcess(args=[], returncode=0,
                stdout=json.dumps(importer_result), stderr="")
            with patch.object(rp, "ROOT", root), patch.object(rp, "_local_database_url", return_value="postgresql://localhost/test"), \
                    patch.dict(rp.os.environ, {"UEC_REAL_PREVIEW_RUNS_ROOT": str(output_root)}, clear=False), \
                    patch.object(rp.subprocess, "run", side_effect=[completed, imported]) as run:
                result = rp._refresh_source_locked(source_id)

            self.assertEqual(result["status"], "imported")
            self.assertEqual(run.call_count, 2)
            importer_args = run.call_args_list[1].args[0]
            self.assertEqual(importer_args[importer_args.index("--root") + 1], str(source_root))
            ledger = json.loads(Path(result["ledger"]).read_text(encoding="utf-8"))
            self.assertEqual(ledger["acquisition"]["run_id"], runner_run_id)
            self.assertEqual(ledger["public_rows"], 0)

    def test_offline_actions_are_scoped_to_a_dedicated_owned_project(self):
        previous_project, previous_volume = rp.PROJECT, rp.VOLUME
        try:
            with patch.object(rp, "up", return_value={"ok": True}) as up:
                self.assertEqual(rp.main(["offline-up"]), 0)
                up.assert_called_once_with(offline_handoff=True)
                self.assertEqual(rp.PROJECT, "uec-offline-fsis-private")
                self.assertEqual(rp.VOLUME, "uec-offline-fsis-private-postgres")
            with patch.object(rp, "down", return_value=None) as down:
                self.assertEqual(rp.main(["offline-down"]), 0)
                down.assert_called_once_with()
                self.assertEqual(rp.PROJECT, "uec-offline-fsis-private")
            with patch.object(rp, "reset", return_value=None) as reset:
                self.assertEqual(rp.main(["offline-reset"]), 0)
                reset.assert_called_once_with()
                self.assertEqual(rp.PROJECT, "uec-offline-fsis-private")
            with patch.object(rp, "offline_resume", return_value={"ok": True}) as resume:
                self.assertEqual(rp.main(["offline-resume"]), 0)
                resume.assert_called_once_with()
                self.assertEqual(rp.PROJECT, "uec-offline-fsis-private")
        finally:
            rp.PROJECT, rp.VOLUME = previous_project, previous_volume

    def test_default_private_root_is_private_drive(self):
        self.assertEqual(str(rp.PRIVATE_ROOT), r"D:\UntilEveryCage-private")

    def test_missing_importer_fails_before_resources(self):
        with patch.object(rp, "shutil") as shutil_mock, patch.object(rp, "PRIVATE_ROOT") as private_root, patch.object(rp, "IMPORTER", Path("missing-importer")), patch.object(rp, "subprocess") as subprocess:
            shutil_mock.which.return_value = "tool"
            subprocess.run.return_value.returncode = 0
            private_root.is_dir.return_value = True
            with self.assertRaisesRegex(rp.PreviewError, "lane 1 importer"):
                rp.prerequisites()

    def test_resource_ownership_rejects_unexpected_volume(self):
        def fake(args):
            if "volume" in args:
                return [{"Name": "other", "Labels": "com.docker.compose.project=uec-real-preview"}]
            return []
        with patch.object(rp, "_docker_json", side_effect=fake):
            with self.assertRaisesRegex(rp.PreviewError, "ambiguously owned volume"):
                rp.verify_resources()

    def test_process_state_requires_exact_project(self):
        with patch.object(rp, "_state") as state_path:
            state_path.return_value.exists.return_value = True
            state_path.return_value.read_text.return_value = json.dumps({"project": "uec-local-v2"})
            with self.assertRaisesRegex(rp.PreviewError, "invalid ownership"):
                rp._read_state()

    def test_windows_missing_process_is_not_reported_as_running(self):
        completed = rp.subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch.object(rp.os, "name", "nt"), patch.object(rp.shutil, "which", return_value="powershell"), patch.object(rp.subprocess, "run", return_value=completed):
            self.assertFalse(rp._pid_exists(12345))

    def test_offline_resume_validates_latest_snapshots_and_zero_publication(self):
        counts_by_source = {
            "au.npi.facilities": (8116, 8116, 0, 0, 0),
            "ca.ontario.meat-plants": (460, 460, 0, 0, 0),
        }
        def rows_for(expected):
            return [(source, "a" * 64, "b" * 64, "c" * 64, *counts, 0,
                     counts[0], counts[1], 1) for source, counts in expected.items()]
        valid = rows_for(counts_by_source)
        summary = rp._validate_offline_resume_aggregates(
            valid, {"releases": 0, "release_members": 0},
            {"054_public_suppression_generation"}, rp.OFFLINE_RESUME_REQUIRED_TABLES)
        expected_observations = sum(item[0] for item in counts_by_source.values())
        expected_candidates = sum(item[1] for item in counts_by_source.values())
        expected_map_visible = len(counts_by_source) - 2
        self.assertEqual(summary, {
            "observation_count": expected_observations,
            "source_scoped_candidate_count": expected_candidates,
            "numeric_coordinate_count": expected_map_visible,
            "coarse_placeable_count": 0,
            "map_visible_count": expected_map_visible,
            "unmapped_facility_count": expected_candidates - expected_map_visible,
            "public_release_count": 0, "public_projection_count": 0,
        })
        invalid_cases = [
            ([("extra.source", *valid[0][1:]), *valid], {"releases": 0}, {"054_public_suppression_generation"}, rp.OFFLINE_RESUME_REQUIRED_TABLES),
            ([valid[0], valid[0]], {"releases": 0}, {"054_public_suppression_generation"}, rp.OFFLINE_RESUME_REQUIRED_TABLES),
            ([(*valid[0][:2], "not-a-hash", *valid[0][3:]), *valid[1:]], {"releases": 0}, {"054_public_suppression_generation"}, rp.OFFLINE_RESUME_REQUIRED_TABLES),
            (valid, {"releases": 1}, {"054_public_suppression_generation"}, rp.OFFLINE_RESUME_REQUIRED_TABLES),
            (valid, {"releases": 0}, set(), rp.OFFLINE_RESUME_REQUIRED_TABLES),
        ]
        for rows, publication, migrations, tables in invalid_cases:
            with self.subTest(publication=publication, migrations=migrations, sources=len(rows)), self.assertRaises(rp.PreviewError):
                rp._validate_offline_resume_aggregates(rows, publication, migrations, tables)

    def test_http_never_places_token_in_url(self):
        token = "secret-value"
        request = rp.urllib.request.Request(f"http://127.0.0.1:{rp.API_PORT}/health/ready", headers={"X-Uec-Dev-Preview-Token": token})
        self.assertNotIn(token, request.full_url)

    def test_strict_refresh_uses_empty_private_bootstrap_and_restores_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "source-preview-ledger.json"
            observed = {}
            down = Mock()

            def start():
                observed["bootstrap"] = rp.os.environ.get("UEC_REAL_PREVIEW_EMPTY_BOOTSTRAP")
                rp.SESSION_TOKEN = "in-memory-test-token"
                return {"status": "ready"}

            cert = types.ModuleType("scripts.certify_real_preview")
            cert.certify = lambda *args: {"status": "certified", "run_id": "run-1",
                                           "counts": {}, "checks": {}, "claims": {}}
            environment = {"UEC_REAL_PREVIEW_EMPTY_BOOTSTRAP": "0"}
            with patch.object(rp, "PRIVATE_ROOT", root), patch.object(rp, "status", return_value={"database": "stopped", "api": False}), \
                    patch.object(rp, "up", side_effect=start), patch.object(rp, "down", down), \
                    patch.object(rp, "refresh_source", return_value={"ledger": str(ledger)}), \
                    patch.object(rp, "_local_database_url", return_value="postgresql://localhost/test"), \
                    patch.dict(rp.os.environ, environment, clear=False), patch.dict(sys.modules, {"scripts.certify_real_preview": cert}):
                result = rp.strict_refresh("dk.smiley")
                self.assertEqual(rp.os.environ.get("UEC_REAL_PREVIEW_EMPTY_BOOTSTRAP"), "0")

            self.assertEqual(result["status"], "certified")
            self.assertEqual(observed["bootstrap"], "1")
            down.assert_called_once()

    def test_strict_refresh_stops_its_project_if_startup_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            down = Mock()
            with patch.object(rp, "PRIVATE_ROOT", root), patch.object(rp, "status", return_value={"database": "stopped", "api": False}), \
                    patch.object(rp, "up", side_effect=rp.PreviewError("startup failed")), patch.object(rp, "down", down), \
                    patch.dict(rp.os.environ, {"UEC_REAL_PREVIEW_EMPTY_BOOTSTRAP": "0"}, clear=False):
                with self.assertRaisesRegex(rp.PreviewError, "startup failed"):
                    rp.strict_refresh("dk.smiley")
                self.assertEqual(rp.os.environ.get("UEC_REAL_PREVIEW_EMPTY_BOOTSTRAP"), "0")
            down.assert_called_once()


if __name__ == "__main__":
    unittest.main()
