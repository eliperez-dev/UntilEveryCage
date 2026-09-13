import hashlib
import importlib.util
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import sys


SCRIPT = Path(__file__).parents[1] / "scripts" / "stages" / "acquire-denmark-smiley.py"
SPEC = importlib.util.spec_from_file_location("acquire_denmark_smiley", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

RUNNER_SCRIPT = Path(__file__).parents[1] / "run-denmark-pipeline.py"
RUNNER_SPEC = importlib.util.spec_from_file_location("run_denmark_pipeline", RUNNER_SCRIPT)
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(RUNNER)


class FixtureHandler(BaseHTTPRequestHandler):
    payload = b"<Root><Row /></Root>"

    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/xml")
            self.end_headers()
            return
        if self.path == "/error":
            self.send_response(503)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/xml; charset=utf-8")
        self.send_header("ETag", '"fixture-v1"')
        self.send_header("Last-Modified", "Mon, 01 Jan 2024 00:00:00 GMT")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *_):
        pass


class AcquisitionServer:
    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_port}"

    def __exit__(self, *_):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()


class DenmarkAcquisitionTests(unittest.TestCase):
    def write_terms_review(self, root: Path, decision="approved") -> Path:
        path = root / "terms.json"
        path.write_text(json.dumps({
            "reviewer": "test-maintainer",
            "reference": "https://example.test/terms",
            "reviewed_at": "2026-09-13T00:00:00Z",
            "decision": decision,
            "notes": "Synthetic test approval.",
        }), encoding="utf-8")
        return path

    def test_local_file_archives_hash_size_and_deterministic_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthetic.xml"
            payload = b"<Root><Row /></Root>"
            source.write_bytes(payload)
            metadata = MODULE.archive_local_file(source, root / "raw", run_id="test-run", retrieved_at="2026-09-13T00:00:00Z")
            run_dir = root / "raw" / "dk.smiley" / "test-run"
            self.assertEqual(metadata["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(metadata["byte_size"], len(payload))
            self.assertEqual(metadata["terms_review"], "not_required_for_local_file")
            self.assertEqual((run_dir / "Smileydata.xml").read_bytes(), payload)
            self.assertEqual(json.loads((run_dir / "acquisition-metadata.json").read_text(encoding="utf-8")), metadata)

    def test_fetch_requires_affirmative_terms_review(self):
        with tempfile.TemporaryDirectory() as directory, AcquisitionServer() as base_url:
            root = Path(directory)
            with self.assertRaises(MODULE.AcquisitionError):
                MODULE.fetch(base_url + "/xml", root / "raw", run_id="missing-review", terms_review_path=None, timeout_seconds=1, max_bytes=1024)
            rejected = self.write_terms_review(root, decision="rejected")
            with self.assertRaises(MODULE.AcquisitionError):
                MODULE.fetch(base_url + "/xml", root / "raw", run_id="rejected-review", terms_review_path=rejected, timeout_seconds=1, max_bytes=1024)
            malformed = root / "malformed-terms.json"
            malformed.write_text('{"reviewer": "test-maintainer"}', encoding="utf-8")
            with self.assertRaises(MODULE.AcquisitionError):
                MODULE.fetch(base_url + "/xml", root / "raw", run_id="malformed-review", terms_review_path=malformed, timeout_seconds=1, max_bytes=1024)
            self.assertFalse((root / "raw" / "dk.smiley" / "missing-review" / "Smileydata.xml").exists())

    def test_fetch_archives_redirect_final_url_and_headers(self):
        with tempfile.TemporaryDirectory() as directory, AcquisitionServer() as base_url:
            root = Path(directory)
            metadata = MODULE.fetch(base_url + "/redirect", root / "raw", run_id="network-run", terms_review_path=self.write_terms_review(root), timeout_seconds=1, max_bytes=1024)
            self.assertEqual(metadata["requested_url"], base_url + "/redirect")
            self.assertEqual(metadata["final_url"], base_url + "/xml")
            self.assertEqual(metadata["response_headers"]["ETag"], '"fixture-v1"')
            self.assertEqual(metadata["publication_metadata"]["Last-Modified"], "Mon, 01 Jan 2024 00:00:00 GMT")
            self.assertTrue((root / "raw" / "dk.smiley" / "network-run" / "Smileydata.xml").is_file())

    def test_fetch_failure_leaves_no_partial_artifact(self):
        with tempfile.TemporaryDirectory() as directory, AcquisitionServer() as base_url:
            root = Path(directory)
            review = self.write_terms_review(root)
            with self.assertRaises(MODULE.AcquisitionError):
                MODULE.fetch(base_url + "/xml", root / "raw", run_id="too-large", terms_review_path=review, timeout_seconds=1, max_bytes=1)
            with self.assertRaises(MODULE.AcquisitionError):
                MODULE.fetch(base_url + "/error", root / "raw", run_id="server-error", terms_review_path=review, timeout_seconds=1, max_bytes=1024)
            raw_root = root / "raw" / "dk.smiley"
            self.assertFalse(any(raw_root.rglob("Smileydata.xml")) if raw_root.exists() else False)
            self.assertFalse(any(raw_root.rglob("*.part")) if raw_root.exists() else False)

    def test_runner_fetch_front_edge_never_invokes_import_or_promotion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw"
            output_dir = root / "staging"
            terms = self.write_terms_review(root)
            stages = []

            def fake_stage(name, _script, args):
                stages.append(name)
                if name == "acquire":
                    run_id = args[args.index("--run-id") + 1]
                    artifact = raw_root / "dk.smiley" / run_id / "Smileydata.xml"
                    artifact.parent.mkdir(parents=True)
                    artifact.write_bytes(FixtureHandler.payload)
                    (artifact.parent / "acquisition-metadata.json").write_text(json.dumps({"requested_url": "https://example.test/xml", "final_url": "https://example.test/final"}), encoding="utf-8")

            with patch.object(RUNNER, "run_stage", side_effect=fake_stage), \
                 patch.object(RUNNER, "artifact_manifest", return_value=output_dir / "pipeline-manifest.json"), \
                 patch.object(sys, "argv", ["run-denmark-pipeline.py", "--fetch", "--terms-review", str(terms), "--raw-output-root", str(raw_root), "--run-id", "controlled-run", "--output-dir", str(output_dir)]):
                self.assertEqual(RUNNER.main(), 0)
            self.assertEqual(stages, ["acquire", "parse", "normalize", "classify", "validate", "geocode_queue"])
            self.assertFalse({"import", "promote", "publish"} & set(stages))

    def test_runner_preserves_existing_local_input_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "local.xml"
            source.write_bytes(FixtureHandler.payload)
            stages = []

            def fake_stage(name, _script, _args):
                stages.append(name)

            with patch.object(RUNNER, "run_stage", side_effect=fake_stage), \
                 patch.object(RUNNER, "artifact_manifest", return_value=root / "pipeline-manifest.json"), \
                 patch.object(sys, "argv", ["run-denmark-pipeline.py", str(source), "--output-dir", str(root / "staging")]):
                self.assertEqual(RUNNER.main(), 0)
            self.assertEqual(stages, ["parse", "normalize", "classify", "validate", "geocode_queue"])


if __name__ == "__main__":
    unittest.main()
