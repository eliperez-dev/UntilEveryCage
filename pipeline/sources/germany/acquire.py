"""Bounded acquisition through the public BVL BLtU session and CSV export."""
from __future__ import annotations

import hashlib
import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from pipeline.contracts.source_lifecycle import atomic_bytes, atomic_json

from .adapter import CONFIG


class BvlAcquisitionError(RuntimeError):
    pass


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.action = ""
        self.hidden: dict[str, str] = {}
        self.csv_href = ""
        self.version_text = ""
        self._capture_version = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "form" and a.get("id") == "osForm":
            self.action = a.get("action") or ""
        if tag == "input" and (a.get("type") or "").lower() == "hidden" and a.get("name"):
            self.hidden[a["name"]] = a.get("value") or ""
        if tag == "a" and (a.get("title") or "").upper() == "CSV":
            self.csv_href = a.get("href") or ""

    def handle_data(self, data: str) -> None:
        if "BVL Betriebslisten Version" in data:
            self.version_text = " ".join(data.split())


def _bounded_open(opener: Any, request: urllib.request.Request, timeout: float, limit: int):
    try:
        response = opener.open(request, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise BvlAcquisitionError(f"BVL request failed: {type(error).__name__}") from error
    status = getattr(response, "status", 200)
    if status != 200:
        response.close()
        raise BvlAcquisitionError(f"BVL returned HTTP {status}")
    return response


def fetch(*, output_root: str | Path, run_id: str, timeout_seconds: float = 30,
          max_bytes: int = 16 * 1024 * 1024) -> dict[str, Any]:
    if not 1 <= timeout_seconds <= 120 or not 1024 <= max_bytes <= 64 * 1024 * 1024:
        raise BvlAcquisitionError("timeout or byte limit outside configured safe bounds")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", run_id):
        raise BvlAcquisitionError("invalid run id")
    url = CONFIG["acquisition_url"]
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    headers = {"User-Agent": "UntilEveryCage/controlled-acquisition", "Accept": "text/html,application/xhtml+xml"}

    def get(target: str):
        if urllib.parse.urlparse(target).hostname not in {"bltu.bvl.bund.de"}:
            raise BvlAcquisitionError("refusing non-BVL navigation")
        return _bounded_open(opener, urllib.request.Request(target, headers=headers), timeout_seconds, max_bytes)

    with get(url) as response:
        landing_url = response.geturl()
        landing = response.read(min(max_bytes + 1, 256 * 1024 + 1))
    if len(landing) > 256 * 1024:
        raise BvlAcquisitionError("unexpectedly large BVL landing page")
    first = _FormParser(); first.feed(landing.decode("utf-8", "replace"))
    if not first.action or not first.hidden:
        raise BvlAcquisitionError("public BVL continuation form not recognized")
    action_url = urllib.parse.urljoin(landing_url, first.action)
    form = dict(first.hidden)
    form["osForm:button"] = "osForm:button"
    req = urllib.request.Request(action_url, data=urllib.parse.urlencode(form).encode(), headers={**headers, "Content-Type": "application/x-www-form-urlencoded"})
    with _bounded_open(opener, req, timeout_seconds, max_bytes) as response:
        page_url = response.geturl(); page = response.read(min(max_bytes + 1, 512 * 1024 + 1))
    if len(page) > 512 * 1024:
        raise BvlAcquisitionError("unexpectedly large BVL start page")
    parser = _FormParser(); parser.feed(page.decode("utf-8", "replace"))
    view = re.search(rb'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', page)
    if not view:
        raise BvlAcquisitionError("BVL start page did not expose a session view state")
    post = {"osForm": "osForm", "javax.faces.ViewState": view.group(1).decode(), "osForm:id_002eqsj": "clicked"}
    req = urllib.request.Request(page_url, data=urllib.parse.urlencode(post).encode(), headers={**headers, "Content-Type": "application/x-www-form-urlencoded"})
    with _bounded_open(opener, req, timeout_seconds, max_bytes) as response:
        list_url = response.geturl(); listing = response.read(min(max_bytes + 1, 4 * 1024 * 1024 + 1))
    if len(listing) > 4 * 1024 * 1024:
        raise BvlAcquisitionError("unexpectedly large BVL list page")
    parser = _FormParser(); parser.feed(listing.decode("utf-8", "replace"))
    if "Generalliste" not in listing.decode("utf-8", "replace") or not parser.csv_href:
        raise BvlAcquisitionError("BVL general-list CSV export control missing")
    export_url = urllib.parse.urljoin(list_url, parser.csv_href)
    if urllib.parse.urlparse(export_url).hostname != "bltu.bvl.bund.de":
        raise BvlAcquisitionError("refusing export outside BVL host")
    with get(export_url) as response:
        content_type = (response.headers.get("Content-Type") or "").split(";")[0].lower()
        if content_type not in {"application/csv", "text/csv", "application/octet-stream"}:
            raise BvlAcquisitionError("BVL export returned unexpected content type")
        raw = response.read(max_bytes + 1)
    if not raw or len(raw) > max_bytes:
        raise BvlAcquisitionError("BVL export empty or exceeded byte limit")
    if b"Neue Zulassungsnummer" not in raw[:8192]:
        raise BvlAcquisitionError("BVL export header fingerprint marker missing")
    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    root = Path(output_root) / run_id
    raw_path = atomic_bytes(root / "bltu-general-list.csv", raw)
    metadata = {"source_id": CONFIG["source_id"], "acquisition_method": "official_bltu_public_session_export", "requested_url": url,
        "final_url": export_url, "retrieved_at_utc": retrieved, "requested_at_utc": retrieved,
        "effective_date": "unknown", "publication_date": None, "source_display_version": parser.version_text or "unknown",
        "content_type": content_type, "byte_size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "artifact_path": str(raw_path.resolve()), "adapter_version": CONFIG["adapter_version"],
        "code_version": CONFIG["adapter_version"], "config_version": CONFIG["schema_version"],
        "coverage": CONFIG["coverage"], "rights_caveat": CONFIG["terms"],
        "privacy_caveat": "private staging; address and coordinate review pending", "terms_review": "public-access export; dataset-specific retention and redistribution review remains open"}
    atomic_json(root / "acquisition-metadata.json", metadata)
    return metadata
