import hashlib
import importlib
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from pipeline.common.acquisition import AcquisitionError, fetch_source

from .refresh import _validate_download, refresh


ROOT = Path(__file__).parent


class FsisRefreshTests(unittest.TestCase):
    def _terms(self, root: Path) -> Path:
        path = root / "terms.json"
        path.write_text(json.dumps({
            "reviewer": "synthetic-test-operator",
            "reference": "synthetic",
            "reviewed_at": "2026-09-15T00:00:00Z",
            "decision": "approved",
            "notes": "synthetic test only",
        }), encoding="utf-8")
        return path

    def test_bundle_refresh_writes_private_handoff_and_provenance_per_file(self):
        with tempfile.TemporaryDirectory() as directory:
            result = refresh(
                run_dir=Path(directory) / "run",
                directory_path=ROOT / "fixtures/valid.csv",
                demographics_path=ROOT / "fixtures/demographics.csv",
                retrieved_at_utc="2026-09-18T00:00:00Z",
                effective_date="2026-09-14",
                mode="handoff",
            )
            manifest = result["manifest"]
            self.assertTrue(result["candidate_created"])
            self.assertEqual(manifest["release_state"], "not-created")
            self.assertEqual(manifest["publication_state"], "private-candidate")
            self.assertEqual(manifest["source_artifacts"]["demographics"]["byte_size"], len((ROOT / "fixtures/demographics.csv").read_bytes()))
            self.assertEqual(manifest["row_reconciliation"]["matched_demographic_rows"], 2)
            handoff_path = Path(directory) / "run/lifecycle/handoff/manifest.json"
            self.assertTrue(handoff_path.exists())
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            self.assertEqual(handoff["handoff_artifact_role"], "directory")
            self.assertEqual(handoff["source_artifacts"]["demographics"]["sha256"], manifest["source_artifacts"]["demographics"]["sha256"])
            self.assertEqual(handoff["bundle_artifact"]["sha256"], manifest["sha256"])

    def test_schema_drift_blocks_handoff_after_previous_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = refresh(run_dir=root / "first", directory_path=ROOT / "fixtures/valid.csv", mode="dry-run")
            previous = root / "first/lifecycle/manifest.json"
            changed = root / "changed.csv"
            original = (ROOT / "fixtures/valid.csv").read_text(encoding="utf-8").splitlines()
            changed.write_text("\n".join([original[0] + ",new_column"] + [line + ",new" for line in original[1:]]) + "\n", encoding="utf-8")
            # A changed but parseable header is detected against the prior
            # manifest and blocks handoff.
            with self.assertRaises(ValueError):
                refresh(run_dir=root / "second", directory_path=changed, previous_manifest=previous, mode="handoff")
            self.assertFalse((root / "second/lifecycle/handoff/manifest.json").exists())

    def test_stale_or_unknown_edition_blocks_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "source_effective_date_not_current"):
                refresh(run_dir=Path(directory) / "stale", directory_path=ROOT / "fixtures/valid.csv",
                        effective_date="2020-01-01", mode="handoff")
            with self.assertRaisesRegex(ValueError, "source_effective_date_not_current"):
                refresh(run_dir=Path(directory) / "unknown", directory_path=ROOT / "fixtures/valid.csv",
                        mode="handoff")

    def test_octet_stream_html_is_rejected_without_candidate_or_sensitive_failure_text(self):
        class Response:
            status = 200

            def __init__(self, content_type):
                self.headers = {"Content-Type": content_type, "Content-Length": "33"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _size):
                if not hasattr(self, "done"):
                    self.done = True
                    return b"<html><title>Login</title></html>"
                return b""

            def geturl(self):
                return "https://example.test/fsis.csv"

        class Opener:
            def __init__(self, content_type):
                self.calls = 0
                self.content_type = content_type

            def open(self, _request, timeout):
                self.calls += 1
                return Response(self.content_type)

        for index, content_type in enumerate(("text/csv", "application/octet-stream")):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                opener = Opener(content_type)
                with patch("pipeline.common.acquisition.urllib.request.build_opener", return_value=opener):
                    with self.assertRaisesRegex(AcquisitionError, "HTML/login/challenge"):
                        fetch_source(
                            source_id="us.fsis.directory", url="https://example.test/fsis.csv",
                            output_root=root / "raw", artifact_name="directory.csv",
                            terms_review_path=self._terms(root), run_id=f"html-{index}", max_attempts=3,
                            artifact_validator=lambda path, headers: _validate_download(path, headers, role="directory"),
                        )
                failure_path = root / f"raw/us.fsis.directory/html-{index}/acquisition-failure.json"
                failure = json.loads(failure_path.read_text(encoding="utf-8"))
                encoded = json.dumps(failure)
                self.assertEqual(opener.calls, 1)
                self.assertEqual(failure["failure_class"], "content-signature")
                self.assertFalse(failure["artifact_created"])
                self.assertNotIn("<html", encoded.lower())
                self.assertNotIn("set-cookie", encoded.lower())
                self.assertFalse((root / f"raw/us.fsis.directory/html-{index}/directory.csv").exists())

    def test_fetch_path_wires_source_validator_before_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            html = root / "html-response"
            html.write_bytes(b"<html><title>challenge</title></html>")

            def fake_fetch_source(**kwargs):
                kwargs["artifact_validator"](html, {"Content-Type": "application/octet-stream"})

            refresh_module = importlib.import_module(refresh.__module__)
            with patch.object(refresh_module, "fetch_source", side_effect=fake_fetch_source):
                with self.assertRaisesRegex(AcquisitionError, "HTML/login/challenge"):
                    refresh(
                        run_dir=root / "run", fetch=True, terms_review_path=self._terms(root),
                        effective_date="2026-09-14", mode="handoff",
                    )
            self.assertFalse((root / "run/lifecycle/handoff/manifest.json").exists())

    def test_identity_only_directory_header_is_schema_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "identity-only.csv"
            path.write_bytes(b"establishment_id\nlogin_required\n")
            with self.assertRaisesRegex(AcquisitionError, "expected CSV schema"):
                _validate_download(path, {"Content-Type": "text/csv"}, role="directory")

    def test_complete_header_only_exports_pass_download_validation(self):
        for fixture, role in (("valid.csv", "directory"), ("demographics.csv", "demographics")):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / fixture
                path.write_text(Path(ROOT / "fixtures" / fixture).read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
                _validate_download(path, {"Content-Type": "text/csv"}, role=role)

    def test_403_does_not_retry_and_preserves_previous_manifest(self):
        class Opener:
            def __init__(self):
                self.calls = 0

            def open(self, request, timeout):
                self.calls += 1
                raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = root / "previous" / "lifecycle" / "manifest.json"
            previous.parent.mkdir(parents=True)
            prior_bytes = b'{"validated":"previous"}\n'
            previous.write_bytes(prior_bytes)
            opener = Opener()
            with patch("pipeline.common.acquisition.urllib.request.build_opener", return_value=opener):
                with self.assertRaisesRegex(AcquisitionError, "HTTP 403"):
                    refresh(
                        run_dir=root / "new", fetch=True, terms_review_path=self._terms(root),
                        previous_manifest=previous, mode="handoff", effective_date="2026-09-14",
                        max_attempts=3, retry_delay_seconds=0,
                    )
            self.assertEqual(opener.calls, 1)
            self.assertEqual(previous.read_bytes(), prior_bytes)
            self.assertFalse((root / "new/lifecycle/handoff/manifest.json").exists())

    def test_429_exhausts_bounded_retries_without_artifact(self):
        class Opener:
            def __init__(self):
                self.calls = 0

            def open(self, request, timeout):
                self.calls += 1
                raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, None)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            opener = Opener()
            with patch("pipeline.common.acquisition.urllib.request.build_opener", return_value=opener):
                with self.assertRaisesRegex(AcquisitionError, "HTTP 429"):
                    fetch_source(
                        source_id="us.fsis.directory", url="https://example.test/fsis.csv",
                        output_root=root / "raw", artifact_name="directory.csv",
                        terms_review_path=self._terms(root), run_id="rate-limit", max_attempts=3,
                        retry_delay_seconds=0,
                    )
            failure = json.loads((root / "raw/us.fsis.directory/rate-limit/acquisition-failure.json").read_text(encoding="utf-8"))
            self.assertEqual(opener.calls, 3)
            self.assertEqual(failure["failure_class"], "http-429")
            self.assertEqual(len(failure["attempts"]), 3)
            self.assertFalse(failure["artifact_created"])
            self.assertFalse((root / "raw/us.fsis.directory/rate-limit/directory.csv").exists())


if __name__ == "__main__":
    unittest.main()
