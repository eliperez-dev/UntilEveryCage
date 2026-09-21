"""Compare two explicitly selected reviewed-demo source summaries.

This is a planning/diagnostic helper for the generic demonstration workflow.
It never chooses a source, creates a release, starts a database, or emits rows.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.scripts.diagnostics.data_readiness_report import DataReadinessError


FORBIDDEN_KEYS = frozenset({"rows", "records", "source_values", "raw_fields", "address", "coordinates", "latitude", "longitude"})


def _safe(value: Any, path: str = "comparison") -> None:
    if isinstance(value, Mapping):
        leaked = sorted(FORBIDDEN_KEYS.intersection(value))
        if leaked:
            raise DataReadinessError(f"row payload key in {path}: {leaked}")
        for key, child in value.items():
            _safe(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _safe(child, f"{path}[{index}]")


def _source_summary(report: Mapping[str, Any], source_id: str) -> dict[str, Any]:
    observations = report.get("observations")
    if not isinstance(observations, Mapping):
        raise DataReadinessError("readiness report has no observations section")
    aliases = {
        "fr.dgal.union": "france",
        "fr.dgal.section-i": "france",
        "fr.dgal.section-ii": "france",
        "dk.smiley": "denmark",
        "us.fsis": "fsis",
        "it.853-2004": "italy",
    }
    key = aliases.get(source_id, source_id.split(".")[-1])
    value = observations.get(key)
    if not isinstance(value, Mapping):
        raise DataReadinessError(f"source is not present in readiness report: {source_id}")
    result = {"source_id": source_id, "observation_unit": value.get("observation_unit")}
    if "count" in value:
        result["observation_count"] = value["count"]
    if "section_i" in value:
        result["section_i_count"] = value["section_i"]
        result["section_ii_count"] = value["section_ii"]
    if source_id == "dk.smiley":
        result.update({
            "identity_state": value.get("identity_state"),
            "facility_identity_count": value.get("facility_identity_count"),
            "coordinate_state": report["coordinate_states"]["denmark"]["display_state"],
        })
    else:
        candidates = report.get("candidates", {}).get("by_source", {})
        coordinates = report.get("coordinate_states", {})
        result.update({
            "candidate_count": candidates.get(source_id),
            "numeric_coordinate_count": coordinates.get("numeric_coordinate", {}).get("by_source", {}).get(source_id),
            "publication_state": report.get("publication", {}).get("publication_eligibility"),
        })
    return result


def compare_sources(report: Mapping[str, Any], left_source_id: str, right_source_id: str) -> dict[str, Any]:
    """Compare exactly two caller-selected sources; never infer a preferred one."""
    if not left_source_id or not right_source_id:
        raise DataReadinessError("left_source_id and right_source_id are required")
    if left_source_id == right_source_id:
        raise DataReadinessError("comparison sources must be distinct")
    result = {
        "schema_version": "reviewed-demo-source-comparison-v1",
        "selection": {
            "mode": "explicit-source-pair",
            "left_source_id": left_source_id,
            "right_source_id": right_source_id,
            "auto_choice": False,
            "operator_must_select_release_source": True,
        },
        "sources": [
            _source_summary(report, left_source_id),
            _source_summary(report, right_source_id),
        ],
        "publication": {
            "release_created": False,
            "release_promoted": False,
            "public_api_rows": 0,
            "state": "blocked_pending_human_review",
        },
        "limitations": [
            "This compares aggregate readiness only; it is not a source-quality ranking.",
            "No source is recommended or automatically selected for a demonstration.",
            "Terms, privacy/location, coordinate precision, identity, and project approval remain human gates.",
        ],
    }
    _safe(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--left-source", required=True)
    parser.add_argument("--right-source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    comparison = compare_sources(report, args.left_source, args.right_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(comparison, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output), "auto_choice": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
