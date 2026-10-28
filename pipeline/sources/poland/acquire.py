"""Bounded acquisition of every GIW approval section, using published paging."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
import urllib.error

from pipeline.contracts.source_lifecycle import atomic_bytes, atomic_json
from .adapter import ADAPTER_VERSION, SCHEMA_VERSION, SECTIONS, SOURCE_ID, SOURCE_URL, RegisterPage, bundle_digest

MAX_BYTES = 32 * 1024 * 1024
MAX_PAGES = 600
MAX_PAGE_BYTES = 512 * 1024


class SourceRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname != "zywnosc.wetgiw.gov.pl":
            raise ValueError("GIW redirect escaped the source host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(*, output_root: Path, run_id: str, terms_review_path: Path,
          timeout_seconds=30, max_bytes=MAX_BYTES, opener=None, pause_seconds=.55, resume_root: Path | None = None):
    review = json.loads(terms_review_path.read_text(encoding="utf-8"))
    if (review.get("source_id") != SOURCE_ID or review.get("decision") != "approved"
            or review.get("private_preview_only") is not True or review.get("source_url") != SOURCE_URL):
        raise ValueError("GIW private source terms review is required")
    max_bytes = min(int(max_bytes), MAX_BYTES)
    timeout_seconds = min(float(timeout_seconds), 30)
    target = output_root / SOURCE_ID / run_id
    pages = target / "source-pages"
    pages.mkdir(parents=True, exist_ok=True)
    client = opener or urllib.request.build_opener(SourceRedirect())
    receipts, sections, total, requests = [], [], 0, 0
    resumed = 0
    if resume_root is not None:
        resume_root = Path(resume_root).resolve(strict=True)
        allowed = Path(__file__).resolve().parents[3] / "data/staging"
        if not resume_root.is_relative_to(allowed) or resume_root.name != "source-pages" or resume_root.is_symlink():
            raise ValueError("GIW partial recovery must use the assigned private staging pages")

    def request(section, page, page_size=20):
        nonlocal requests
        if requests >= MAX_PAGES:
            raise ValueError("GIW acquisition exceeded the request limit")
        if requests and pause_seconds:
            time.sleep(pause_seconds)
        requests += 1
        url = SOURCE_URL + "?" + urllib.parse.urlencode({"sekcja": section, "poprzedniaSekcja": section,
                                                       "lng": 1, "pagenbr": page, "onpage": page_size})
        req = urllib.request.Request(url, headers={"User-Agent": "UntilEveryCage-source-pipeline/2.0", "Accept": "text/html"})
        atomic_json(target / "acquisition-progress.json", {"status": "fetching", "section": section, "page": page,
            "requests": requests, "completed_pages": len(receipts)})
        for attempt in range(2):
            try:
                with client.open(req, timeout=timeout_seconds) as response:
                    final = urllib.parse.urlsplit(response.geturl())
                    if (response.status != 200 or final.scheme != "https" or final.hostname != "zywnosc.wetgiw.gov.pl"
                            or final.path != "/spi/zatw/index.php"):
                        raise ValueError("GIW source access or redirect changed")
                    raw = response.read(MAX_PAGE_BYTES + 1)
                    if len(raw) > MAX_PAGE_BYTES:
                        raise ValueError("GIW page exceeded the byte limit")
                    facts = {"requested_url": url, "final_url": response.geturl(), "http_status": response.status,
                             "content_type": response.headers.get("Content-Type"), "byte_size": len(raw),
                             "sha256": hashlib.sha256(raw).hexdigest(), "attempts": attempt + 1,
                             "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                break
            except (TimeoutError, ConnectionError, urllib.error.URLError):
                if attempt or requests >= MAX_PAGES: raise
                requests += 1
                time.sleep(2)
        parsed = RegisterPage(raw)
        if parsed.selected_section != section:
            raise ValueError("GIW response changed the selected section")
        return raw, parsed, facts

    for section in SECTIONS:
        raw, first, facts = request(section, 1)
        count = first.count
        page_size = max(first.ordinals, default=20)
        if page_size > 100 or not first.ordinals.issubset(set(range(1,min(count,page_size)+1))):
            raise ValueError("GIW first-page ordinal coverage is invalid")
        page_count = max(1, (count + page_size - 1) // page_size)
        if page_count > 200 or first.last_page != page_count:
            raise ValueError("GIW count and published pagination disagree")
        ordinals = set()
        identities = set()
        for page_number in range(1, page_count + 1):
            filename = f"section-{section:02d}-page-{page_number:04d}.html"
            if page_number > 1:
                cached = None
                for folder in (pages, resume_root):
                    file = folder / filename if folder is not None else None
                    if file is None or not file.is_file() or file.is_symlink(): continue
                    retained_at = datetime.fromtimestamp(file.stat().st_mtime, timezone.utc)
                    age = (datetime.now(timezone.utc) - retained_at).total_seconds()
                    if not 0 <= age <= 7200: continue
                    content = file.read_bytes()
                    if len(content) > MAX_PAGE_BYTES: continue
                    candidate = RegisterPage(content)
                    if candidate.count == count and candidate.selected_section == section:
                        cached = (file, content, candidate, retained_at)
                        break
                if cached is None:
                    raw, parsed, facts = request(section, page_number, page_size)
                else:
                    file, raw, parsed, retained_at = cached
                    resumed += 1
                    receipt_path = file.parent.parent / (filename + ".receipt.json")
                    original = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() and not receipt_path.is_symlink() else {}
                    digest = hashlib.sha256(raw).hexdigest()
                    if original and (original.get("sha256") != digest or original.get("byte_size") != len(raw)):
                        raise ValueError("GIW recovered page receipt does not match its bytes")
                    facts = {**original, "source_capture": "recovered_partial_operator_capture",
                             "original_http_metadata": original.get("original_http_metadata", "retained" if original else "not_retained"),
                             "original_artifact_path": str(file), "retained_file_time_utc": retained_at.isoformat(),
                             "byte_size": len(raw), "sha256": digest}
            else:
                parsed = first
            expected = set(range((page_number-1)*page_size+1, min(page_number*page_size, count)+1))
            if (parsed.count != count or not parsed.ordinals.issubset(expected) or ordinals & parsed.ordinals
                    or (expected and not parsed.ordinals)):
                raise ValueError("GIW page count or ordinal coverage changed")
            ids = {r["wni"] for r in parsed.data}
            # The register may list the same WNI under multiple numbered entries.
            # Ordinals establish paging completeness; WNI groups source identity.
            identities.update(ids)
            ordinals.update(parsed.ordinals)
            total += len(raw)
            if total > max_bytes:
                raise ValueError("GIW section bundle exceeded the byte limit")
            atomic_bytes(pages / filename, raw)
            receipts.append({**facts, "artifact": filename, "section": section, "page": page_number,
                             "establishment_entries": len(parsed.ordinals), "approval_observations": len(parsed.data),
                             "source_omitted_ordinals": sorted(expected - parsed.ordinals)})
            atomic_json(target / (filename + ".receipt.json"), receipts[-1])
        _, final, _ = request(section, 1, page_size)
        # The source's associated-activity aggregation has no stable ordering.
        # Preserve it verbatim per page; compare stable site/approval fields.
        stable = lambda p: {(r["ordinal"], r["wni"], r["name"], r["address"]) for r in p.data}
        if (final.count != count or final.ordinals != first.ordinals
                or stable(final) != stable(first)):
            raise ValueError("GIW section changed while acquiring its pages")
        sections.append({"section": section, "label": first.section_options[section],
                         "establishment_entries": count, "page_count": page_count, "page_size": page_size,
                         "observed_establishment_entries": len(ordinals),
                         "source_omitted_ordinals": sorted(set(range(1,count+1)) - ordinals),
                         "unique_veterinary_identifiers": len(identities), "count_rechecked": True})
    digest, size = bundle_digest(pages)
    facts = {"source_id": SOURCE_ID, "run_id": run_id, "canonical_url": SOURCE_URL,
             "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
             "artifact_sha256": digest, "artifact_byte_size": size, "page_count": len(receipts),
             "request_count": requests, "sections": sections, "pages": receipts,
             "recovered_partial_pages": resumed,
             "acquisition_method": "live_register_pages_with_explicit_same_day_partial_recovery" if resumed else "live_register_pages",
             "source_establishment_section_entries": sum(s["establishment_entries"] for s in sections),
             "approval_observations": sum(p["approval_observations"] for p in receipts),
             "terms_review": review, "adapter_version": ADAPTER_VERSION, "schema_version": SCHEMA_VERSION,
             "geocoding": "not_run", "publication": "not_created"}
    atomic_json(target / "acquisition-metadata.json", facts)
    atomic_json(target / "acquisition-progress.json", {"status": "completed", "completed_pages": len(receipts), "requests": requests})
    return {**facts, "artifact_path": str(pages)}
