"""Repeatable private acquisition, drift QA, and FSA monthly handoff."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact

from .adapter import CONFIG, FsaApprovedEstablishmentsAdapter, _csv
from .handoff import write_private_monthly_handoff


class RefreshError(ValueError):
    """The source refresh cannot safely continue."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _header_fingerprint(raw: bytes) -> tuple[str, int]:
    headers, _, _ = _csv(raw)
    return hashlib.sha256(json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(), len(headers)


def _read_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        normalized = json.loads(line).get("normalized", {})
        value = normalized.get("establishment_id")
        if isinstance(value, str) and value:
            ids.add(value)
    return ids


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=list) + "\n", encoding="utf-8")


def _fetch(url: str, destination: Path) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "UntilEveryCage/uk-fsa-refresh"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
        effective = response.headers.get("Last-Modified") or "unknown"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    return raw, effective


def refresh_monthly(
    *,
    run_dir: str | Path,
    raw_path: str | Path | None = None,
    fetch: bool = False,
    source_url: str = CONFIG["source_url"],
    retrieved_at_utc: str | None = None,
    effective_date: str | None = None,
    code_version: str = CONFIG["adapter_version"],
    config_version: str = CONFIG["contract_version"],
    mode: str = "dry-run",
    previous_normalized: str | Path | None = None,
    bounded_sample: bool = False,
) -> dict[str, Any]:
    """Run a private refresh; ``mode=handoff`` also emits candidate-handoff-v1."""
    if mode not in {"dry-run", "handoff"}:
        raise RefreshError("mode must be dry-run or handoff")
    if fetch == (raw_path is not None):
        raise RefreshError("specify exactly one of raw_path or fetch")
    root = Path(run_dir)
    if fetch:
        raw, observed_effective = _fetch(source_url, root / "raw" / "source.csv")
        effective_date = effective_date or observed_effective
        input_path = root / "raw" / "source.csv"
    else:
        input_path = Path(raw_path)  # type: ignore[arg-type]
        raw = input_path.read_bytes()
    retrieved_at_utc = retrieved_at_utc or _utc_now()
    effective_date = effective_date or "unknown"
    adapter = FsaApprovedEstablishmentsAdapter()
    result = adapter.parse_bytes(raw)
    if result.profile != "monthly":
        raise RefreshError("UK refresh requires the monthly FSA profile")
    fingerprint, columns = _header_fingerprint(raw)
    alarms: list[str] = []
    expected = CONFIG.get("monthly_schema_fingerprint")
    if expected and fingerprint != expected and not bounded_sample:
        alarms.append("schema_fingerprint_changed")
    baseline = int(CONFIG["monthly_baseline_rows"])
    if not bounded_sample and abs(len(result.accepted) + len(result.quarantined) - baseline) > max(100, baseline // 10):
        alarms.append("input_row_count_changed")
    previous_ids = _read_ids(Path(previous_normalized)) if previous_normalized else set()
    current_ids = {
        r["normalized"].get("establishment_id")
        for r in result.accepted
    } | {
        item["record"]["normalized"].get("establishment_id")
        for item in result.quarantined
    }
    current_ids.discard(None)
    disappeared = len(previous_ids - current_ids) if previous_ids else 0
    artifact = SourceArtifact(
        source_url=source_url,
        retrieved_at_utc=retrieved_at_utc,
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        effective_date=effective_date,
        code_version=code_version,
        config_version=config_version,
        rights_caveat="metadata-indicated-open-government-licence-v3-pending-project-review",
        privacy_caveat="restricted-private-staging; privacy and coordinate review pending",
        coverage="England and Wales profile; other nations remain quarantined",
    )
    if alarms and mode == "handoff":
        raise RefreshError("refresh drift alarm blocks handoff: " + ", ".join(alarms))
    handoff = None
    if mode == "handoff":
        handoff = write_private_monthly_handoff(input_path, root / "handoff", artifact)
    report = {
        "source_url": source_url,
        "retrieved_at_utc": retrieved_at_utc,
        "effective_date": effective_date,
        "sha256": artifact.sha256,
        "byte_size": artifact.byte_size,
        "code_version": code_version,
        "config_version": config_version,
        "profile": result.profile,
        "schema_fingerprint": fingerprint,
        "column_count": columns,
        "input_rows": len(result.accepted) + len(result.quarantined),
        "normalized_rows": len(result.accepted),
        "quarantined_rows": len(result.quarantined),
        "coverage_counts": result.coverage_counts or {},
        "anomaly_counts": result.anomaly_counts or {},
        "drift_alarms": alarms,
        "disappeared_not_observed_count": disappeared,
        "disappearance_semantics": "not-observed; never inferred as closure",
        "geocoding": "disabled",
        "mode": mode,
        "release_state": "not-created",
        "publication_state": "private-candidate" if handoff else "not-staged",
    }
    _write_json(root / "refresh.json", report)
    return {"report": report, "handoff": handoff}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--raw", type=Path)
    source.add_argument("--fetch", action="store_true")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--source-url", default=CONFIG["source_url"])
    parser.add_argument("--retrieved-at-utc")
    parser.add_argument("--effective-date")
    parser.add_argument("--code-version", default=CONFIG["adapter_version"])
    parser.add_argument("--config-version", default=CONFIG["contract_version"])
    parser.add_argument("--mode", choices=("dry-run", "handoff"), default="dry-run")
    parser.add_argument("--previous-normalized", type=Path)
    parser.add_argument("--bounded-sample", action="store_true")
    args = parser.parse_args()
    result = refresh_monthly(
        run_dir=args.run_dir, raw_path=args.raw, fetch=args.fetch, source_url=args.source_url,
        retrieved_at_utc=args.retrieved_at_utc, effective_date=args.effective_date,
        code_version=args.code_version, config_version=args.config_version, mode=args.mode,
        previous_normalized=args.previous_normalized, bounded_sample=args.bounded_sample,
    )
    print(json.dumps(result["report"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
