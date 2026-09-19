"""Record provenance for APHIS inspection exports captured one public page at a time."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


CAPTURE_SCHEMA_VERSION = "us-aphis-inspection-page-capture-v1"
DOCUMENT_INVENTORY_SCHEMA_VERSION = "us-aphis-inspection-document-inventory-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _page_stats(path: Path) -> tuple[list[str], int]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if not header:
            raise ValueError(f"empty CSV page: {path}")
        rows = sum(1 for row in reader if any(cell.strip() for cell in row))
    return header, rows


def build_capture_manifest(
    page_paths: Sequence[Path],
    *,
    output_path: Path,
    source_url: str,
    retrieved_at_utc: str,
    query_context: dict[str, Any],
    excluded_files: Sequence[str] = (),
) -> dict[str, Any]:
    """Write a row-free manifest for an ordered set of original page exports."""

    if not page_paths:
        raise ValueError("at least one page export is required")
    if not source_url or not retrieved_at_utc:
        raise ValueError("source_url and retrieved_at_utc are required")
    pages: list[dict[str, Any]] = []
    expected_header: list[str] | None = None
    total_rows = 0
    for ordinal, raw_path in enumerate(page_paths, start=1):
        path = Path(raw_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        header, rows = _page_stats(path)
        if expected_header is None:
            expected_header = header
        elif header != expected_header:
            raise ValueError(f"page header mismatch: {path}")
        pages.append(
            {
                "ordinal": ordinal,
                "file": path.name,
                "sha256": _sha256(path),
                "byte_size": path.stat().st_size,
                "data_rows": rows,
            }
        )
        total_rows += rows

    manifest = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "source_id": "us.aphis",
        "profile": "inspections",
        "source_url": source_url,
        "retrieved_at_utc": retrieved_at_utc,
        "query_context": query_context,
        "page_count": len(pages),
        "input_rows": total_rows,
        "headers": expected_header,
        "pages": pages,
        "excluded_files": list(excluded_files),
        "created_by": "pipeline.sources.us.aphis.capture",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def write_document_inventory(
    output_path: Path,
    *,
    source_url: str,
    query_context: dict[str, Any],
    associated_ui_link_rows: int,
    document_route: str,
    downloaded_documents: int,
    status: str,
    failure_reason: str,
) -> dict[str, Any]:
    """Write a row-free inventory when linked public documents cannot be retained."""

    inventory = {
        "schema_version": DOCUMENT_INVENTORY_SCHEMA_VERSION,
        "source_id": "us.aphis",
        "profile": "inspections",
        "source_url": source_url,
        "query_context": query_context,
        "associated_ui_link_rows": associated_ui_link_rows,
        "document_route_observed": document_route,
        "csv_document_reference_rows": 0,
        "downloaded_documents": downloaded_documents,
        "status": status,
        "failure_reason": failure_reason,
        "non_ui_endpoint_not_attempted": True,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return inventory


def _parse_query_context(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("query context must be a JSON object")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--retrieved-at-utc", required=True)
    parser.add_argument("--query-context", required=True, type=_parse_query_context)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--document-inventory", type=Path)
    parser.add_argument("--associated-ui-link-rows", type=int)
    parser.add_argument("--document-route")
    parser.add_argument("--downloaded-documents", type=int, default=0)
    parser.add_argument("--document-status")
    parser.add_argument("--document-failure-reason")
    args = parser.parse_args(argv)
    pages = sorted(args.page_dir.glob("page-*.csv"))
    build_capture_manifest(
        pages,
        output_path=args.output,
        source_url=args.source_url,
        retrieved_at_utc=args.retrieved_at_utc,
        query_context=args.query_context,
        excluded_files=args.exclude,
    )
    if args.document_inventory:
        required = {
            "associated-ui-link-rows": args.associated_ui_link_rows,
            "document-route": args.document_route,
            "document-status": args.document_status,
            "document-failure-reason": args.document_failure_reason,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            parser.error("document inventory requires: " + ", ".join(missing))
        write_document_inventory(
            args.document_inventory,
            source_url=args.source_url,
            query_context=args.query_context,
            associated_ui_link_rows=args.associated_ui_link_rows,
            document_route=args.document_route,
            downloaded_documents=args.downloaded_documents,
            status=args.document_status,
            failure_reason=args.document_failure_reason,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
