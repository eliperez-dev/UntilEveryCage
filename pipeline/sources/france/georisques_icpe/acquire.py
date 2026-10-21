"""Bounded, terms-gated pagination for the official ICPE API V1 route."""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from pipeline.common.acquisition import fetch_source
from pipeline.contracts.source_lifecycle import atomic_json

from .adapter import GeorisquesIcpeAnimalAdapter
from .config import CONFIG


def _url(page: int, page_size: int) -> str:
    # Official OpenAPI documents comma-separated nomenclature values.
    query = urlencode({
        "nomenclature": ",".join(CONFIG["animal_rubrics"]),
        "page": page,
        "page_size": page_size,
    })
    return f'{CONFIG["source_url"]}?{query}'


def acquire_snapshot(*, output_root: str | Path, terms_review_path: str | Path,
                     run_id: str | None = None, timeout_seconds: float = 30.0,
                     page_size: int | None = None, max_pages: int | None = None,
                     max_records: int | None = None,
                     sleep_fn: Any = time.sleep) -> dict[str, Any]:
    """Fetch and reconcile one filtered snapshot; no unfiltered dump route."""
    from pipeline.common.acquisition import default_run_id

    size = page_size if page_size is not None else CONFIG["page_size"]
    page_cap = max_pages if max_pages is not None else CONFIG["max_pages"]
    row_cap = max_records if max_records is not None else CONFIG["max_records"]
    if (not 1 <= size <= 100 or not 1 <= page_cap <= CONFIG["max_pages"]
            or not 1 <= row_cap <= CONFIG["max_records"]):
        raise ValueError("page_size/max_pages/max_records exceed source safety bounds")
    snapshot_id = run_id or default_run_id()
    source_root = Path(output_root) / CONFIG["source_id"]
    snapshot_dir = source_root / "snapshots" / snapshot_id
    pages_dir = snapshot_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=False)
    adapter = GeorisquesIcpeAnimalAdapter()
    page_facts: list[dict[str, Any]] = []
    total: int | None = None
    total_pages: int | None = None
    seen_page_ids: set[str] = set()
    for page in range(1, page_cap + 1):
        if total_pages is not None and page > total_pages:
            break
        url = _url(page, size)

        def validate(path: Path, _headers: dict[str, str], expected_page: int = page) -> None:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError("ICPE response is not valid UTF-8 JSON") from error
            parsed = adapter._parse_payload_for_size(payload, expected_page, size, row_cap)
            if total is not None and (parsed["results"], parsed["total_pages"]) != (total, total_pages):
                raise ValueError("ICPE totals changed while fetching the snapshot")
            if parsed["results"] > row_cap or parsed["total_pages"] > page_cap:
                raise ValueError("ICPE response exceeds configured snapshot bounds")

        metadata = fetch_source(
            source_id=CONFIG["source_id"], url=url,
            output_root=source_root / "page-responses",
            artifact_name=f"page-{page:05d}.json",
            terms_review_path=terms_review_path,
            run_id=f"{snapshot_id}-page-{page:05d}",
            timeout_seconds=timeout_seconds,
            max_bytes=CONFIG["max_page_bytes"],
            allowed_content_types=("application/json",),
            code_version=CONFIG["adapter_version"],
            config_version=CONFIG["config_version"],
            coverage=CONFIG["coverage"],
            rights_caveat="Géorisques CGU state prior acceptance is required and identify Licence Ouverte 2.0; attribution/update-date obligations require review. Private acquisition only.",
            privacy_caveat="Restricted raw pages; preserve source facility names/identifiers for private review; no personal-contact expansion or geocoding.",
            query_context={"page": page, "page_size": size,
                           "nomenclature": list(CONFIG["animal_rubrics"]),
                           "animal_rubric_filter_only": True},
            artifact_validator=validate,
        )
        raw_path = Path(metadata["artifact_path"])
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        parsed = adapter._parse_payload_for_size(payload, page, size, row_cap)
        # API result rows are observations. Multiple rubric records may share
        # an AIOT, so retain their multiplicity but fail closed on an exact
        # repeated row or a missing stable identity during acquisition.
        for row in parsed["data"]:
            if not isinstance(row, dict):
                raise ValueError("ICPE page contains a non-object observation")
            aiot = adapter._text(row.get("codeAIOT"))
            if not aiot:
                raise ValueError("ICPE observation lacks its stable AIOT identifier")
            row_digest = hashlib.sha256(json.dumps(
                row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")).hexdigest()
            if row_digest in seen_page_ids:
                raise ValueError("ICPE pagination repeated an identical source observation")
            seen_page_ids.add(row_digest)
        if total is None:
            total, total_pages = parsed["results"], parsed["total_pages"]
            if total > row_cap or total_pages > page_cap:
                raise ValueError("filtered snapshot exceeds configured record/page bound")
        destination = pages_dir / f"page-{page:05d}.json"
        shutil.copyfile(raw_path, destination)
        page_facts.append({"page": page, "sha256": metadata["sha256"],
                           "byte_size": metadata["byte_size"],
                           "rows": len(payload["data"]),
                           "retrieved_at_utc": metadata["retrieved_at_utc"],
                           "requested_url": metadata["requested_url"]})
        if page < (total_pages or 0):
            sleep_fn(CONFIG["minimum_delay_seconds"])
    if total is None or total_pages is None or len(page_facts) != total_pages:
        raise ValueError("bounded page loop ended before all API pages were acquired")
    if sum(item["rows"] for item in page_facts) != total:
        raise ValueError("acquired row count does not equal API results")
    concatenated = b"".join((pages_dir / f"page-{item['page']:05d}.json").read_bytes() for item in page_facts)
    manifest = {
        "source_id": CONFIG["source_id"], "source_url": CONFIG["source_url"],
        "run_id": snapshot_id, "retrieved_at_utc": page_facts[-1]["retrieved_at_utc"],
        "page_size": size, "pages": page_facts, "results": total,
        "total_pages": total_pages, "sha256": hashlib.sha256(concatenated).hexdigest(),
        "byte_size": len(concatenated), "artifact_path": str(pages_dir),
        "filter": {"nomenclature": list(CONFIG["animal_rubrics"])},
        "rights_caveat": "CGU acceptance recorded for private acquisition/processing only; attribution/update-date obligations and publication remain separately gated.",
        "publication_state": "blocked-pending-terms-privacy-factual-release-review",
    }
    atomic_json(snapshot_dir / "snapshot-manifest.json", manifest)
    return manifest
