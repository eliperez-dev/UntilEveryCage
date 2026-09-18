"""Bounded private acquisition for documented APHIS downloads.

APHIS is an interactive public-search service.  This module permits a direct
fetch only when an operator supplies a terms-reviewed, documented download
URL.  The normal supported path remains saving the export or linked report in
an authorized browser and passing it to ``refresh --raw``.  It never probes
hidden endpoints, paginates a UI, or bypasses a challenge or access control.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

from pipeline.common.acquisition import AcquisitionError, fetch_source
from pipeline.contracts.source_lifecycle import atomic_json

from .adapter import CONFIG


CSV_PROFILES = {"registrations", "annual_reports", "inspections"}
DOCUMENT_PROFILES = {"documents"}
ALL_PROFILES = CSV_PROFILES | DOCUMENT_PROFILES
CHALLENGE_MARKERS = (
    b"<html",
    b"<!doctype",
    b"captcha",
    b"cloudflare",
    b"just a moment",
    b"access denied",
    b"sign in",
    b"login required",
)


def profile_url(profile: str) -> str:
    if profile not in ALL_PROFILES:
        raise ValueError(f"unsupported APHIS profile: {profile}")
    return {
        "registrations": CONFIG["public_search_url"],
        "annual_reports": CONFIG["annual_reports_url"],
        "inspections": CONFIG["inspection_reports_url"],
        "documents": CONFIG["documents_url"],
    }[profile]


def _csv_download_is_valid(path: Path) -> None:
    raw = path.read_bytes()
    if not raw:
        raise AcquisitionError("APHIS export is empty", failure_class="empty-response")
    if any(marker in raw[:65536].lower() for marker in CHALLENGE_MARKERS):
        raise AcquisitionError(
            "APHIS export appears to be HTML, a login page, or a challenge response",
            failure_class="challenge-response",
            action="use the documented browser export workflow; do not bypass the challenge",
        )
    try:
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True))
    except (UnicodeDecodeError, csv.Error) as error:
        raise AcquisitionError(
            "APHIS export is malformed or truncated",
            failure_class="malformed-export",
            action="repeat the documented export and inspect the saved file before retrying",
        ) from error
    if len(rows) < 2 or not rows[0] or not any(cell.strip() for cell in rows[0]):
        raise AcquisitionError(
            "APHIS export contains no data rows",
            failure_class="empty-response",
            action="check the selected profile and query in the authorized browser export",
        )
    width = len(rows[0])
    if any(len(row) != width for row in rows[1:]):
        raise AcquisitionError(
            "APHIS export has inconsistent row widths",
            failure_class="truncated-response",
            action="repeat the documented export and retain the prior validated artifact",
        )


def _document_is_valid(path: Path) -> None:
    raw = path.read_bytes()
    if not raw:
        raise AcquisitionError("APHIS document is empty", failure_class="empty-response")
    head = raw[:65536].lower()
    if any(marker in head for marker in CHALLENGE_MARKERS):
        raise AcquisitionError(
            "APHIS document appears to be HTML, a login page, or a challenge response",
            failure_class="challenge-response",
            action="use the documented browser download workflow; do not bypass the challenge",
        )
    is_pdf = raw.startswith(b"%PDF-") and b"%%EOF" in raw[-8192:]
    is_zip_container = raw.startswith(b"PK\x03\x04")
    if not (is_pdf or is_zip_container):
        raise AcquisitionError(
            "APHIS document has no recognized PDF or Office-container signature",
            failure_class="invalid-document",
            action="retain the failed response for diagnosis and use the documented download control",
        )


def validate_download(profile: str, path: Path, headers: dict[str, str] | None = None) -> None:
    """Validate bytes after download and before the artifact is committed."""
    if profile in CSV_PROFILES:
        _csv_download_is_valid(path)
    elif profile in DOCUMENT_PROFILES:
        _document_is_valid(path)
    else:
        raise ValueError(f"unsupported APHIS profile: {profile}")


def _artifact_name(profile: str, requested_name: str | None) -> str:
    if requested_name:
        name = Path(requested_name).name
        if name != requested_name or not name:
            raise ValueError("artifact name must be a simple filename")
        return name
    return "source.pdf" if profile == "documents" else "source.csv"


def _write_manifest(metadata: dict[str, Any], profile: str) -> dict[str, Any]:
    artifact_path = Path(metadata["artifact_path"])
    manifest = {
        "manifest_version": "us-aphis-acquisition-v1",
        "source_id": CONFIG["source_id"],
        "profile": profile,
        "artifact": metadata["artifact"],
        "artifact_path": str(artifact_path),
        "source_url": metadata["final_url"],
        "requested_url": metadata["requested_url"],
        "retrieved_at_utc": metadata["retrieved_at_utc"],
        "effective_date": metadata.get("effective_date") or "unknown",
        "publication_date": metadata.get("publication_date"),
        "sha256": metadata["sha256"],
        "byte_size": metadata["byte_size"],
        "query_context": metadata.get("query_context") or {},
        "adapter_version": CONFIG["adapter_version"],
        "config_version": CONFIG["contract_version"],
        "release_state": "not-created",
        "publication_state": "private-research-evidence",
        "publication_gate": "blocked",
        "retention": metadata["retention"],
        "coverage": metadata.get("coverage"),
        "document_policy": "documents and amendments remain source evidence; no automatic merge or release",
    }
    atomic_json(artifact_path.parent / "manifest.json", manifest)
    return manifest


def fetch_profile(
    *,
    profile: str,
    output_root: str | Path,
    terms_review_path: str | Path,
    source_url: str | None = None,
    run_id: str | None = None,
    query_context: dict[str, Any] | None = None,
    publication_date: str | None = None,
    effective_date: str | None = None,
    timeout_seconds: float = 60.0,
    max_bytes: int = 128 * 1024 * 1024,
    artifact_name: str | None = None,
) -> dict[str, Any]:
    if profile not in ALL_PROFILES:
        raise ValueError(f"unsupported APHIS profile: {profile}")
    context = {**(query_context or {}), "profile": profile}
    url = source_url or profile_url(profile)
    metadata = fetch_source(
        source_id=CONFIG["source_id"],
        url=url,
        output_root=output_root,
        artifact_name=_artifact_name(profile, artifact_name),
        terms_review_path=terms_review_path,
        run_id=run_id,
        timeout_seconds=timeout_seconds,
        max_bytes=max_bytes,
        allowed_content_types=(
            "text/csv",
            "application/csv",
            "application/pdf",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/octet-stream",
        ),
        effective_date=effective_date,
        publication_date=publication_date,
        code_version=CONFIG["adapter_version"],
        config_version=CONFIG["contract_version"],
        coverage=f"APHIS {profile} documented download only; no facility merge or completeness claim",
        rights_caveat="APHIS source terms and attribution require operator review before publication",
        privacy_caveat="restricted private staging; names, addresses, documents, and coordinates require review",
        query_context=context,
        artifact_validator=lambda path, headers: validate_download(profile, path, headers),
    )
    metadata["profile"] = profile
    atomic_json(Path(metadata["artifact_path"]).parent / "acquisition-metadata.json", metadata)
    _write_manifest(metadata, profile)
    return metadata


def preserve_local_document(
    *,
    raw_path: str | Path,
    run_dir: str | Path,
    source_url: str | None = None,
    retrieved_at_utc: str | None = None,
    effective_date: str | None = None,
    publication_date: str | None = None,
    query_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register an operator-saved document without copying or parsing it."""
    path = Path(raw_path)
    if not path.is_file():
        raise ValueError(f"raw artifact does not exist: {path}")
    validate_download("documents", path)
    raw = path.read_bytes()
    metadata = {
        "acquisition_method": "operator_assisted_document_download",
        "source_id": CONFIG["source_id"],
        "profile": "documents",
        "artifact": path.name,
        "artifact_path": str(path),
        "requested_url": source_url or CONFIG["documents_url"],
        "final_url": source_url or CONFIG["documents_url"],
        "retrieved_at_utc": retrieved_at_utc,
        "effective_date": effective_date or "unknown",
        "publication_date": publication_date,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_size": len(raw),
        "query_context": {**(query_context or {}), "profile": "documents"},
        "adapter_version": CONFIG["adapter_version"],
        "config_version": CONFIG["contract_version"],
        "coverage": "APHIS downloadable document/amendment only; source evidence, no automatic row merge",
        "rights_caveat": "APHIS source terms and attribution require operator review before publication",
        "privacy_caveat": "restricted private staging; document contents require review",
        "retention": {"class": "restricted-research-evidence", "public_exposure": False, "review_required": True},
    }
    if not retrieved_at_utc:
        raise ValueError("retrieved_at_utc is required for a preserved document")
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    atomic_json(root / "acquisition-metadata.json", metadata)
    return _write_manifest(metadata, "documents")


