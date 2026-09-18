"""Run and inspect the private US refresh lanes as one operator workflow.

This module is orchestration only.  FSIS and APHIS keep their own acquisition
and adapter contracts; this command invokes them, then emits one row-free
operator report with freshness, validation, reconciliation, quarantine, and
private-import readiness.  It cannot create or promote a public release.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.common.source_operations import classify_failure, freshness_for, load_source_schedules
from pipeline.contracts.source_lifecycle import atomic_json

from .aphis.refresh import refresh as refresh_aphis
from .fsis.refresh import refresh as refresh_fsis


REPORT_VERSION = "us-operator-report-v1"
PUBLIC_SURFACES = {"api": False, "map": False, "export": False, "cache": False, "history": False}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _as_of(value: str | None) -> str:
    if value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("as_of_utc must include a timezone")
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return _now()


def _load_plan(path: str | Path) -> tuple[dict[str, Any], Path]:
    plan_path = Path(path).resolve()
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"US refresh plan cannot be read: {error}") from error
    if not isinstance(plan, dict) or not isinstance(plan.get("sources"), list) or not plan["sources"]:
        raise ValueError("US refresh plan requires a non-empty sources list")
    return plan, plan_path.parent


def _path(value: Any, base: Path) -> Path | None:
    if value in (None, ""):
        return None
    candidate = Path(str(value))
    return candidate if candidate.is_absolute() else base / candidate


def _failure_status(source_id: str, profile: str | None, error: BaseException, source_root: Path, previous_manifest: Path | None) -> dict[str, Any]:
    details = classify_failure(error)
    return {
        "source_id": source_id,
        "profile": profile,
        "status": "failed",
        "run_dir": str(source_root),
        "failure": {key: details[key] for key in ("failure_class", "retryable", "action")},
        "release_promoted": False,
        "release_preserved": True,
        "previous_valid": {
            "manifest": None if previous_manifest is None else str(previous_manifest),
            "available": bool(previous_manifest and previous_manifest.is_file()),
            "preserved_on_failure": True,
        },
        "public_surfaces": PUBLIC_SURFACES,
        "publication_gate": "blocked",
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _acquisition_summary(source_root: Path) -> dict[str, Any]:
    value = _read_json(source_root / "acquisition-metadata.json")
    if value is None:
        return {"state": "not-recorded"}
    if "acquisition_method" in value:
        return {
            "state": "captured",
            "method": value.get("acquisition_method"),
            "source_url": value.get("final_url") or value.get("requested_url"),
            "retrieved_at_utc": value.get("retrieved_at_utc"),
            "sha256": value.get("sha256"),
            "byte_size": value.get("byte_size"),
            "attempts": value.get("attempts", []),
        }
    roles = {}
    for role, metadata in sorted(value.items()):
        if not isinstance(metadata, dict):
            continue
        roles[role] = {
            "method": metadata.get("acquisition_method"),
            "source_url": metadata.get("final_url") or metadata.get("requested_url"),
            "retrieved_at_utc": metadata.get("retrieved_at_utc"),
            "sha256": metadata.get("sha256"),
            "byte_size": metadata.get("byte_size"),
            "attempts": metadata.get("attempts", []),
        }
    return {"state": "captured", "roles": roles}


def _generic_drift(manifest: dict[str, Any], previous_manifest: Path | None) -> list[str]:
    if previous_manifest is None:
        return []
    previous = _read_json(previous_manifest)
    if previous is None:
        return ["previous_manifest_unavailable"]
    alarms: list[str] = []
    if previous.get("source_profile") and manifest.get("source_profile") and previous["source_profile"] != manifest["source_profile"]:
        alarms.append("previous_source_profile_changed")
    if previous.get("schema_fingerprint") and manifest.get("schema_fingerprint") and previous["schema_fingerprint"] != manifest["schema_fingerprint"]:
        alarms.append("schema_fingerprint_changed")
    before = previous.get("input_rows")
    after = manifest.get("input_rows")
    if isinstance(before, int) and before and isinstance(after, int) and abs(after - before) > max(100, before // 10):
        alarms.append("input_row_count_changed_gt_10_percent")
    return alarms


def _summary(source_spec: dict[str, Any], result: dict[str, Any], source_root: Path, as_of_utc: str, previous_manifest: Path | None) -> dict[str, Any]:
    source_id = str(result.get("source_id") or ("us.aphis" if source_spec.get("source") == "aphis" else "us.fsis"))
    profile = source_spec.get("profile")
    manifest = result.get("manifest") if isinstance(result.get("manifest"), dict) else {}
    schedule = load_source_schedules()[source_id]
    retrieved = manifest.get("retrieved_at_utc")
    health = _read_json(Path(str(result.get("run_dir", source_root))) / "source-health.json")
    qa = _read_json(Path(str(result.get("run_dir", source_root))) / "qa.json") or {}
    counts = {key: manifest.get(key) for key in ("input_rows", "normalized_rows", "quarantined_rows")}
    reconciliation = manifest.get("row_reconciliation") if isinstance(manifest.get("row_reconciliation"), dict) else {}
    alarms = manifest.get("drift", {}).get("alarms", []) if isinstance(manifest.get("drift"), dict) else []
    alarms = sorted(set(alarms) | set(_generic_drift(manifest, previous_manifest)))
    if isinstance(qa.get("drift_alarms"), list):
        alarms = sorted(set(alarms) | set(qa["drift_alarms"]))
    status = str(result.get("status", "unknown"))
    return {
        "source_id": source_id,
        "profile": profile,
        "status": status,
        "run_dir": str(result.get("run_dir", source_root)),
        "freshness": freshness_for(schedule, retrieved, as_of_utc=as_of_utc),
        "acquisition": _acquisition_summary(source_root),
        "validation": {
            "state": "passed" if manifest and status in {"candidate-ready", "staged-restricted"} else "failed",
            "schema_fingerprint": manifest.get("schema_fingerprint"),
            "demographic_schema_fingerprint": manifest.get("demographic_schema_fingerprint"),
            "drift_alarms": alarms,
        },
        "row_reconciliation": reconciliation,
        "counts": counts,
        "quarantine": {
            "rows": manifest.get("quarantined_rows"),
            "reasons": manifest.get("anomaly_counts", {}),
        },
        "private_import": {
            "candidate_created": bool(result.get("candidate_created")),
            "candidate_imported": bool(result.get("candidate_import", {}).get("status") == "completed") if isinstance(result.get("candidate_import"), dict) else False,
            "ready_for_private_review": bool(result.get("candidate_created")) and not alarms,
            "publication_eligible_rows": 0,
        },
        "previous_valid": {
            "manifest": None if previous_manifest is None else str(previous_manifest),
            "available": bool(previous_manifest and previous_manifest.is_file()),
            "preserved_on_failure": True,
        },
        "release": {
            "release_state": manifest.get("release_state", "not-created"),
            "publication_state": result.get("publication_state", manifest.get("publication_state", "blocked")),
            "release_promoted": False,
            "public_surfaces": PUBLIC_SURFACES,
            "geocoding": manifest.get("geocoding", "disabled"),
        },
        "health_snapshot": None if health is None else {
            "health_state": health.get("health_state"),
            "private_validation": health.get("private_validation"),
            "public_exposure": health.get("public_exposure"),
        },
    }


def _run_one(spec: dict[str, Any], base: Path, root: Path, mode: str, retry: dict[str, Any], previous_manifest: Path | None, as_of_utc: str) -> dict[str, Any]:
    source = spec.get("source")
    if source not in {"fsis", "aphis"}:
        raise ValueError("each US refresh source must be fsis or aphis")
    source_root = root / ("fsis" if source == "fsis" else f"aphis-{spec.get('profile', 'unknown')}")
    source_root.mkdir(parents=True, exist_ok=True)
    try:
        if source == "fsis":
            directory = _path(spec.get("directory"), base)
            demographics = _path(spec.get("demographics"), base)
            fetch = bool(spec.get("fetch"))
            result = refresh_fsis(
                run_dir=source_root,
                directory_path=directory,
                demographics_path=demographics,
                fetch=fetch,
                source_url=spec.get("source_url") or None,
                retrieved_at_utc=spec.get("retrieved_at_utc"),
                effective_date=spec.get("effective_date"),
                mode=mode,
                terms_review_path=_path(spec.get("terms_review"), base),
                previous_manifest=previous_manifest,
                max_attempts=int(retry["max_attempts"]),
                retry_delay_seconds=float(retry["retry_delay_seconds"]),
                max_retry_delay_seconds=float(retry["max_retry_delay_seconds"]),
            )
        else:
            profile = str(spec.get("profile", ""))
            raw = _path(spec.get("raw"), base)
            result = refresh_aphis(
                run_dir=source_root,
                profile=profile,
                raw_path=raw,
                fetch=bool(spec.get("fetch")),
                source_url=spec.get("source_url") or None,
                terms_review_path=_path(spec.get("terms_review"), base),
                output_root=_path(spec.get("output_root"), base) or (root / "raw"),
                run_id=spec.get("run_id"),
                retrieved_at_utc=spec.get("retrieved_at_utc"),
                effective_date=spec.get("effective_date"),
                publication_date=spec.get("publication_date"),
                query_context=spec.get("query_context") if isinstance(spec.get("query_context"), dict) else {},
                max_attempts=int(retry["max_attempts"]),
                retry_delay_seconds=float(retry["retry_delay_seconds"]),
                max_retry_delay_seconds=float(retry["max_retry_delay_seconds"]),
            )
        return _summary(spec, result, source_root, as_of_utc, previous_manifest)
    except (OSError, ValueError, TypeError) as error:
        status = _failure_status("us.aphis" if source == "aphis" else "us.fsis", spec.get("profile"), error, source_root, previous_manifest)
        atomic_json(source_root / "run-status.json", status)
        atomic_json(source_root / "failure-report.json", status["failure"] | {"schema_version": "us-operator-failure-v1", "public_exposure": False, "release_promoted": False, "release_preserved": True})
        return status


def run_us_refresh(plan: dict[str, Any], *, plan_base: str | Path = ".", run_root: str | Path, mode: str = "dry-run", as_of_utc: str | None = None) -> dict[str, Any]:
    """Run each declared lane and write one aggregate, row-free operator report."""
    if mode not in {"dry-run", "handoff"}:
        raise ValueError("mode must be dry-run or handoff")
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=True)
    as_of = _as_of(as_of_utc)
    base = Path(plan_base)
    retry = {
        "max_attempts": int(plan.get("retry", {}).get("max_attempts", 3)),
        "retry_delay_seconds": float(plan.get("retry", {}).get("retry_delay_seconds", 1.0)),
        "max_retry_delay_seconds": float(plan.get("retry", {}).get("max_retry_delay_seconds", 30.0)),
    }
    sources = plan.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("US refresh plan requires a non-empty sources list")
    summaries: list[dict[str, Any]] = []
    for spec in sources:
        if not isinstance(spec, dict):
            raise ValueError("US refresh source entries must be objects")
        previous = _path(spec.get("previous_manifest"), base)
        summaries.append(_run_one(spec, base, root, mode, retry, previous, as_of))
    failed = [item for item in summaries if item.get("status") == "failed"]
    report = {
        "schema_version": REPORT_VERSION,
        "generated_at_utc": _now(),
        "as_of_utc": as_of,
        "mode": mode,
        "source_count": len(summaries),
        "sources": summaries,
        "overall_state": "attention-required" if failed or any(item.get("validation", {}).get("drift_alarms") for item in summaries) else "private-review-ready",
        "freshness_summary": {"current": sum(item.get("freshness", {}).get("state") == "current" for item in summaries), "stale": sum(item.get("freshness", {}).get("state") == "stale" for item in summaries), "unknown": sum(item.get("freshness", {}).get("state") in {"unknown", "not-run"} for item in summaries)},
        "release": {"release_state": "not-created", "release_promoted": False, "publication_gate": "blocked", "public_exposure": False, "public_surfaces": PUBLIC_SURFACES},
        "operator_actions": [
            "review acquisition metadata, schema/count drift, row reconciliation, and quarantine reasons",
            "confirm source-specific privacy and evidence review before any separate approval process",
            "retain the previous validated state when a refresh fails or remains unresolved",
        ],
    }
    atomic_json(root / "us-refresh-report.json", report)
    return report


def diagnose(run_root: str | Path, *, as_of_utc: str | None = None) -> dict[str, Any]:
    """Return safe diagnostics from an existing aggregate report only."""
    root = Path(run_root)
    report = _read_json(root / "us-refresh-report.json")
    if report is None:
        raise ValueError(f"US refresh report not found: {root / 'us-refresh-report.json'}")
    checks = []
    for item in report.get("sources", []):
        run_dir = Path(str(item.get("run_dir", "")))
        checks.append({
            "source_id": item.get("source_id"),
            "status": item.get("status"),
            "run_status_present": (run_dir / "run-status.json").is_file(),
            "manifest_present": (run_dir / "manifest.json").is_file(),
            "review_packet_present": (run_dir / "review-packet.json").is_file(),
            "previous_valid_available": item.get("previous_valid", {}).get("available", False),
            "public_exposure": item.get("release", {}).get("public_surfaces", PUBLIC_SURFACES),
        })
    result = {
        "schema_version": "us-operator-diagnostics-v1",
        "as_of_utc": _as_of(as_of_utc),
        "report_path": str(root / "us-refresh-report.json"),
        "overall_state": report.get("overall_state"),
        "checks": checks,
        "release": report.get("release", {"release_promoted": False, "publication_gate": "blocked", "public_exposure": False}),
        "safe_diagnostic_boundary": "aggregate metadata only; no source rows, raw values, coordinates, or restricted payloads",
    }
    atomic_json(root / "us-refresh-diagnostics.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, help="row-free JSON plan describing local captures or terms-reviewed fetches")
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("dry-run", "handoff"), default="dry-run")
    parser.add_argument("--as-of-utc")
    parser.add_argument("--diagnose", action="store_true", help="inspect an existing report without reading source rows")
    args = parser.parse_args()
    try:
        if args.diagnose:
            result = diagnose(args.run_root, as_of_utc=args.as_of_utc)
        else:
            if args.plan is None:
                raise ValueError("--plan is required unless --diagnose is used")
            plan, base = _load_plan(args.plan)
            result = run_us_refresh(plan, plan_base=base, run_root=args.run_root, mode=args.mode, as_of_utc=args.as_of_utc)
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("overall_state") in {"private-review-ready", "attention-required"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
