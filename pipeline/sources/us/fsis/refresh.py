"""Private FSIS refresh with a sanctioned assisted-acquisition boundary."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.common.acquisition import AcquisitionError, fetch_source, utc_now
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json

from .adapter import CONFIG, FsisMpiAdapter


def assisted_capture_contract(*, source_url: str = CONFIG["directory_url"]) -> dict[str, Any]:
    return {
        "source_id": CONFIG["source_id"],
        "method": "operator-assisted-official-export",
        "steps": [
            "Open the official FSIS MPI Directory page in an authorized browser session.",
            "Save one current MPI Directory CSV (by establishment name or number) and the supplemental Establishment Demographic CSV without editing them.",
            "Record the displayed edition/publication date and the final URL for each saved file.",
            "Place the directory CSV at --directory and, when available, the demographic CSV at --demographics; --raw remains a directory-only compatibility alias.",
            "Run dry-run first and review schema fingerprints, count/drift, duplicate identities, exact-key reconciliation, privacy, coordinates, and category results before any test-only handoff.",
        ],
        "controls": [
            "No credential or access-control bypass",
            "HTML, login, 403, and schema-drift responses fail closed",
            "No raw artifact in Git",
            "Directory and demographics join only on exact source-native IDs/numbers",
            "FSIS facility evidence is not joined to APHIS rows",
        ],
        "source_url": source_url,
        "current_routes": {
            "directory_by_name": CONFIG.get("directory_by_name_url"),
            "directory_by_number": CONFIG.get("directory_by_number_url"),
            "demographics": CONFIG.get("demographics_url"),
        },
    }


def _local_facts(path: Path, *, role: str, source_url: str, retrieved_at_utc: str, effective_date: str | None) -> dict[str, Any]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    return {
        "acquisition_method": "preserved_local_artifact",
        "source_id": f"{CONFIG['source_id']}.{role}",
        "artifact_role": role,
        "artifact": path.name,
        "artifact_path": str(path),
        "requested_url": source_url,
        "final_url": source_url,
        "retrieved_at_utc": retrieved_at_utc,
        "effective_date": effective_date or "unknown",
        "publication_date": None,
        "sha256": digest,
        "byte_size": len(raw),
        "code_version": CONFIG["adapter_version"],
        "config_version": CONFIG["contract_version"],
        "rights_caveat": "FSIS source terms and attribution require operator review before publication",
        "privacy_caveat": "private staging; address, phone, DUNS, and coordinate review pending",
        "coverage": "FSIS MPI edition only; state-inspection and APHIS populations excluded",
        "terms_review": "required before network acquisition or handoff",
    }


def _artifact(metadata: dict[str, Any]) -> SourceArtifact:
    return SourceArtifact(
        source_url=str(metadata.get("final_url") or metadata.get("requested_url")),
        retrieved_at_utc=str(metadata["retrieved_at_utc"]),
        sha256=str(metadata["sha256"]),
        byte_size=int(metadata["byte_size"]),
        publication_date=metadata.get("publication_date"),
        effective_date=metadata.get("effective_date"),
        code_version=str(metadata.get("code_version") or CONFIG["adapter_version"]),
        config_version=str(metadata.get("config_version") or CONFIG["contract_version"]),
        rights_caveat=metadata.get("rights_caveat"),
        privacy_caveat=metadata.get("privacy_caveat"),
        coverage=metadata.get("coverage"),
        redirects=tuple(metadata.get("redirects") or ()),
    )


def _drift(manifest: dict[str, Any], previous_manifest: str | Path | None) -> dict[str, Any]:
    if previous_manifest is None:
        return {"checked": False, "blocked": False, "alarms": []}
    previous = json.loads(Path(previous_manifest).read_text(encoding="utf-8"))
    alarms: list[str] = []
    if previous.get("schema_fingerprint") and previous["schema_fingerprint"] != manifest.get("schema_fingerprint"):
        alarms.append("directory_schema_fingerprint_changed")
    if previous.get("demographic_schema_fingerprint") and previous.get("demographic_schema_fingerprint") != manifest.get("demographic_schema_fingerprint"):
        alarms.append("demographic_schema_fingerprint_changed")
    before = previous.get("row_reconciliation", {}).get("directory_rows")
    after = manifest.get("row_reconciliation", {}).get("directory_rows")
    if isinstance(before, int) and before and isinstance(after, int) and abs(after - before) > max(100, before // 10):
        alarms.append("directory_row_count_changed_gt_10_percent")
    return {"checked": True, "blocked": bool(alarms), "alarms": alarms, "previous_manifest": str(previous_manifest)}


def _currentness(effective_date: str | None, *, max_age_days: int) -> dict[str, Any]:
    """Classify the displayed source edition without guessing when absent."""
    if max_age_days < 0:
        raise ValueError("max_age_days must be non-negative")
    if not effective_date or effective_date == "unknown":
        return {"status": "unknown", "blocked": True, "effective_date": "unknown", "max_age_days": max_age_days}
    try:
        observed = datetime.fromisoformat(effective_date.replace("Z", "+00:00")).date()
    except ValueError as error:
        raise ValueError("effective_date must be ISO-8601") from error
    today = datetime.now(timezone.utc).date()
    age_days = (today - observed).days
    return {"status": "current" if 0 <= age_days <= max_age_days else "stale", "blocked": age_days < 0 or age_days > max_age_days,
            "effective_date": observed.isoformat(), "age_days": age_days, "max_age_days": max_age_days}


def refresh(
    *,
    run_dir: str | Path,
    raw_path: str | Path | None = None,
    directory_path: str | Path | None = None,
    demographics_path: str | Path | None = None,
    fetch: bool = False,
    source_url: str = CONFIG["directory_url"],
    retrieved_at_utc: str | None = None,
    effective_date: str | None = None,
    mode: str = "dry-run",
    terms_review_path: str | Path | None = None,
    previous_manifest: str | Path | None = None,
    max_bytes: int = 128 * 1024 * 1024,
    max_attempts: int = 3,
    retry_delay_seconds: float = 1.0,
    max_retry_delay_seconds: float = 30.0,
    max_age_days: int = 14,
) -> dict[str, Any]:
    if raw_path is not None and directory_path is not None:
        raise ValueError("specify raw_path or directory_path, not both")
    if raw_path is not None and demographics_path is not None:
        raise ValueError("--demographics requires --directory")
    if fetch and (raw_path is not None or directory_path is not None or demographics_path is not None):
        raise ValueError("fetch cannot be combined with local artifacts")
    if not fetch and raw_path is None and directory_path is None:
        raise ValueError("specify a directory artifact or fetch")
    if mode not in {"dry-run", "handoff"}:
        raise ValueError("mode must be dry-run or handoff")

    root = Path(run_dir)
    metadata: dict[str, Any] = {}
    paths: dict[str, Path] = {}
    if fetch:
        if terms_review_path is None:
            raise ValueError("terms_review_path is required for network acquisition")
        routes = {
            "directory": CONFIG.get("directory_by_number_url") or CONFIG["data_url"],
            "demographics": CONFIG.get("demographics_url"),
        }
        for role, url in routes.items():
            if not url:
                raise ValueError(f"missing configured FSIS {role} URL")
            try:
                acquired = fetch_source(
                    source_id=f"{CONFIG['source_id']}.{role}", url=url, output_root=root / "acquisition",
                    artifact_name=f"{role}.csv", terms_review_path=terms_review_path, max_bytes=max_bytes,
                    allowed_content_types=("text/csv", "application/csv", "application/octet-stream"),
                    code_version=CONFIG["adapter_version"], config_version=CONFIG["contract_version"],
                    coverage="FSIS MPI edition only; state-inspection and APHIS populations excluded",
                    rights_caveat="terms review retained with run", privacy_caveat="private staging; privacy review pending",
                    effective_date=effective_date,
                    max_attempts=max_attempts,
                    retry_delay_seconds=retry_delay_seconds,
                    max_retry_delay_seconds=max_retry_delay_seconds,
                )
            except AcquisitionError:
                # Preserve the shared failure class, retryability, and attempt
                # ledger for the aggregate operator report.  The role remains
                # identifiable from the private acquisition-failure.json.
                raise
            paths[role] = Path(acquired["artifact_path"])
            metadata[role] = acquired
    else:
        paths["directory"] = Path(directory_path or raw_path)  # type: ignore[arg-type]
        if not paths["directory"].is_file():
            raise ValueError(f"directory artifact does not exist: {paths['directory']}")
        observed_at = retrieved_at_utc or utc_now()
        metadata["directory"] = _local_facts(
            paths["directory"], role="directory",
            source_url=CONFIG.get("directory_by_number_url") or source_url,
            retrieved_at_utc=observed_at, effective_date=effective_date,
        )
        if demographics_path is not None:
            paths["demographics"] = Path(demographics_path)
            if not paths["demographics"].is_file():
                raise ValueError(f"demographics artifact does not exist: {paths['demographics']}")
            metadata["demographics"] = _local_facts(paths["demographics"], role="demographics", source_url=CONFIG.get("demographics_url", source_url), retrieved_at_utc=observed_at, effective_date=effective_date)

    atomic_json(root / "acquisition-metadata.json", metadata)
    artifacts = {role: _artifact(facts) for role, facts in metadata.items()}
    adapter = FsisMpiAdapter()
    lifecycle_root = root / "lifecycle"
    manifest = adapter.run_sources(paths, lifecycle_root, artifacts)
    currentness = _currentness(effective_date or metadata["directory"].get("effective_date"), max_age_days=max_age_days)
    manifest["currentness"] = currentness
    drift = _drift(manifest, previous_manifest)
    manifest["drift"] = drift
    atomic_json(lifecycle_root / "manifest.json", manifest)
    if mode == "handoff" and (drift["blocked"] or currentness["blocked"]):
        reasons = drift["alarms"] + (["source_effective_date_not_current"] if currentness["blocked"] else [])
        raise ValueError("refresh gate blocks handoff: " + ", ".join(reasons))

    handoff = None
    if mode == "handoff":
        bundle_artifact = SourceArtifact(
            source_url=manifest["source_url"], retrieved_at_utc=manifest["retrieved_at_utc"],
            sha256=manifest["sha256"], byte_size=manifest["byte_size"], publication_date=manifest.get("publication_date"),
            effective_date=manifest.get("effective_date"), code_version=manifest["code_version"],
            config_version=manifest["config_version"], rights_caveat=manifest.get("acquisition", {}).get("rights_caveat"),
            privacy_caveat=manifest.get("acquisition", {}).get("privacy_caveat"), coverage=manifest.get("coverage"),
        )
        handoff = adapter.write_candidate_handoff(
            lifecycle_root,
            artifacts["directory"],
            output_dir=lifecycle_root / "handoff",
            bundle_artifact=bundle_artifact,
            source_artifacts=manifest.get("source_artifacts"),
        )

    status = {
        "status": "candidate-ready" if handoff else "staged-restricted",
        "mode": mode,
        "candidate_created": bool(handoff),
        "release_promoted": False,
        "release_state": "not-created",
        "publication_state": "private-candidate" if handoff else "terms-gate-blocked",
        "public_surfaces": {"api": False, "map": False, "export": False, "cache": False, "history": False},
        "geocoding": "disabled",
        "run_dir": str(lifecycle_root),
        "manifest": manifest,
        "drift": drift,
        "assisted_capture_contract": assisted_capture_contract(source_url=source_url),
    }
    atomic_json(lifecycle_root / "run-status.json", status)
    atomic_json(root / "assisted-capture-contract.json", status["assisted_capture_contract"])
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--raw", type=Path, help="legacy alias for a directory CSV")
    source.add_argument("--directory", type=Path)
    source.add_argument("--fetch", action="store_true")
    parser.add_argument("--demographics", type=Path)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--source-url", default=CONFIG["directory_url"])
    parser.add_argument("--retrieved-at-utc")
    parser.add_argument("--effective-date")
    parser.add_argument("--previous-manifest", type=Path)
    parser.add_argument("--terms-review", type=Path)
    parser.add_argument("--mode", choices=("dry-run", "handoff"), default="dry-run")
    parser.add_argument("--max-bytes", type=int, default=128 * 1024 * 1024)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--retry-delay-seconds", type=float, default=1.0)
    parser.add_argument("--max-retry-delay-seconds", type=float, default=30.0)
    parser.add_argument("--max-age-days", type=int, default=14)
    args = parser.parse_args()
    try:
        result = refresh(
            run_dir=args.run_dir, raw_path=args.raw, directory_path=args.directory, demographics_path=args.demographics,
            fetch=args.fetch, source_url=args.source_url, retrieved_at_utc=args.retrieved_at_utc,
            effective_date=args.effective_date, mode=args.mode, terms_review_path=args.terms_review,
            previous_manifest=args.previous_manifest, max_bytes=args.max_bytes,
            max_attempts=args.max_attempts, retry_delay_seconds=args.retry_delay_seconds,
            max_retry_delay_seconds=args.max_retry_delay_seconds,
            max_age_days=args.max_age_days,
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 2
    print(json.dumps({"status": result.get("status"), "run_dir": result.get("run_dir"), "manifest": result.get("manifest", {}).get("source_id")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
