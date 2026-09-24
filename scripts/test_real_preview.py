"""Offline safety tests for the real-preview lifecycle."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("real_preview", ROOT / "scripts" / "real_preview.py")
rp = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(rp)


class LifecycleTests(unittest.TestCase):
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

    def test_http_never_places_token_in_url(self):
        token = "secret-value"
        request = rp.urllib.request.Request(f"http://127.0.0.1:{rp.API_PORT}/health/ready", headers={"X-Uec-Dev-Preview-Token": token})
        self.assertNotIn(token, request.full_url)


if __name__ == "__main__":
    unittest.main()
