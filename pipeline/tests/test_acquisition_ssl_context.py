from __future__ import annotations

import json
import ssl
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from pipeline.common.acquisition import AcquisitionError, fetch_source


class _Response(BytesIO):
    status = 200
    headers = {"Content-Type": "application/octet-stream", "Content-Length": "8"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def geturl(self):
        return "https://data.example.invalid/source"


class _Opener:
    def open(self, _request, timeout):
        self.timeout = timeout
        return _Response(b"snapshot")


class AcquisitionSSLContextTests(unittest.TestCase):
    def test_custom_context_is_passed_to_https_handler_and_remains_verified(self):
        from pipeline.sources.scotland_aquaculture.acquire import _tls_context

        context = _tls_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        staging = Path(__file__).resolve().parents[2] / "data" / "staging" / "source-expansion-20261020" / "ssl-context-tests"
        staging.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=staging) as directory:
            review = Path(directory) / "terms.json"
            review.write_text(json.dumps({
                "reviewer": "synthetic test", "reference": "synthetic", "reviewed_at": "2026-10-20T00:00:00Z",
                "decision": "approved", "notes": "synthetic only",
            }), encoding="utf-8")
            opener = _Opener()
            with patch("pipeline.common.acquisition.urllib.request.HTTPSHandler") as https_handler, \
                    patch("pipeline.common.acquisition.urllib.request.build_opener", return_value=opener) as build_opener:
                result = fetch_source(
                    source_id="test.ssl-context", url="https://data.example.invalid/source",
                    output_root=Path(directory), artifact_name="source.bin", terms_review_path=review,
                    run_id="tls-test", allowed_content_types=("application/octet-stream",), ssl_context=context,
                )
            https_handler.assert_called_once_with(context=context)
            handlers = build_opener.call_args.args
            self.assertEqual(len(handlers), 2)
            self.assertIs(handlers[1], https_handler.return_value)
            self.assertEqual(Path(result["artifact_path"]).read_bytes(), b"snapshot")

    def test_unverified_context_is_rejected_before_network(self):
        with patch("pipeline.common.acquisition.urllib.request.build_opener") as build_opener:
            with self.assertRaisesRegex(AcquisitionError, "certificate validation and hostname"):
                fetch_source(
                    source_id="test.ssl-context", url="https://data.example.invalid/source",
                    output_root="unused", artifact_name="source.bin", terms_review_path="unused",
                    ssl_context=ssl._create_unverified_context(),
                )
        build_opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