def parse_query_context(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    path = Path(value)
    try:
        payload = json.loads(path.read_text(encoding="utf-8") if path.is_file() else value)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("query context must be JSON or a path to a JSON file") from error
    if not isinstance(payload, dict):
        raise ValueError("query context must be a JSON object")
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=sorted(ALL_PROFILES), required=True)
    parser.add_argument("--terms-review", type=Path)
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--run-id")
    parser.add_argument("--source-url")
    parser.add_argument("--query-context")
    parser.add_argument("--publication-date")
    parser.add_argument("--effective-date")
    parser.add_argument("--retrieved-at-utc")
    parser.add_argument("--artifact-name")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--max-bytes", type=int, default=128 * 1024 * 1024)
    args = parser.parse_args()
    try:
        query_context = parse_query_context(args.query_context)
        if args.raw:
            if args.profile != "documents" or args.run_dir is None:
                raise ValueError("--raw requires --profile documents and --run-dir")
            metadata = preserve_local_document(
                raw_path=args.raw,
                run_dir=args.run_dir,
                source_url=args.source_url,
                retrieved_at_utc=args.retrieved_at_utc,
                publication_date=args.publication_date,
                effective_date=args.effective_date,
                query_context=query_context,
            )
            print(json.dumps({"status": "preserved", "manifest": str(Path(args.run_dir) / "manifest.json"), "sha256": metadata["sha256"]}, sort_keys=True))
            return 0
        if args.terms_review is None:
            raise ValueError("--terms-review is required for documented network acquisition")
        metadata = fetch_profile(
            profile=args.profile,
            output_root=args.output_root,
            terms_review_path=args.terms_review,
            source_url=args.source_url,
            run_id=args.run_id,
            query_context=query_context,
            publication_date=args.publication_date,
            effective_date=args.effective_date,
            timeout_seconds=args.timeout_seconds,
            max_bytes=args.max_bytes,
            artifact_name=args.artifact_name,
        )
    except (AcquisitionError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "acquired", "artifact_path": metadata["artifact_path"], "sha256": metadata["sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
