"""Private operational records for repeatable source refreshes.

This module owns the source-agnostic concerns around the adapter lifecycle:
schedule/freshness expectations, content-addressed raw evidence, append-only
run history, deterministic review packets, and bounded failure reporting.  It
does not acquire, transform, import, approve, or publish records.

All output is suitable for restricted operator use.  Health and review output
is deliberately aggregate and keeps release promotion disabled.
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
import time
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .acquisition import AcquisitionError
from .delta import compare_normalized_paths, compare_runs
from pipeline.contracts.source_lifecycle import atomic_bytes, atomic_json


OPERATIONS_SCHEMA_VERSION = "source-operations-v1"
RUN_CLASSIFICATIONS = {"changed", "unchanged", "failed", "review-required"}
_SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class SourceOperationsError(ValueError):
    """A source operations contract is malformed or inconsistent."""


class RetryExhaustedError(RuntimeError):
    """A bounded operation failed after its permitted attempts."""

    def __init__(self, message: str, *, attempts: list[dict[str, Any]], cause: BaseException) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.cause = cause


@dataclass(frozen=True)
class SourceSchedule:
    """Operational expectations for one source, separate from publication."""

    source_id: str
    cadence: str
    interval_hours: int | None
    stale_after_hours: int | None
    max_attempts: int = 1
    backoff_seconds: float = 0.0
    max_backoff_seconds: float = 30.0
    retention_class: str = "restricted-research-evidence"
    manual_fallback: str = "operator review required"

    def __post_init__(self) -> None:
        if not _SOURCE_ID.fullmatch(self.source_id):
            raise SourceOperationsError(f"invalid source_id: {self.source_id!r}")
        if not isinstance(self.cadence, str) or not self.cadence:
            raise SourceOperationsError(f"{self.source_id}.cadence must be non-empty")
        for name in ("interval_hours", "stale_after_hours"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or value <= 0):
                raise SourceOperationsError(f"{self.source_id}.{name} must be a positive integer or null")
        if self.stale_after_hours is not None and self.interval_hours is not None and self.stale_after_hours < self.interval_hours:
            raise SourceOperationsError(f"{self.source_id}.stale_after_hours must cover its interval")
        if not isinstance(self.max_attempts, int) or not 1 <= self.max_attempts <= 10:
            raise SourceOperationsError(f"{self.source_id}.max_attempts must be between 1 and 10")
        if self.backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise SourceOperationsError(f"{self.source_id} retry backoff cannot be negative")
        if self.backoff_seconds > self.max_backoff_seconds:
            raise SourceOperationsError(f"{self.source_id}.backoff_seconds exceeds max_backoff_seconds")

    @classmethod
    def from_mapping(cls, value: object, *, index: int = 0) -> "SourceSchedule":
        if not isinstance(value, dict):
            raise SourceOperationsError(f"schedules[{index}] must be an object")
        required = {"source_id", "cadence", "interval_hours", "stale_after_hours"}
        missing = sorted(required - value.keys())
        if missing:
            raise SourceOperationsError(f"schedules[{index}] missing fields: {', '.join(missing)}")
        try:
            return cls(
                source_id=str(value["source_id"]), cadence=str(value["cadence"]),
                interval_hours=value["interval_hours"], stale_after_hours=value["stale_after_hours"],
                max_attempts=value.get("max_attempts", 1),
                backoff_seconds=float(value.get("backoff_seconds", 0)),
                max_backoff_seconds=float(value.get("max_backoff_seconds", 30)),
                retention_class=str(value.get("retention_class", "restricted-research-evidence")),
                manual_fallback=str(value.get("manual_fallback", "operator review required")),
            )
        except (TypeError, ValueError) as error:
            raise SourceOperationsError(f"schedules[{index}] has invalid values") from error

    def as_mapping(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "cadence": self.cadence,
            "interval_hours": self.interval_hours,
            "stale_after_hours": self.stale_after_hours,
            "max_attempts": self.max_attempts,
            "backoff_seconds": self.backoff_seconds,
            "max_backoff_seconds": self.max_backoff_seconds,
            "retention_class": self.retention_class,
            "manual_fallback": self.manual_fallback,
        }


def load_source_schedules(path: str | Path | None = None, *, registry_path: str | Path | None = None) -> dict[str, SourceSchedule]:
    """Load and validate the complete operational schedule inventory."""
    config_path = Path(path) if path is not None else Path(__file__).parents[1] / "source_operations.json"
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SourceOperationsError(f"cannot read source schedules: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise SourceOperationsError("source operations config schema_version 1.0 is required")
    values = payload.get("schedules")
    if not isinstance(values, list) or not values:
        raise SourceOperationsError("source operations schedules must be a non-empty list")
    schedules: dict[str, SourceSchedule] = {}
    for index, value in enumerate(values):
        schedule = SourceSchedule.from_mapping(value, index=index)
        if schedule.source_id in schedules:
            raise SourceOperationsError(f"duplicate schedule for {schedule.source_id}")
        schedules[schedule.source_id] = schedule
    if registry_path is not None:
        from pipeline.source_registry import load_registry

        registry = load_registry(Path(registry_path))
        registry_ids = {item["source_id"] for item in registry["sources"]}
        missing = sorted(registry_ids - schedules.keys())
        extra = sorted(schedules.keys() - registry_ids)
        if extra:
            raise SourceOperationsError(f"schedule/source registry mismatch; missing={missing}, extra={extra}")
        # Reference-only registry entries still need an explicit health row.
        # An unknown cadence is not acquisition authorization.
        for source_id in missing:
            schedules[source_id] = SourceSchedule(
                source_id=source_id, cadence="unknown", interval_hours=None,
                stale_after_hours=None,
                manual_fallback="source-specific terms and an authorized acquisition route remain unresolved",
            )
    return schedules


def _parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as error:
        raise SourceOperationsError(f"{label} must be timezone-aware ISO-8601") from error
    if parsed.tzinfo is None:
        raise SourceOperationsError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def freshness_for(schedule: SourceSchedule, retrieved_at_utc: str | None, *, as_of_utc: str) -> dict[str, Any]:
    """Return deterministic freshness facts without calling a source."""
    as_of = _parse_time(as_of_utc, "as_of_utc")
    if not retrieved_at_utc:
        return {"state": "not-run", "retrieved_at_utc": None, "as_of_utc": as_of.isoformat().replace("+00:00", "Z"), "age_hours": None, "due": False}
    retrieved = _parse_time(retrieved_at_utc, "retrieved_at_utc")
    age_hours = round((as_of - retrieved).total_seconds() / 3600, 3)
    if age_hours < 0:
        state = "clock-skew"
    elif schedule.stale_after_hours is None:
        state = "unknown"
    else:
        state = "stale" if age_hours > schedule.stale_after_hours else "current"
    due = bool(schedule.interval_hours is not None and age_hours >= schedule.interval_hours)
    return {
        "state": state,
        "retrieved_at_utc": retrieved.isoformat().replace("+00:00", "Z"),
        "as_of_utc": as_of.isoformat().replace("+00:00", "Z"),
        "age_hours": age_hours,
        "due": due,
        "interval_hours": schedule.interval_hours,
        "stale_after_hours": schedule.stale_after_hours,
    }


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 0.0
    max_backoff_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 10:
            raise SourceOperationsError("retry max_attempts must be between 1 and 10")
        if self.backoff_seconds < 0 or self.max_backoff_seconds < 0 or self.backoff_seconds > self.max_backoff_seconds:
            raise SourceOperationsError("retry backoff values are invalid")


def classify_failure(error: BaseException) -> dict[str, Any]:
    """Classify failures into bounded, actionable operator categories."""
    if isinstance(error, RetryExhaustedError):
        return {"failure_class": "retry-exhausted", "retryable": False, "action": "inspect attempts and use the source manual fallback", "message": str(error)}
    if isinstance(error, AcquisitionError):
        return {
            "failure_class": getattr(error, "failure_class", "acquisition"),
            "retryable": bool(getattr(error, "retryable", False)),
            "action": getattr(error, "action", "inspect the private acquisition evidence and source terms"),
            "message": str(error),
        }
    if isinstance(error, (TimeoutError, socket.timeout)):
        return {"failure_class": "timeout", "retryable": True, "action": "retry within the source bound; use the manual capture route if it persists", "message": str(error)}
    if isinstance(error, urllib.error.HTTPError):
        retryable = error.code == 429 or 500 <= error.code <= 599
        return {"failure_class": f"http-{error.code}", "retryable": retryable, "action": "retry a bounded server/rate-limit failure" if retryable else "verify URL, authorization, and terms before another run", "message": str(error)}
    if isinstance(error, urllib.error.URLError):
        return {"failure_class": "network", "retryable": True, "action": "retry within the source bound; verify connectivity if it persists", "message": str(error)}
    if isinstance(error, (json.JSONDecodeError, UnicodeError)):
        return {"failure_class": "malformed-input", "retryable": False, "action": "retain the artifact and inspect schema/encoding before rerun", "message": str(error)}
    return {"failure_class": "validation-or-runtime", "retryable": False, "action": "inspect the private run report; correct the adapter or input before rerun", "message": str(error)}


def run_with_bounded_retries(
    operation: Callable[[], Any],
    policy: RetryPolicy,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Any, list[dict[str, Any]]]:
    """Run an operation with retryable failures only and a hard attempt bound."""
    attempts: list[dict[str, Any]] = []
    for number in range(1, policy.max_attempts + 1):
        try:
            return operation(), attempts + [{"attempt": number, "outcome": "success"}]
        except BaseException as error:
            details = classify_failure(error)
            attempt = {"attempt": number, "outcome": "failed", **details}
            attempts.append(attempt)
            if not details["retryable"] or number == policy.max_attempts:
                raise RetryExhaustedError(
                    f"operation failed after {number} bounded attempt(s): {details['failure_class']}",
                    attempts=attempts,
                    cause=error,
                ) from error
            delay = min(policy.max_backoff_seconds, policy.backoff_seconds * (2 ** (number - 1)))
            attempt["retry_delay_seconds"] = delay
            if delay:
                sleep(delay)
    raise AssertionError("retry loop did not return or raise")


def register_deduplicated_artifact(
    raw: bytes,
    operations_root: str | Path,
    metadata: dict[str, Any],
    *,
    artifact_name: str = "artifact",
) -> dict[str, Any]:
    """Store immutable bytes once while retaining each observation manifest."""
    root = Path(operations_root)
    digest = hashlib.sha256(raw).hexdigest()
    artifact_path = root / "raw" / "sha256" / digest[:2] / digest / artifact_name
    existed = artifact_path.exists()
    if existed and artifact_path.read_bytes() != raw:
        raise SourceOperationsError(f"content-addressed artifact collision: {digest}")
    if not existed:
        atomic_bytes(artifact_path, raw)
    observation = {
        **metadata,
        "operations_schema_version": OPERATIONS_SCHEMA_VERSION,
        "sha256": digest,
        "checksum_sha256": digest,
        "byte_size": len(raw),
        "artifact_name": artifact_name,
        "artifact_path": str(artifact_path),
        "artifact_state": "deduplicated" if existed else "stored",
        "retention": {
            "class": metadata.get("retention_class", "restricted-research-evidence"),
            "public_exposure": False,
            "review_required": True,
            "exceptional_removal_policy": "docs/ETHICS.md sections 2, 6, 8, and 9",
        },
    }
    observation_id = hashlib.sha256(json.dumps(observation, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    observation["observation_id"] = observation_id
    observation_path = root / "raw" / "observations" / f"{observation_id}.json"
    if not observation_path.exists():
        atomic_json(observation_path, observation)
    observation["observation_path"] = str(observation_path)
    return observation


def _safe_source_id(source_id: str) -> str:
    if not _SOURCE_ID.fullmatch(source_id):
        raise SourceOperationsError(f"invalid source_id: {source_id!r}")
    return source_id


def read_run_history(operations_root: str | Path, source_id: str) -> list[dict[str, Any]]:
    path = Path(operations_root) / "history" / f"{_safe_source_id(source_id)}.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise SourceOperationsError(f"invalid run history at {path}:{line_number}") from error
        if not isinstance(value, dict):
            raise SourceOperationsError(f"run history entry at {path}:{line_number} must be an object")
        rows.append(value)
    return rows


def append_run_history(operations_root: str | Path, source_id: str, entry: dict[str, Any]) -> Path:
    path = Path(operations_root) / "history" / f"{_safe_source_id(source_id)}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return path


def classify_run(*, failed: bool, review_required: bool, artifact_sha256: str | None, normalized_sha256: str | None, previous: dict[str, Any] | None) -> str:
    if failed:
        return "failed"
    if review_required:
        return "review-required"
    if previous and artifact_sha256 == previous.get("artifact_sha256") and normalized_sha256 == previous.get("normalized_sha256"):
        return "unchanged"
    return "changed"


def _file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provenance(manifest: dict[str, Any]) -> dict[str, Any]:
    keys = ("source_url", "retrieved_at_utc", "publication_date", "effective_date", "sha256", "checksum_sha256", "byte_size", "code_version", "config_version", "redirects")
    return {key: manifest[key] for key in keys if manifest.get(key) is not None}


def build_release_diff(previous_run_dir: str | Path | None, current_run_dir: str | Path, *, previous_normalized_path: str | Path | None = None, prior_eligible_release: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a row-free, deterministic diff for a human operator."""
    current = Path(current_run_dir)
    if previous_run_dir is None and previous_normalized_path is not None:
        normalized_delta = compare_normalized_paths(previous_normalized_path, current / "normalized" / "records.jsonl")
        return {"schema_version": "release-diff-v1", **normalized_delta, "release_promoted": False, "prior_eligible_release": prior_eligible_release}
    if previous_run_dir is None:
        return {
            "schema_version": "release-diff-v1", "status": "no-previous-validated-run",
            "release_promoted": False, "prior_eligible_release": prior_eligible_release,
            "counts": {"added": 0, "changed": 0, "not_observed": 0, "suppressed": 0},
        }
    delta = compare_runs(Path(previous_run_dir), current, prior_eligible_release=prior_eligible_release)
    return {"schema_version": "release-diff-v1", **delta, "release_promoted": False}


