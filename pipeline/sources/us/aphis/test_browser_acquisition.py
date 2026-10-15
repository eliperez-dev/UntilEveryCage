import json
import tempfile
import unittest
from pathlib import Path

from pipeline.common.acquisition import AcquisitionError

from .browser_acquisition import acquire_public_search_export


class _Element:
    def __init__(self, *, text="", attrs=None, children=None):
        self.text = text
        self.attrs = attrs or {}
        self.children = children or []
        self.clicked = False

    def get_attribute(self, name):
        return self.attrs.get(name)

    def is_displayed(self):
        return True

    def is_enabled(self):
        return True

    def find_elements(self, _by, _selector):
        return self.children

    def click(self):
        self.clicked = True


class _Driver:
    def __init__(self, download_dir, *, year_control=True, export_control=True):
        self.download_dir = download_dir
        self.year_control = year_control
        self.export_control = export_control
        self.search = _Element(text="Search")
        self.export = _Element(text="Export to CSV", attrs={"aria-label": "Export to CSV"})
        self.profile_link = _Element(text="View Annual Reports")

    def set_page_load_timeout(self, _value):
        pass

    def get(self, _url):
        pass

    def find_elements(self, _by, selector):
        if selector == "select":
            return [_Element(children=[_Element(text="2025", attrs={"value": "2025"})])] if self.year_control else []
        if selector == "a":
            return [self.profile_link]
        return [self.search, self.export] if self.export_control else [self.search]

    def execute_script(self, script, *args):
        if "dispatchEvent" in script:
            return None
        if "scrollIntoView" in script:
            (self.download_dir / "annual_reports.csv").write_bytes(b"Customer Number,Certificate Number,Year\n1,R-1,2025\n")
        return None

    def quit(self):
        pass


class _By:
    CSS_SELECTOR = "css"


class BrowserAcquisitionTests(unittest.TestCase):
    def test_annual_export_preserves_private_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def opener(download_dir):
                return _Driver(download_dir), {"browser": "Firefox", "by": _By, "timeout_exception": RuntimeError}
            metadata = acquire_public_search_export(
                profile="annual_reports", profile_url="https://example.test/annual", output_root=root,
                run_id="run-1", query_context={"selected_year": "2025", "amended_reports_included": True},
                artifact_validator=lambda path, _headers: self.assertTrue(path.is_file()), driver_opener=opener,
            )
            self.assertEqual(metadata["query_context"]["selected_year"], "2025")
            self.assertEqual(metadata["retention"]["public_exposure"], False)
            self.assertTrue(Path(metadata["artifact_path"]).is_file())
            stored = json.loads((root / "us.aphis/run-1/acquisition-metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["profile"], "annual_reports")

    def test_annual_export_requires_explicit_year(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AcquisitionError, "selected_year"):
                acquire_public_search_export(
                    profile="annual_reports", profile_url="https://example.test/annual", output_root=directory,
                    run_id="run-1", query_context={}, artifact_validator=lambda *_: None,
                )

    def test_missing_export_control_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            def opener(download_dir):
                return _Driver(download_dir, export_control=False), {"browser": "Firefox", "by": _By, "timeout_exception": RuntimeError}
            with self.assertRaisesRegex(AcquisitionError, "Export to CSV"):
                acquire_public_search_export(
                    profile="annual_reports", profile_url="https://example.test/annual", output_root=directory,
                    run_id="run-1", query_context={"selected_year": "2025"},
                    artifact_validator=lambda *_: None, driver_opener=opener,
                )


if __name__ == "__main__":
    unittest.main()
