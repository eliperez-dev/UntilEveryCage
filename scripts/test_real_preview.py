"""Offline safety tests for the real-preview lifecycle."""
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("real_preview", ROOT / "scripts" / "real_preview.py")
rp = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(rp)


class LifecycleTests(unittest.TestCase):
    def test_dispatcher_accepts_only_lifecycle_actions(self):
        for action in ("up", "status", "probe", "down", "reset"):
            with self.subTest(action=action), patch.object(rp, action, return_value={"ok": True}):
                self.assertEqual(rp.main([action]), 0)
        with self.assertRaises(SystemExit) as raised:
            rp.main(["import"])
        self.assertEqual(raised.exception.code, 2)

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
        request = rp.urllib.request.Request("http://127.0.0.1:38000/health/ready", headers={"X-Uec-Dev-Preview-Token": token})
        self.assertNotIn(token, request.full_url)


if __name__ == "__main__":
    unittest.main()