def build_review_packet(
    run_dir: str | Path,
    *,
    manifest: dict[str, Any] | None,
    status: dict[str, Any],
    previous_run_dir: str | Path | None = None,
    previous_normalized_path: str | Path | None = None,
    prior_eligible_release: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a stable operator packet containing no source rows or raw fields."""
    manifest = manifest or {}
    source_id = str(manifest.get("source_id") or status.get("source_id") or "unknown")
    qa_path = Path(run_dir) / "qa.json"
    qa: dict[str, Any] = {}
    if qa_path.exists():
        value = json.loads(qa_path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            qa = value
    failed = status.get("status") == "failed"
    review_required = bool(status.get("review_required") or manifest.get("review_required") or qa.get("drift_alarms") or manifest.get("quarantined_rows", 0))
    reasons: list[str] = []
    if failed:
        reasons.append("run failed; inspect failure report before rerun")
    if manifest.get("quarantined_rows", 0):
        reasons.append("quarantined rows require source-specific review")
    if qa.get("drift_alarms"):
        reasons.append("drift alarms require operator review")
    if status.get("publication_state") in {"human-gate-required", "terms-gate-blocked"}:
        reasons.append("publication remains behind the human/terms gate")
    if not reasons:
        reasons.append("confirm private evidence and release scope before any separate approval action")
    diff = build_release_diff(previous_run_dir, run_dir, previous_normalized_path=previous_normalized_path, prior_eligible_release=prior_eligible_release)
    counts = {
        key: manifest.get(key) for key in ("input_rows", "normalized_rows", "quarantined_rows")
    }
    qa_counts = {key: qa.get(key) for key in counts}
    blockers = status.get("review_blockers", {})
    return {
        "schema_version": "private-review-packet-v1",
        "source_id": source_id,
        "run_dir_digest": _file_sha256(Path(run_dir) / "manifest.json") or _file_sha256(Path(run_dir) / "run-manifest.json"),
        "run_id": status.get("run_id") or Path(run_dir).name,
        "classification": status.get("run_classification", "failed" if failed else "changed"),
        "review_required": review_required,
        "reasons": sorted(set(reasons)),
        "provenance": _provenance(manifest),
        "schema": {
            "adapter_version": manifest.get("adapter_version"),
            "schema_version": manifest.get("schema_version"),
            "schema_fingerprint": manifest.get("schema_fingerprint"),
            "schema_status": manifest.get("schema_status", "not-reported"),
        },
        "counts": {
            **counts,
            "reconciles": all(isinstance(value, int) and value >= 0 for value in counts.values()) and counts["input_rows"] == counts["normalized_rows"] + counts["quarantined_rows"],
            "qa_matches_manifest": counts == qa_counts,
        },
        "quarantine": {"rows": manifest.get("quarantined_rows"), "reasons": manifest.get("anomaly_counts", {})},
        "run": {
            "status": status.get("status"),
            "publication_state": status.get("publication_state", "unchanged"),
            "release_state": manifest.get("release_state", "not-created"),
            "input_rows": manifest.get("input_rows"),
            "normalized_rows": manifest.get("normalized_rows"),
            "quarantined_rows": manifest.get("quarantined_rows"),
            "drift_alarms": sorted(set(qa.get("drift_alarms", []))) if isinstance(qa.get("drift_alarms", []), list) else [],
        },
        "release_diff": diff,
        "gates": {
            "release_state": manifest.get("release_state", "not-created"),
            "publication_state": status.get("publication_state"),
            "release_promoted": status.get("release_promoted"),
            "public_surfaces": status.get("public_surfaces", {surface: False for surface in ("api", "map", "export", "cache", "history")}),
            "geocoding": manifest.get("geocoding", "disabled"),
        },
        "blockers": blockers,
        "prior_eligible_release": prior_eligible_release,
        "release_promotion_allowed": False,
        "public_exposure": False,
        "operator_actions": [
            "inspect private acquisition metadata and QA report",
            "resolve listed review reasons and source-specific blockers",
            "use a separate authorized release process; this packet cannot promote a release",
        ],
    }


def finalize_run_operations(
    operations_root: str | Path,
    run_dir: str | Path,
    *,
    manifest: dict[str, Any] | None,
    status: dict[str, Any],
    config: dict[str, Any] | None = None,
    previous_run_dir: str | Path | None = None,
    previous_normalized_path: str | Path | None = None,
    prior_eligible_release: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist the shared run ledger and deterministic operator artifacts."""
    config = config or {}
    manifest = manifest or {}
    source_id = str(manifest.get("source_id") or status.get("source_id") or config.get("source_id") or "unknown")
    history = read_run_history(operations_root, source_id)
    previous = history[-1] if history else None
    if previous_run_dir is None and previous and previous.get("run_dir"):
        candidate = Path(previous["run_dir"])
        if candidate.exists():
            previous_run_dir = candidate
    run_path = Path(run_dir)
    normalized_path = run_path / "normalized" / "records.jsonl"
    artifact_sha256 = manifest.get("sha256") or manifest.get("checksum_sha256") or config.get("checksum_sha256")
    normalized_sha256 = _file_sha256(normalized_path)
    failed = status.get("status") == "failed"
    review_required = bool(status.get("review_required") or manifest.get("review_required") or manifest.get("quarantined_rows", 0) or (run_path / "qa.json").exists() and json.loads((run_path / "qa.json").read_text(encoding="utf-8")).get("drift_alarms"))
    classification = classify_run(failed=failed, review_required=review_required, artifact_sha256=artifact_sha256, normalized_sha256=normalized_sha256, previous=previous)
    status.update({
        "source_id": source_id,
        "run_classification": classification,
        "review_required": review_required,
        "artifact_state": "unchanged" if previous and artifact_sha256 == previous.get("artifact_sha256") else "changed",
        "release_preserved": True,
        "release_promoted": False,
    })
    status["review_blockers"] = config.get("review_blockers", {})
    packet = build_review_packet(run_path, manifest=manifest, status=status, previous_run_dir=previous_run_dir, previous_normalized_path=previous_normalized_path, prior_eligible_release=prior_eligible_release)
    packet_path = run_path / "review-packet.json"
    diff_path = run_path / "release-diff.json"
    atomic_json(packet_path, packet)
    atomic_json(diff_path, packet["release_diff"])
    entry = {
        "schema_version": "run-history-v1",
        "source_id": source_id,
        "run_id": status.get("run_id") or run_path.name,
        "run_dir": str(run_path),
        "run_status": status.get("status"),
        "run_classification": classification,
        "review_required": review_required,
        "release_promoted": False,
        "release_preserved": True,
        "artifact_sha256": artifact_sha256,
        "normalized_sha256": normalized_sha256,
        "retrieved_at_utc": manifest.get("retrieved_at_utc") or config.get("retrieved_at_utc"),
        "input_rows": manifest.get("input_rows"),
        "normalized_rows": manifest.get("normalized_rows"),
        "quarantined_rows": manifest.get("quarantined_rows"),
        # Keep the append-only aggregate ledger row-free.  The detailed error
        # stays in the restricted run-status/failure report instead.
        "error": "run failed; see restricted failure-report.json" if failed else None,
        "failure_class": status.get("failure_class") if failed else None,
    }
    history_path = append_run_history(operations_root, source_id, entry)
    status.update({"history_path": str(history_path), "review_packet_path": str(packet_path), "release_diff_path": str(diff_path)})
    if failed:
        status["failure_report"] = failure_report(source_id=source_id, run_id=entry["run_id"], error=status.get("error", "run failed"), attempts=status.get("attempts", []), manual_fallback=config.get("manual_fallback"))
        atomic_json(run_path / "failure-report.json", status["failure_report"])
        if config.get("notification_root"):
            status["notification_path"] = str(write_failure_notification(status["failure_report"], config["notification_root"]))
    return status


def failure_report(*, source_id: str, run_id: str, error: BaseException | str, attempts: Iterable[dict[str, Any]] = (), manual_fallback: str | None = None) -> dict[str, Any]:
    details = classify_failure(error) if isinstance(error, BaseException) else {"failure_class": "run-failed", "retryable": False, "action": "inspect the private run and rerun after correction", "message": str(error)}
    # Exception messages can accidentally echo a source value.  The report is
    # useful to an operator without copying that payload into an aggregate
    # notification or append-only history record.
    details = {key: value for key, value in details.items() if key != "message"}
    safe_attempts = [
        {key: value for key, value in attempt.items() if key != "message"}
        for attempt in attempts
    ]
    report = {
        "schema_version": "failure-report-v1", "source_id": source_id, "run_id": run_id,
        "failure": details, "attempts": safe_attempts, "public_exposure": False,
        "release_promoted": False, "release_preserved": True,
        "operator_action": manual_fallback or details["action"],
    }
    return report


def write_failure_notification(report: dict[str, Any], notifications_root: str | Path) -> Path:
    """Write a local, append-only notification hook payload; no service is required."""
    source_id = _safe_source_id(str(report.get("source_id", "unknown")))
    path = Path(notifications_root) / f"{source_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return path


def build_source_health_index(
    operations_root: str | Path,
    *,
    schedules_path: str | Path | None = None,
    registry_path: str | Path | None = None,
    as_of_utc: str,
) -> dict[str, Any]:
    """Build a deterministic aggregate health index for every registered source."""
    schedules = load_source_schedules(schedules_path, registry_path=registry_path)
    sources: list[dict[str, Any]] = []
    for source_id in sorted(schedules):
        schedule = schedules[source_id]
        history = read_run_history(operations_root, source_id)
        latest = history[-1] if history else None
        last_validated = next((item for item in reversed(history) if item.get("run_status") != "failed"), None)
        freshness = freshness_for(schedule, last_validated.get("retrieved_at_utc") if last_validated else None, as_of_utc=as_of_utc)
        if latest is None:
            health_state = "not-run"
        elif latest.get("run_status") == "failed":
            health_state = "failed"
        elif latest.get("run_classification") == "review-required":
            health_state = "review-required"
        elif freshness["state"] == "stale":
            health_state = "degraded"
        else:
            health_state = "private-validated"
        sources.append({
            "source_id": source_id,
            "schedule": schedule.as_mapping(),
            "health_state": health_state,
            "private_validation": latest is not None and latest.get("run_status") != "failed",
            "public_exposure": False,
            "publication_eligibility": "blocked",
            "freshness": freshness,
            "last_run": None if latest is None else {
                key: latest.get(key) for key in ("run_id", "run_dir", "run_status", "run_classification", "review_required", "artifact_sha256", "normalized_sha256", "input_rows", "normalized_rows", "quarantined_rows", "failure_class")
            },
            "last_validated_run": None if last_validated is None else {
                key: last_validated.get(key) for key in ("run_id", "run_dir", "run_status", "run_classification", "artifact_sha256", "normalized_sha256", "retrieved_at_utc")
            },
            "run_count": len(history),
        })
    return {
        "schema_version": "source-health-index-v1",
        "as_of_utc": _parse_time(as_of_utc, "as_of_utc").isoformat().replace("+00:00", "Z"),
        "private_validation": True,
        "public_exposure": False,
        "publication_eligibility": "blocked",
        "sources": sources,
    }


__all__ = [
    "OPERATIONS_SCHEMA_VERSION", "RetryExhaustedError", "RetryPolicy", "SourceOperationsError", "SourceSchedule",
    "append_run_history", "build_release_diff", "build_review_packet", "build_source_health_index", "classify_failure",
    "classify_run", "failure_report", "finalize_run_operations", "freshness_for", "load_source_schedules",
    "read_run_history", "register_deduplicated_artifact", "run_with_bounded_retries", "write_failure_notification",
]
