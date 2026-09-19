"""Build a row-free, deterministic report of locally available real-data runs.

Raw and derived records are intentionally not read into the report.  This
tool inventories manifests and only uses aggregate counts already recorded by
authorized private acquisition jobs.  Missing counts are reported as unknown,
never as zero.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _json_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.json")) if root.exists() else []


def _artifacts(payload: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    if isinstance(payload.get("artifacts"), list):
        return [dict(item, _manifest=str(path)) for item in payload["artifacts"] if isinstance(item, dict)]
    if payload.get("source_id"):
        return [dict(payload, _manifest=str(path))]
    return []


def build_report(manifest_root: Path) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    for path in _json_files(manifest_root):
        try:
            artifacts.extend(_artifacts(json.loads(path.read_text(encoding="utf-8")), path))
        except (OSError, json.JSONDecodeError):
            continue
    sources = sorted({item["source_id"] for item in artifacts if item.get("source_id")})
    countries = sorted({item.get("country_code") or item.get("country") for item in artifacts if item.get("country_code") or item.get("country")})
    known_rows = 0
    row_sources = 0
    states: dict[str, int] = {}
    for item in artifacts:
        rows = item.get("input_rows", item.get("rows"))
        if isinstance(rows, int) and rows >= 0:
            known_rows += rows
            row_sources += 1
        state = item.get("capture_state") or item.get("capture_status") or ("row_artifact" if isinstance(rows, int) else "metadata_only")
        states[state] = states.get(state, 0) + 1
    return {
        "report_version": "real-data-corpus-v1",
        "privacy_boundary": "row-free manifest and aggregate report; raw/derived records remain private and ignored",
        "manifest_files": len(_json_files(manifest_root)),
        "artifact_entries": len(artifacts),
        "source_ids": sources,
        "country_values": countries,
        "known_input_rows": known_rows,
        "sources_with_known_row_counts": row_sources,
        "strata": {"country": countries, "source": sources, "category": "not available without private normalized rows", "accepted_quarantined": "not available without private run manifests", "coordinate_precision": "not available without private normalized rows", "identity_quality": "not available without private normalized rows"},
        "capture_states": dict(sorted(states.items())),
        "target_assessment": {"requested_min_rows": 25000, "requested_countries": 5, "requested_source_profiles": 8, "met": False, "reason": "available local manifests do not provide 25,000 counted real normalized records across five countries and eight profiles"},
        "limitations": ["metadata-only and route-only entries are not records", "unknown counts are not treated as zero", "no publication release or approval is created"],
    }


def canonical_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-root", type=Path, default=Path("data/manifests"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = canonical_bytes(build_report(args.manifest_root))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(payload).hexdigest()}))


if __name__ == "__main__":
    main()
