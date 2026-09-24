import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.common.acquisition import AcquisitionError

from .firefox_acquisition import _edition_date, _remove_downloads, acquire_firefox


ROOT = Path(__file__).parent


class FakeTimeout(Exception):
    pass


class FakeBy:
    CSS_SELECTOR = "css selector"


class FakeDriver:
    capabilities = {"browserVersion": "synthetic-firefox"}

    def __init__(self, download_dir: Path, payload: bytes, *, timeout_after_download: bool = False):
        self.download_dir = download_dir
        self.payload = payload
        self.timeout_after_download = timeout_after_download
        self.urls: list[str] = []
        self.quit_called = False

    def set_page_load_timeout(self, _seconds):
        return None

    def get(self, url):
        self.urls.append(url)
        if url.endswith(".csv"):
            (self.download_dir / "source.csv").write_bytes(self.payload)
            if self.timeout_after_download:
                raise FakeTimeout("download completed while navigation remained pending")

    def find_elements(self, _selector, _value):
        return []

    def quit(self):
        self.quit_called = True


def _terms(root: Path) -> Path:
    path = root / "terms.json"
    path.write_text(json.dumps({
        "reviewer": "synthetic-test-operator",
        "reference": "synthetic",
        "reviewed_at": "2026-09-15T00:00:00Z",
        "decision": "approved",
        "notes": "synthetic test only",
    }), encoding="utf-8")
    return path


def _authorization() -> dict:
    return {
        "status": "authorized",
        "basis": "synthetic test owner authorization",
        "scope": "official FSIS test route; private staging only",
        "allowed_routes": [{"source_id": "us.fsis.directory", "role": "directory", "url": "https://example.test/directory.csv"}],
        "restrictions": ["no public release", "no credentials", "no bypass"],
        "recorded_at_utc": "2026-09-20T00:00:00Z",
        "terms_status": "unknown",
    }


