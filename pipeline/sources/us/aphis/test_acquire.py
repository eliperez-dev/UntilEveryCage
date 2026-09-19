import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.common.acquisition import AcquisitionError

from .acquire import fetch_profile, preserve_local_document, validate_download


class AphisAcquisitionTests(unittest.TestCase):
    def test_csv_validator_rejects_empty_challenge_and_inconsistent_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = {
                "empty.csv": b"Account Name,Certificate Number\n",
                "challenge.csv": b"<html><title>Just a moment...</title></html>\n",
                "truncated.csv": b"Account Name,Certificate Number\nSynthetic,1,unexpected\n",
            }
            for name, payload in cases.items():
                path = root / name
                path.write_bytes(payload)
                with self.subTest(name=name):
                    with self.assertRaises(AcquisitionError):
                        validate_download("registrations", path)

    def test_document_validator_requires_pdf_or_office_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / "invalid.pdf"
            invalid.write_bytes(b"not a document")
            with self.assertRaisesRegex(AcquisitionError, "signature"):
                validate_download("documents", invalid)

            valid = root / "report.pdf"
            valid.write_bytes(b"%PDF-1.7\nsynthetic\n%%EOF\n")
            validate_download("documents", valid)

    def test_operator_saved_document_gets_private_manifest_without_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / "amendment.pdf"
            document.write_bytes(b"%PDF-1.7\nsynthetic amendment\n%%EOF\n")
            manifest = preserve_local_document(
                raw_path=document,
                run_dir=root / "run",
                source_url="https://example.test/amendment.pdf",
                retrieved_at_utc="2026-09-18T00:00:00Z",
                effective_date="2025",
                query_context={"document_id": "synthetic"},
            )
            self.assertEqual(manifest["profile"], "documents")
            self.assertEqual(manifest["publication_gate"], "blocked")
            self.assertEqual(manifest["query_context"]["document_id"], "synthetic")
            self.assertEqual(manifest["artifact_path"], str(document))

    def test_fetch_preserves_query_context_and_writes_manifest(self):
        payload = b"Account Name,Customer Number,Certificate Number,License Type,Certificate Status,Status Date\nSynthetic,1,00-B-0001,Class B,Active,2026-01-01\n"

        class Response:
            status = 200
            headers = {"Content-Type": "text/csv", "Content-Length": str(len(payload)), "Last-Modified": "Tue, 15 Sep 2026 00:00:00 GMT"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _size):
                if getattr(self, "done", False):
                    return b""
                self.done = True
                return payload

            def geturl(self):
                return "https://download.example.test/aphis.csv"

        class Opener:
            def open(self, _request, timeout):
                return Response()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            terms = root / "terms.json"
            terms.write_text(json.dumps({"reviewer": "operator", "reference": "synthetic", "reviewed_at": "2026-09-15T00:00:00Z", "decision": "approved", "notes": "test"}), encoding="utf-8")
            with patch("pipeline.common.acquisition.urllib.request.build_opener", return_value=Opener()):
                metadata = fetch_profile(
                    profile="registrations",
                    output_root=root / "raw",
                    terms_review_path=terms,
                    run_id="run-1",
                    query_context={"selected_year": "2026", "amended": False},
                )
            run = Path(metadata["artifact_path"]).parent
            manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["query_context"]["selected_year"], "2026")
            self.assertEqual(manifest["byte_size"], len(payload))
            self.assertEqual(manifest["effective_date"], "Tue, 15 Sep 2026 00:00:00 GMT")

    def test_challenge_failure_keeps_prior_artifact_and_records_context(self):
        previous = b"Account Name,Customer Number,Certificate Number,License Type,Certificate Status,Status Date\nSynthetic,1,00-B-0001,Class B,Active,2026-01-01\n"
        challenge = b"<html><title>Access denied</title></html>\n"

        class Response:
            status = 200
            headers = {"Content-Type": "text/csv", "Content-Length": str(len(challenge))}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _size):
                if getattr(self, "done", False):
                    return b""
                self.done = True
                return challenge

            def geturl(self):
                return "https://download.example.test/challenge.csv"

        class Opener:
            def open(self, _request, timeout):
                return Response()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prior = root / "prior.csv"
            prior.write_bytes(previous)
            terms = root / "terms.json"
            terms.write_text(json.dumps({"reviewer": "operator", "reference": "synthetic", "reviewed_at": "2026-09-15T00:00:00Z", "decision": "approved", "notes": "test"}), encoding="utf-8")
            with patch("pipeline.common.acquisition.urllib.request.build_opener", return_value=Opener()):
                with self.assertRaisesRegex(AcquisitionError, "challenge"):
                    fetch_profile(
                        profile="annual_reports",
                        output_root=root / "raw",
                        terms_review_path=terms,
                        run_id="run-2",
                        source_url="https://example.test/annual-reports.csv",
                        effective_date="2025",
                        query_context={"selected_year": "2025"},
                    )
            self.assertEqual(prior.read_bytes(), previous)
            failure = json.loads((root / "raw/us.aphis/run-2/acquisition-failure.json").read_text(encoding="utf-8"))
            self.assertEqual(failure["failure_class"], "challenge-response")
            self.assertEqual(failure["requested_url"], "https://example.test/annual-reports.csv")
            self.assertEqual(failure["effective_date"], "2025")
            self.assertTrue(failure["requested_at_utc"])
            self.assertEqual(failure["query_context"]["selected_year"], "2025")


if __name__ == "__main__":
    unittest.main()
