"""Private APHIS refresh with a documented-download or assisted-capture boundary."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline.common.acquisition import AcquisitionError, utc_now
from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_health import build_health_snapshot, write_health_snapshot
from pipeline.contracts.source_lifecycle import atomic_json

from .acquire import CSV_PROFILES, ALL_PROFILES, fetch_profile, parse_query_context, profile_url, validate_download
from .adapter import CONFIG, AphisPublicSearchAdapter
from .handoff import import_private_candidate, write_private_handoff


def assisted_capture_contract(profile: str) -> dict[str, Any]:
    if profile not in ALL_PROFILES:
        raise ValueError("unsupported APHIS profile")
    return {
        "source_id": CONFIG["source_id"],
        "profile": profile,
        "method": "operator-assisted-public-search-export",
        "source_url": profile_url(profile),
        "steps": [
            "Open the APHIS Animal Care Public Search Tool or the documented annual-summary/inspection page in an authorized browser session.",
            f"Select the {profile.replace('_', ' ')} view and use only its documented export or download control.",
            "For annual reports, retain the selected fiscal year and any amended-report indicator; for documents, retain the report/document identifier and displayed source date.",
            "Save the export or linked document without editing it; record query parameters, displayed date/year, final URL, and the retrieval time in the run metadata.",
            "Run the private dry-run and review profile, schema/signature, duplicate IDs, missing dates, privacy, and coverage before any test-only handoff.",
        ],
        "boundaries": [
            "No automation against hidden endpoints, browser internals, credentials, rate limits, or access-control challenges.",
            "Registrations/licenses, annual reports, inspections, downloadable documents/amendments, laboratories, and aggregate summaries are separate evidence types.",
            "A failed or empty response is not a valid zero-row observation; keep the previous validated artifact available.",
            "Absence is not closure and an inspection or document is not a facility-master assertion.",
        ],
    }


def _local_metadata(
    path: Path,
    *,
    profile: str,
    source_url: str | None,
    retrieved_at_utc: str | None,
    effective_date: str | None,
    publication_date: str | None,
    query_context: dict[str, Any] | None,
) -> dict[str, Any]:
    raw = path.read_bytes()
    validate_download(profile, path)
    return {
        "acquisition_method": "preserved_local_artifact",
        "source_id": CONFIG["source_id"],
        "profile": profile,
        "artifact": path.name,
        "artifact_path": str(path),
        "requested_url": source_url or profile_url(profile),
        "final_url": source_url or profile_url(profile),
        "retrieved_at_utc": retrieved_at_utc or utc_now(),
        "effective_date": effective_date or "unknown",
        "publication_date": publication_date,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_size": len(raw),
        "code_version": CONFIG["adapter_version"],
        "config_version": CONFIG["contract_version"],
        "rights_caveat": "APHIS export terms and attribution require operator review before publication",
        "privacy_caveat": "restricted private staging; address, names, documents, and coordinates require review",
        "coverage": f"APHIS {profile} export only; no facility merge or completeness claim",
        "terms_review": "required before publication",
        "query_context": {**(query_context or {}), "profile": profile},
        "retention": {"class": "restricted-research-evidence", "public_exposure": False, "review_required": True},
    }


def refresh(
    *,
    run_dir: str | Path,
    profile: str,
    raw_path: str | Path | None = None,
    fetch: bool = False,
    source_url: str | None = None,
    terms_review_path: str | Path | None = None,
    output_root: str | Path = "data/raw",
    run_id: str | None = None,
    retrieved_at_utc: str | None = None,
    effective_date: str | None = None,
    publication_date: str | None = None,
    query_context: dict[str, Any] | None = None,
    timeout_seconds: float = 60.0,
    max_bytes: int = 128 * 1024 * 1024,
) -> dict[str, Any]:
    if profile not in CSV_PROFILES:
        raise ValueError("refresh parses registrations, annual_reports, or inspections; use acquire.py for documents/amendments")
    if fetch == (raw_path is not None):
        raise ValueError("specify exactly one of raw_path or fetch")
    root = Path(run_dir)
    if fetch:
        if terms_review_path is None:
            raise ValueError("terms_review_path is required for network acquisition")
        acquisition = fetch_profile(
            profile=profile,
            output_root=Path(output_root),
            terms_review_path=terms_review_path,
            source_url=source_url,
            run_id=run_id,
            query_context=query_context,
            publication_date=publication_date,
            effective_date=effective_date,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
        )
        path = Path(acquisition["artifact_path"])
    else:
        path = Path(raw_path)  # type: ignore[arg-type]
        if not path.is_file():
            raise ValueError(f"raw artifact does not exist: {path}")
        acquisition = _local_metadata(
            path,
            profile=profile,
            source_url=source_url,
            retrieved_at_utc=retrieved_at_utc,
            effective_date=effective_date,
            publication_date=publication_date,
            query_context=query_context,
        )

    raw = path.read_bytes()
    artifact = SourceArtifact(
        source_url=str(acquisition["final_url"]),
        retrieved_at_utc=str(acquisition["retrieved_at_utc"]),
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        publication_date=acquisition.get("publication_date"),
        effective_date=acquisition.get("effective_date") or "unknown",
        code_version=CONFIG["adapter_version"],
        config_version=CONFIG["contract_version"],
        rights_caveat=acquisition["rights_caveat"],
        privacy_caveat=acquisition["privacy_caveat"],
        coverage=acquisition["coverage"],
    )
    atomic_json(root / "acquisition-metadata.json", acquisition)
    adapter = AphisPublicSearchAdapter()
    result = adapter.parse_bytes(raw)
    if result["profile"] != profile:
        raise ValueError(f"captured APHIS profile is {result['profile']}, expected {profile}")
    status = run_private_lifecycle(path, root, artifact, adapter, health_as_of_utc=artifact.retrieved_at_utc)
    contract = assisted_capture_contract(profile)
    status["assisted_capture_contract"] = contract
    status["query_context"] = acquisition.get("query_context") or {}
    atomic_json(root / "assisted-capture-contract.json", contract)
    if status.get("status") == "candidate-ready":
        lifecycle_root = Path(status["run_dir"])
        rows = [
            json.loads(line)
            for line in (lifecycle_root / "normalized/records.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        handoff = write_private_handoff(
            lifecycle_root / "candidate-handoff",
            rows,
            artifact,
            profile=profile,
            source_sha256=acquisition["sha256"],
        )
        imported = import_private_candidate(lifecycle_root / "candidate-handoff")
        atomic_json(lifecycle_root / "candidate-import.json", imported)
        write_health_snapshot(
            lifecycle_root / "source-health.json",
            build_health_snapshot(
                lifecycle_root,
                as_of_utc=artifact.retrieved_at_utc,
                import_evidence_path=lifecycle_root / "candidate-import.json",
            ),
        )
        status["candidate_handoff"] = handoff
        status["candidate_import"] = imported
    atomic_json(root / "run-status.json", status)
    return status

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--raw", type=Path)
    source.add_argument("--fetch", action="store_true")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--profile", choices=sorted(CSV_PROFILES), required=True)
    parser.add_argument("--source-url")
    parser.add_argument("--terms-review", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--run-id")
    parser.add_argument("--retrieved-at-utc")
    parser.add_argument("--effective-date")
    parser.add_argument("--publication-date")
    parser.add_argument("--query-context")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--max-bytes", type=int, default=128 * 1024 * 1024)
    args = parser.parse_args()
    try:
        result = refresh(
            run_dir=args.run_dir,
            profile=args.profile,
            raw_path=args.raw,
            fetch=args.fetch,
            source_url=args.source_url,
            terms_review_path=args.terms_review,
            output_root=args.output_root,
            run_id=args.run_id,
            retrieved_at_utc=args.retrieved_at_utc,
            effective_date=args.effective_date,
            publication_date=args.publication_date,
            query_context=parse_query_context(args.query_context),
            timeout_seconds=args.timeout_seconds,
            max_bytes=args.max_bytes,
        )
    except (AcquisitionError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": result.get("status"), "run_dir": result.get("run_dir")}, sort_keys=True))
    return 0 if result.get("status") in {"candidate-ready", "staged-restricted"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
