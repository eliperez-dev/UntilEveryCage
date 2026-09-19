"""Record provenance for APHIS inspection exports captured one public page at a time."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Sequence


CAPTURE_SCHEMA_VERSION = "us-aphis-inspection-page-capture-v1"
DOCUMENT_INVENTORY_SCHEMA_VERSION = "us-aphis-inspection-document-inventory-v1"
LINEAGE_COLUMNS = (
    "__capture_page_ordinal",
    "__capture_page_sha256",
    "__capture_page_byte_size",
    "__capture_page_row",
    "__capture_page_retrieved_at_utc",
    "__capture_source_url",
)


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


def _canonical_row(row: dict[str, Any], headers: Sequence[str]) -> bytes:
    values = {str(header): "" if row.get(header) is None else str(row.get(header)) for header in headers}
    return (json.dumps(values, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def build_lineage_csv(
    page_paths: Sequence[Path],
    *,
    page_metadata: Sequence[dict[str, Any]],
    output_path: Path,
    source_url: str,
) -> dict[str, Any]:
    """Create a derived CSV with explicit original-page row lineage."""

    if len(page_paths) != len(page_metadata):
        raise ValueError("page metadata must match page count")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    total_rows = 0
    expected_header: list[str] | None = None
    original_digest = hashlib.sha256()
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=output_path.parent,
            prefix=f".{output_path.name}.", delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            writer: csv.DictWriter | None = None
            for ordinal, (page_path, metadata) in enumerate(zip(page_paths, page_metadata), start=1):
                with page_path.open("r", encoding="utf-8-sig", newline="") as source:
                    reader = csv.DictReader(source)
                    header = list(reader.fieldnames or [])
                    if expected_header is None:
                        expected_header = header
                        writer = csv.DictWriter(handle, fieldnames=header + list(LINEAGE_COLUMNS), lineterminator="\n")
                        writer.writeheader()
                    elif header != expected_header:
                        raise ValueError(f"page header mismatch: {page_path}")
                    assert writer is not None
                    for page_row, row in enumerate(reader, start=1):
                        original_digest.update(_canonical_row(row, expected_header))
                        row.update({
                            "__capture_page_ordinal": str(ordinal),
                            "__capture_page_sha256": str(metadata["sha256"]),
                            "__capture_page_byte_size": str(metadata["byte_size"]),
                            "__capture_page_row": str(page_row),
                            "__capture_page_retrieved_at_utc": "unknown",
                            "__capture_source_url": source_url,
                        })
                        writer.writerow(row)
                        total_rows += 1
            handle.flush()
            derived_digest = hashlib.sha256()
            with temporary_path.open("r", encoding="utf-8", newline="") as derived_handle:
                derived_reader = csv.DictReader(derived_handle)
                derived_header = list(derived_reader.fieldnames or [])
                if derived_header[:len(expected_header or [])] != (expected_header or []):
                    raise ValueError("derived lineage CSV header drift")
                for derived_row in derived_reader:
                    derived_digest.update(_canonical_row(derived_row, expected_header or []))
            if derived_digest.hexdigest() != original_digest.hexdigest():
                raise ValueError("derived lineage CSV changed an original source row")
        temporary_path.replace(output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return {
        "classification": "derived_staging_with_original_page_lineage",
        "file": output_path.name,
        "sha256": _sha256(output_path),
        "byte_size": output_path.stat().st_size,
        "input_rows": total_rows,
        "lineage_columns": list(LINEAGE_COLUMNS),
        "original_row_sequence_sha256": original_digest.hexdigest(),
        "derived_row_sequence_sha256": derived_digest.hexdigest(),
        "row_sequence_match": True,
    }


def build_capture_manifest(
    page_paths: Sequence[Path],
    *,
    output_path: Path,
    source_url: str,
    retrieved_at_utc: str,
    query_context: dict[str, Any],
    excluded_files: Sequence[str] = (),
    lineage_output_path: Path | None = None,
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
                "source_url": source_url,
                "page_retrieved_at_utc": "unknown",
            }
        )
        total_rows += rows

    manifest = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "source_id": "us.aphis",
        "profile": "inspections",
        "source_url": source_url,
        "retrieved_at_utc": retrieved_at_utc,
        "retrieved_at_scope": "bundle_generation; per-page actual retrieval timestamps unknown",
        "query_context": query_context,
        "page_count": len(pages),
        "input_rows": total_rows,
        "headers": expected_header,
        "pages": pages,
        "excluded_files": list(excluded_files),
        "created_by": "pipeline.sources.us.aphis.capture",
    }
    if lineage_output_path is not None:
        derived = build_lineage_csv(
            page_paths,
            page_metadata=pages,
            output_path=lineage_output_path,
            source_url=source_url,
        )
        try:
            derived["file"] = str(lineage_output_path.relative_to(output_path.parent))
        except ValueError:
            pass
        manifest["derived_artifact"] = derived
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
    parser.add_argument("--lineage-output", type=Path)
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
        lineage_output_path=args.lineage_output,
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
