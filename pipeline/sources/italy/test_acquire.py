import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .acquire import AcquisitionError, discover_csv, fetch
from .it_853_adapter import REQUIRED
from .refresh import refresh


class FakeResponse:
    def __init__(self, body: bytes, url: str, content_type: str):
        self.body = body
        self.status = 200
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        self._url = url
        self._offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, limit=-1):
        if limit < 0:
            chunk = self.body[self._offset:]
        else:
            chunk = self.body[self._offset:self._offset + limit]
        self._offset += len(chunk)
        return chunk

    def geturl(self):
        return self._url


HEADER = ";".join(REQUIRED)
CSV = (HEADER + "\n;IT-1;Test;Address;Town;XX;010;Piemonte;Class;A1;Activity;P;S;IT;12;45;1;tax;vat;001001;;;AUTORIZZATA;2026-09-15;\n").encode()
CATALOG = b'<html><a href="/sites/default/files/opendata/STAB_POA_8_20260915.csv">Scarica</a><p>Data ultimo aggiornamento</p><span>15/09/2026</span></html>'


class ItalyAcquisitionTests(unittest.TestCase):
    def review(self, root: Path) -> Path:
        path = root / "terms.json"
        path.write_text(json.dumps({"reviewer": "test", "reference": "iodl", "reviewed_at": "2026-09-15T00:00:00Z", "decision": "approved", "notes": "synthetic fixture"}), encoding="utf-8")
        return path

    def test_discovery_uses_catalog_link_and_rejects_other_hosts(self):
        url, date = discover_csv(CATALOG, "https://www.dati.salute.gov.it/catalog")
        self.assertEqual(url, "https://www.dati.salute.gov.it/sites/default/files/opendata/STAB_POA_8_20260915.csv")
        self.assertEqual(date, "2026-09-15")
        with self.assertRaisesRegex(AcquisitionError, "no supported"):
            discover_csv(b'<a href="https://evil.example/STAB_POA_8_20260915.csv">x</a>', "https://www.dati.salute.gov.it/catalog")

    def test_fetch_archives_catalog_discovered_csv_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []

            def opener(request, timeout):
                calls.append((request.full_url, timeout))
                if len(calls) == 1:
                    return FakeResponse(CATALOG, "https://www.dati.salute.gov.it/catalog", "text/html; charset=utf-8")
                return FakeResponse(CSV, request.full_url, "text/csv; charset=utf-8")

            metadata = fetch(output_root=root / "raw", run_id="run-1", terms_review_path=self.review(root), opener=opener)
            artifact = root / "raw" / "it.853-2004" / "run-1" / "source.csv"
            self.assertEqual(calls[1][0], "https://www.dati.salute.gov.it/sites/default/files/opendata/STAB_POA_8_20260915.csv")
            self.assertEqual(metadata["source_id"], "it.853-2004")
            self.assertEqual(metadata["filename_publication_date"], "2026-09-15")
            self.assertEqual(metadata["sha256"], hashlib.sha256(CSV).hexdigest())
            self.assertEqual(metadata["byte_size"], len(CSV))
            self.assertEqual(json.loads((artifact.parent / "acquisition-metadata.json").read_text())["terms_review"]["decision"], "approved")
            self.assertEqual(artifact.read_bytes(), CSV)

    def test_fetch_requires_approved_terms_and_bounds_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review = root / "terms.json"
            review.write_text(json.dumps({"reviewer": "test", "reference": "x", "reviewed_at": "2026-09-15T00:00:00Z", "decision": "pending", "notes": "no"}), encoding="utf-8")
            with self.assertRaisesRegex(AcquisitionError, "approved"):
                fetch(output_root=root / "raw", run_id="run", terms_review_path=review, opener=lambda *_: None)
            with patch("pipeline.sources.italy.acquire._archive_stream", side_effect=AcquisitionError("download exceeds")):
                calls = iter([FakeResponse(CATALOG, "https://www.dati.salute.gov.it/catalog", "text/html"), FakeResponse(CSV, "https://www.dati.salute.gov.it/file.csv", "text/csv")])
                with self.assertRaisesRegex(AcquisitionError, "exceeds"):
                    fetch(output_root=root / "raw", run_id="run", terms_review_path=self.review(root), opener=lambda *args, **kwargs: next(calls), max_bytes=1)

    def test_local_archived_artifact_runs_shared_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "fixture.csv"
            raw.write_bytes(CSV)
            # The local archive path is test-only; it records unknown source
            # URLs rather than implying that the fixture was downloaded.
            from .acquire import archive_local_file
            metadata = archive_local_file(raw, root / "raw", run_id="local", retrieved_at="2026-09-15T00:00:00Z")
            status = refresh(raw_path=root / "raw" / "it.853-2004" / "local" / "source.csv", run_dir=root / "staging")
            self.assertEqual(status["status"], "candidate-ready")
            self.assertEqual(status["manifest"]["input_rows"], 1)
            self.assertEqual(status["manifest"]["normalized_rows"], 1)
            self.assertEqual(status["acquisition"]["sha256"], metadata["sha256"])


if __name__ == "__main__":
    unittest.main()