class FirefoxAcquisitionTests(unittest.TestCase):
    def test_edition_date_is_read_from_official_link_context(self):
        self.assertEqual(_edition_date("MPI Directory: Numerically by Establishment Number (CSV) | PDF (Sep 21, 2026)"), "2026-09-21")
        self.assertIsNone(_edition_date("MPI Directory CSV"))

    def test_cleanup_failure_does_not_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            download_dir = Path(directory)
            (download_dir / "partial.part").write_bytes(b"partial")
            with patch.object(Path, "unlink", side_effect=OSError("synthetic cleanup failure")):
                _remove_downloads(download_dir)

    def test_complete_file_survives_navigation_timeout_and_records_browser_provenance(self):
        payload = (ROOT / "fixtures/valid.csv").read_bytes()
        drivers: list[FakeDriver] = []

        def opener(download_dir):
            driver = FakeDriver(download_dir, payload, timeout_after_download=True)
            drivers.append(driver)
            return driver, {"browser": "Firefox", "browser_version": "synthetic-firefox", "selenium_version": "synthetic-selenium", "profile": "fresh-temporary", "timeout_exception": FakeTimeout, "by": FakeBy}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = acquire_firefox(
                source_id="us.fsis.directory", page_url="https://example.test/page",
                url="https://example.test/directory.csv", output_root=root / "raw",
                artifact_name="directory.csv", terms_review_path=None, run_id="browser-timeout",
                acquisition_authorization=_authorization(),
                navigation_timeout_seconds=0.1,
                artifact_validator=lambda path, _headers: self.assertEqual(path.read_bytes(), payload), driver_opener=opener,
            )
            self.assertEqual(metadata["acquisition_method"], "firefox_browser_download")
            self.assertTrue(metadata["navigation_timeout_after_download_start"])
            self.assertEqual(metadata["browser"]["browser_version"], "synthetic-firefox")
            self.assertEqual(metadata["terms_review"]["status"], "unknown")
            self.assertEqual(metadata["acquisition_authorization"]["status"], "authorized")
            self.assertTrue(drivers[0].quit_called)
            self.assertTrue((root / "raw/us.fsis.directory/browser-timeout/directory.csv").exists())

    def test_firefox_requires_owner_authorization_separately_from_terms(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(AcquisitionError, "authorization"):
                acquire_firefox(
                    source_id="us.fsis.directory", page_url="https://example.test/page",
                    url="https://example.test/directory.csv", output_root=root / "raw",
                    artifact_name="directory.csv", terms_review_path=None, acquisition_authorization=None,
                    run_id="missing-authorization", driver_opener=lambda _path: (_ for _ in ()).throw(AssertionError("driver must not open")),
                )

    def test_firefox_rejects_unbound_or_malformed_authorization(self):
        payload = (ROOT / "fixtures/valid.csv").read_bytes()

        def opener(download_dir):
            return FakeDriver(download_dir, payload), {"browser": "Firefox", "browser_version": "synthetic", "selenium_version": "synthetic", "profile": "fresh-temporary", "timeout_exception": FakeTimeout, "by": FakeBy}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unbound = _authorization()
            unbound["allowed_routes"] = [{"source_id": "us.fsis.demographics", "role": "demographics", "url": "https://example.test/demographics.csv"}]
            with self.assertRaisesRegex(AcquisitionError, "does not cover"):
                acquire_firefox(
                    source_id="us.fsis.directory", page_url="https://example.test/page", url="https://example.test/directory.csv",
                    output_root=root / "raw", artifact_name="directory.csv", terms_review_path=None,
                    acquisition_authorization=unbound, run_id="unbound", navigation_timeout_seconds=0.1, driver_opener=opener,
                )
            malformed = _authorization()
            malformed["restrictions"] = "no-public-release"
            with self.assertRaisesRegex(AcquisitionError, "restrictions"):
                acquire_firefox(
                    source_id="us.fsis.directory", page_url="https://example.test/page", url="https://example.test/directory.csv",
                    output_root=root / "raw", artifact_name="directory.csv", terms_review_path=None,
                    acquisition_authorization=malformed, run_id="malformed", navigation_timeout_seconds=0.1, driver_opener=opener,
                )

    def test_current_official_page_link_is_required_when_requested(self):
        payload = (ROOT / "fixtures/valid.csv").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AcquisitionError, "not present on the official directory page"):
                acquire_firefox(
                    source_id="us.fsis.directory", page_url="https://example.test/page",
                    url="https://example.test/directory.csv", output_root=Path(directory) / "raw",
                    artifact_name="directory.csv", terms_review_path=_terms(Path(directory)),
                    acquisition_authorization=_authorization(), run_id="missing-official-link",
                    navigation_timeout_seconds=0.1, require_public_link=True,
                    artifact_validator=lambda path, _headers: self.assertEqual(path.read_bytes(), payload),
                    driver_opener=lambda download_dir: (
                        FakeDriver(download_dir, payload),
                        {"browser": "Firefox", "browser_version": "synthetic", "selenium_version": "synthetic",
                         "profile": "fresh-temporary", "timeout_exception": FakeTimeout, "by": FakeBy},
                    ),
                )
    def test_invalid_completed_file_fails_closed_without_retaining_body(self):
        drivers: list[FakeDriver] = []

        def opener(download_dir):
            driver = FakeDriver(download_dir, b"<html>challenge</html>", timeout_after_download=True)
            drivers.append(driver)
            return driver, {"browser": "Firefox", "browser_version": "synthetic-firefox", "selenium_version": "synthetic-selenium", "profile": "fresh-temporary", "timeout_exception": FakeTimeout, "by": FakeBy}

        def reject(_path, _headers):
            raise AcquisitionError("schema rejected", failure_class="content-signature", action="use assisted capture")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(AcquisitionError, "schema rejected"):
                acquire_firefox(
                    source_id="us.fsis.directory", page_url="https://example.test/page",
                    url="https://example.test/directory.csv", output_root=root / "raw",
                    artifact_name="directory.csv", terms_review_path=_terms(root), run_id="browser-invalid",
                    acquisition_authorization=_authorization(),
                    navigation_timeout_seconds=0.1,
                    artifact_validator=reject, driver_opener=opener,
                )
            failure_path = root / "raw/us.fsis.directory/browser-invalid/acquisition-failure.json"
            failure = json.loads(failure_path.read_text(encoding="utf-8"))
            self.assertEqual(failure["failure_class"], "content-signature")
            self.assertFalse(failure["artifact_created"])
            self.assertNotIn("challenge", failure_path.read_text(encoding="utf-8"))
            self.assertFalse((root / "raw/us.fsis.directory/browser-invalid/directory.csv").exists())
            self.assertTrue(drivers[0].quit_called)


if __name__ == "__main__":
    unittest.main()
