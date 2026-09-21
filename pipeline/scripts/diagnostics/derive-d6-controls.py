"""Derive aggregate D6 graph controls from restricted private handoffs.

The default input is ``D:\\UntilEveryCage-private\\d6-graph-mvp``.  This
command never copies row payloads into the repository.  It reads only private
JSONL handoffs, derives source-asserted positive controls and invariant
negative controls, and writes a row-free manifest to the requested output.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow the documented direct-script invocation from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from pipeline.common.d6_source_controls import (
    CONTROL_VERSION,
    PRIVATE_STAGING_ROOT,
    derive_known_connection_controls,
    write_control_manifest,
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def collect_private_controls(root: Path) -> dict[str, Any]:
    graph_candidates: dict[str, list[dict[str, Any]]] = {}
    evidence_rows: dict[str, list[dict[str, Any]]] = {}
    facility_records: dict[str, list[dict[str, Any]]] = {}
    handoffs = 0
    for manifest_path in sorted(root.rglob("manifest.json")):
        try:
            manifest = _json(manifest_path)
        except (OSError, json.JSONDecodeError):
            continue
        records_path = manifest_path.parent / "records.jsonl"
        if not records_path.is_file():
            records_path = manifest_path.parent / "graph-candidates.jsonl"
        if not records_path.is_file():
            continue
        source_id = str(manifest.get("source_id") or "")
        if not source_id:
            continue
        rows: list[dict[str, Any]] = []
        try:
            rows = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, json.JSONDecodeError):
            continue
        handoffs += 1
        if manifest.get("entity_scope") == "evidence_event" or manifest.get("source_kind") == "evidence_event":
            evidence_rows.setdefault(source_id, []).extend(row for row in rows if isinstance(row, dict))
        elif any(isinstance(row, dict) and isinstance(row.get("relationships"), list) for row in rows):
            graph_candidates.setdefault(source_id, []).extend(row for row in rows if isinstance(row, dict))
        else:
            facility_records.setdefault(source_id, []).extend(row for row in rows if isinstance(row, dict))
    controls = derive_known_connection_controls(
        graph_candidates=graph_candidates,
        evidence_rows=evidence_rows,
        facility_records=facility_records,
    )
    controls["control_origin"] = "authorized retained private handoffs"
    controls["private_handoffs_scanned"] = handoffs
    controls["private_sources_scanned"] = sorted(set(graph_candidates) | set(evidence_rows) | set(facility_records))
    controls["row_payloads_in_report"] = False
    controls["schema_version"] = CONTROL_VERSION
    return controls


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", type=Path, default=PRIVATE_STAGING_ROOT)
    parser.add_argument("--output", type=Path, default=Path("data/manifests/d6-real-connection-controls.json"))
    args = parser.parse_args()
    manifest = collect_private_controls(args.private_root)
    write_control_manifest(args.output, manifest)
    print(json.dumps({
        "status": "completed",
        "private_root": str(args.private_root.resolve()),
        "output": str(args.output.resolve()),
        "positive_controls": manifest["positive_controls"]["count"],
        "negative_controls": manifest["negative_controls"]["count"],
        "row_payloads_in_report": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
