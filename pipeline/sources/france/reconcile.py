"""Build a row-free reconciliation for the two France DGAL section runs."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"expected JSON object row: {path}")
            rows.append(value)
    return rows


def _normalized(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("normalized")
    return value if isinstance(value, dict) else {}


def _count(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    values = Counter()
    for row in rows:
        value = _normalized(row).get(field)
        if isinstance(value, (list, tuple)):
            for item in value:
                values[str(item)] += 1
        else:
            values[str(value) if value is not None else "unknown"] += 1
    return dict(sorted(values.items()))


def _approval_keys(rows: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for row in rows:
        normalized = _normalized(row)
        value = normalized.get("establishment_id") or normalized.get("recognition_number")
        if isinstance(value, str) and value.strip():
            keys.add(value.strip())
    return keys


def _run_summary(run_dir: Path) -> tuple[dict[str, Any], set[str]]:
    manifest = _read_json(run_dir / "manifest.json")
    normalized = _rows(run_dir / "normalized" / "records.jsonl")
    quarantine_path = run_dir / "quarantined" / "records.jsonl"
    quarantined = _rows(quarantine_path) if quarantine_path.is_file() else []
    input_rows = int(manifest["input_rows"])
    normalized_rows = int(manifest["normalized_rows"])
    quarantined_rows = int(manifest["quarantined_rows"])
    if input_rows != normalized_rows + quarantined_rows:
        raise ValueError(f"partition mismatch in {run_dir}")
    quarantine_reasons = Counter()
    for item in quarantined:
        for reason in item.get("reasons", ()):  # quarantined envelope
            quarantine_reasons[str(reason)] += 1
    all_rows = normalized + [item.get("record", {}) for item in quarantined]
    summary = {
        "source_id": manifest["source_id"],
        "section": manifest["section"],
        "source_url": manifest["source_url"],
        "retrieved_at_utc": manifest["retrieved_at_utc"],
        "sha256": manifest["sha256"],
        "byte_size": manifest["byte_size"],
        "input_rows": input_rows,
        "normalized_rows": normalized_rows,
        "quarantined_rows": quarantined_rows,
        "partition_valid": True,
        "anomaly_counts": dict(sorted((str(k), int(v)) for k, v in manifest.get("anomaly_counts", {}).items())),
        "quarantine_reason_counts": dict(sorted(quarantine_reasons.items())),
        "identity_conflict_counts": manifest.get("identity_conflict_counts", {"state": "not-reported"}),
        "activity_category_observation_counts": _count(normalized, "activity_categories"),
        "address_state_counts": _count(all_rows, "address_state"),
        "coordinate_state_counts": _count(all_rows, "coordinate_state"),
        "coordinate_gate_counts": _count(all_rows, "coordinate_gate"),
        "privacy_gate_counts": _count(all_rows, "privacy_gate"),
        "publication_gate_counts": _count(all_rows, "publication_gate"),
        "provenance_and_release": {
            "rights_state": "file-specific-terms-pending-human-confirmation",
            "privacy_state": manifest.get("privacy_gate", "unknown"),
            "coordinate_state": manifest.get("coordinate_gate", "unknown"),
            "publication_state": manifest.get("publication_state", "unknown"),
            "release_state": manifest.get("release_state", "unknown"),
            "geocoding": "disabled",
        },
    }
    return summary, _approval_keys(normalized)


def reconcile(section_i_run: str | Path, section_ii_run: str | Path) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    approval_sets: dict[str, set[str]] = {}
    for run_dir in (Path(section_i_run), Path(section_ii_run)):
        summary, keys = _run_summary(run_dir)
        source_id = str(summary["source_id"])
        if source_id in approval_sets:
            raise ValueError(f"duplicate source run: {source_id}")
        summaries.append(summary)
        approval_sets[source_id] = keys
    expected = {"fr.dgal.section-i", "fr.dgal.section-ii"}
    if set(approval_sets) != expected:
        raise ValueError(f"expected exactly the two France DGAL source IDs, found {sorted(approval_sets)}")
    section_i_keys = approval_sets["fr.dgal.section-i"]
    section_ii_keys = approval_sets["fr.dgal.section-ii"]
    totals = {field: sum(int(summary[field]) for summary in summaries) for field in ("input_rows", "normalized_rows", "quarantined_rows")}
    return {
        "schema_version": "france-dgal-reconciliation-v1",
        "source_scopes": [summary["source_id"] for summary in summaries],
        "sources": summaries,
        "totals": {
            **totals,
            "partition_valid": totals["input_rows"] == totals["normalized_rows"] + totals["quarantined_rows"],
            "unique_facility_count": None,
            "identity_semantics": "source observations remain separate; approval-number overlap is a review signal, not an automatic merge",
        },
        "cross_section_overlap": {
            "shared_provisional_approval_number_count": len(section_i_keys & section_ii_keys),
            "section_i_distinct_provisional_approval_numbers": len(section_i_keys),
            "section_ii_distinct_provisional_approval_numbers": len(section_ii_keys),
            "identity_state": "unresolved-before-human-review",
            "merge_policy": "no automatic merge",
        },
        "coverage_limits": [
            "Current DGAL snapshots establish listed-at-retrieval observations only; missing later rows are not closure.",
            "The two files are separate scopes and are not summed as unique facilities.",
            "Address and coordinate values remain restricted source evidence; geocoding is disabled.",
            "File-specific terms, privacy/coordinate review, and project publication approval remain open.",
        ],
    }


def write_reconciliation(section_i_run: str | Path, section_ii_run: str | Path, output: str | Path) -> dict[str, Any]:
    report = reconcile(section_i_run, section_ii_run)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--section-i-run", type=Path, required=True)
    parser.add_argument("--section-ii-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = write_reconciliation(args.section_i_run, args.section_ii_run, args.output)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "ok", "output": str(args.output), "totals": report["totals"], "cross_section_overlap": report["cross_section_overlap"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
