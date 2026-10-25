import tempfile
import unittest
from datetime import datetime
import urllib.request
from pathlib import Path
from unittest.mock import patch

from .acquire import BvlAcquisitionError, _SafeRedirect, fetch
from .adapter import CONFIG


class _Response:
    def __init__(self, body: bytes, url: str, content_type: str = "text/html"):
        self.body, self.url, self.status = body, url, 200
        self.headers = {"Content-Type": content_type}

    def geturl(self):
        return self.url

    def read(self, size=-1):
        if size < 0:
            size = len(self.body)
        body, self.body = self.body[:size], self.body[size:]
        return body

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class _Opener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected BVL request")
        return self.responses.pop(0)


class GermanyAcquisitionTests(unittest.TestCase):
    def flow(self, *, export=b"# Bundesland;Neue Zulassungsnummer\n", content_type="application/csv",
             export_href="/bltu/app/process/bvl-btl_p_veroeffentlichung?execution=e1s3&x=clicked",
             form_action="/bltu/app/process/bvl-btl_p_veroeffentlichung?execution=e1s1"):
        host = "https://bltu.bvl.bund.de"
        landing = f'<form id="osForm" action="{form_action}"><input type="hidden" name="javax.faces.ViewState" value="e1s1"/></form>'.encode()
        start = b'<title>BVL Betriebslisten Version 1.0.35 [10/2023]</title><form id="osForm"><input type="hidden" name="javax.faces.ViewState" value="e1s2"/></form>'
        listing = f'<h1>Generalliste</h1><a title="CSV" href="{export_href}">CSV</a>'.encode()
        opener = _Opener([_Response(landing, CONFIG["acquisition_url"]),
                          _Response(start, host + "/start"),
                          _Response(listing, host + "/list"),
                          _Response(export, host + "/export", content_type)])
        return host, opener

    def run_flow(self, directory, **kwargs):
        host, opener = self.flow(**kwargs)
        with patch("pipeline.sources.germany.acquire.urllib.request.build_opener", return_value=opener):
            metadata = fetch(output_root=directory, run_id="test-run")
        return metadata, opener, host

    def test_public_session_flow_preserves_csv_and_unknown_effective_date(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata, opener, _ = self.run_flow(directory)
            self.assertEqual(metadata["effective_date"], "unknown")
            self.assertIn("1.0.35 [10/2023]", metadata["source_display_version"])
            self.assertLessEqual(datetime.fromisoformat(metadata["requested_at_utc"].replace("Z", "+00:00")),
                                 datetime.fromisoformat(metadata["retrieved_at_utc"].replace("Z", "+00:00")))
            self.assertEqual(len(opener.requests), 4)
            self.assertEqual((Path(metadata["artifact_path"]).read_bytes()).splitlines()[0], b"# Bundesland;Neue Zulassungsnummer")

    def test_refuses_non_https_or_foreign_form_action_and_export(self):
        with tempfile.TemporaryDirectory() as directory:
            for action in ("http://bltu.bvl.bund.de/continue", "https://example.invalid/continue", "https://bltu.bvl.bund.de:8443/continue"):
                with self.subTest(action=action):
                    host, opener = self.flow(form_action=action)
                    with patch("pipeline.sources.germany.acquire.urllib.request.build_opener", return_value=opener):
                        with self.assertRaises(BvlAcquisitionError):
                            fetch(output_root=directory, run_id="test-run")
            for href in ("http://bltu.bvl.bund.de/export", "https://example.invalid/export"):
                with self.subTest(href=href):
                    _, opener = self.flow(export_href=href)
                    with patch("pipeline.sources.germany.acquire.urllib.request.build_opener", return_value=opener):
                        with self.assertRaises(BvlAcquisitionError):
                            fetch(output_root=directory, run_id="bad-host")
                    self.assertEqual(len(opener.requests), 3)
            redirect = _SafeRedirect()
            request = urllib.request.Request("https://bltu.bvl.bund.de/start")
            with self.assertRaises(BvlAcquisitionError):
                redirect.redirect_request(request, None, 302, "Found", {}, "https://example.invalid/next")

    def test_rejects_export_content_type_schema_and_size_overflow(self):
        with tempfile.TemporaryDirectory() as directory:
            host, opener = self.flow(content_type="text/html")
            with patch("pipeline.sources.germany.acquire.urllib.request.build_opener", return_value=opener):
                with self.assertRaises(BvlAcquisitionError):
                    fetch(output_root=directory, run_id="bad-type")
            _, opener = self.flow(export=b"not the expected header")
            with patch("pipeline.sources.germany.acquire.urllib.request.build_opener", return_value=opener):
                with self.assertRaises(BvlAcquisitionError):
                    fetch(output_root=directory, run_id="bad-schema")
            big = b"# Bundesland;Neue Zulassungsnummer\n" + b"x" * 2048
            host, opener = self.flow(export=big)
            with patch("pipeline.sources.germany.acquire.urllib.request.build_opener", return_value=opener):
                with self.assertRaises(BvlAcquisitionError):
                    fetch(output_root=directory, run_id="too-big", max_bytes=1024)


if __name__ == "__main__":
    unittest.main()
