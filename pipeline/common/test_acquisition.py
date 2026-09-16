import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import urllib.error

from .acquisition import AcquisitionError, archive_stream, fetch_source, require_terms_review


class AcquisitionContractTests(unittest.TestCase):
    def test_terms_review_requires_explicit_approved_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "terms.json"
            path.write_text(json.dumps({"reviewer": "operator", "reference": "OGL", "reviewed_at": "2026-09-15T00:00:00Z", "decision": "pending", "notes": "restricted"}), encoding="utf-8")
            with self.assertRaises(AcquisitionError):
                require_terms_review(path)

    def test_archive_stream_enforces_bound_and_removes_partial(self):
        class Stream:
            def read(self, _size):
                return b"123456"

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "artifact.csv"
            with self.assertRaises(AcquisitionError):
                archive_stream(Stream(), target, max_bytes=5)
            self.assertFalse(target.exists())
            self.assertFalse(list(Path(directory).glob("*.part")))

    def test_fetch_retries_network_failure_and_records_attempts(self):
        class Response:
            status = 200
            headers = {"Content-Type": "text/csv", "Content-Length": "7"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, size):
                if not hasattr(self, "done"):
                    self.done = True
                    return b"a,b\n1,2\n"
                return b""

            def geturl(self):
                return "https://example.test/source.csv"

        class Opener:
            def __init__(self):
                self.calls = 0

            def open(self, _request, timeout):
                self.calls += 1
                if self.calls == 1:
                    raise urllib.error.URLError("temporary")
                return Response()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            terms = root / "terms.json"
            terms.write_text(json.dumps({"reviewer": "operator", "reference": "test", "reviewed_at": "2026-09-15T00:00:00Z", "decision": "approved", "notes": "synthetic"}), encoding="utf-8")
            opener = Opener()
            with patch("pipeline.common.acquisition.urllib.request.build_opener", return_value=opener):
                metadata = fetch_source(
                    source_id="test.source", url="https://example.test/source.csv", output_root=root / "raw",
                    artifact_name="source.csv", terms_review_path=terms, run_id="run-1", max_attempts=2,
                )
            self.assertEqual(opener.calls, 2)
            self.assertEqual(len(metadata["attempts"]), 2)
            self.assertEqual(metadata["attempts"][0]["failure_class"], "network")
            self.assertTrue(Path(metadata["artifact_path"]).exists())

    def test_fetch_non_retryable_content_type_fails_closed_with_private_report(self):
        class Response:
            status = 200
            headers = {"Content-Type": "text/html"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class Opener:
            def open(self, _request, timeout):
                return Response()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            terms = root / "terms.json"
            terms.write_text(json.dumps({"reviewer": "operator", "reference": "test", "reviewed_at": "2026-09-15T00:00:00Z", "decision": "approved", "notes": "synthetic"}), encoding="utf-8")
            with patch("pipeline.common.acquisition.urllib.request.build_opener", return_value=Opener()):
                with self.assertRaisesRegex(AcquisitionError, "unexpected content type"):
                    fetch_source(
                        source_id="test.source", url="https://example.test/source", output_root=root / "raw",
                        artifact_name="source", terms_review_path=terms, run_id="run-2", max_attempts=3,
                    )
            failure = json.loads((root / "raw/test.source/run-2/acquisition-failure.json").read_text())
            self.assertEqual(failure["failure_class"], "content-type")
            self.assertFalse(failure["artifact_created"])


if __name__ == "__main__":
    unittest.main()
