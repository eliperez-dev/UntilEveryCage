"""Load, validate and rank country geocoding reconnaissance offline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pipeline.contracts.geocoding_profile import (
    build_recon_report,
    validate_profiles,
)
from pipeline.source_registry import load_registry


ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = Path(__file__).with_name("profiles.json")
STATUS_PATH = ROOT / "docs" / "source-status.json"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_profile_registry(path: Path = PROFILE_PATH, *, known_source_ids: set[str] | None = None) -> dict[str, Any]:
    payload = _load_json(path)
    validate_profiles(payload, known_source_ids=known_source_ids)
    return payload


def build_geocoding_recon(*, source_path: Path | None = None, status_path: Path | None = None, profile_path: Path | None = None) -> dict[str, Any]:
    source_registry = load_registry(source_path or (ROOT / "pipeline" / "source_registry.json"))
    status_registry = _load_json(status_path or STATUS_PATH)
    profile_registry = load_profile_registry(profile_path or PROFILE_PATH, known_source_ids={item["source_id"] for item in source_registry["sources"]})
    report = build_recon_report(source_registry, status_registry, profile_registry)
    rank_by_source = {item["source_id"]: item for item in report["ranked_backlog"]}
    summaries: list[dict[str, Any]] = []
    for profile in profile_registry["profiles"]:
        source_ids = list(profile["source_ids"])
        source_ranks = [rank_by_source[source_id] for source_id in source_ids]
        coordinate = [
            {
                "source_id": item["source_id"],
                "availability": item["availability"],
                "expected_coverage": item["expected_coverage"],
                "review_state": item["review_state"],
            }
            for item in profile["source_coordinate_evidence"]
        ]
        provider_ids = [item["provider_id"] for item in profile["providers"]]
        country_provider_ids = [provider_id for provider_id in provider_ids if not provider_id.startswith("global.")]
        burden = "high" if len(profile["unresolved_questions"]) >= 3 else "medium"
        summaries.append({
            "profile_id": profile["profile_id"],
            "country_code": profile["country_code"],
            "source_ids": source_ids,
            "best_source_score": max(item["score"] for item in source_ranks),
            "current_coordinate_evidence": coordinate,
            "expected_geocoding_coverage": profile["national_address_authority"]["availability"],
            "review_burden": burden,
            "provider_dependencies": country_provider_ids + ["global.nominatim-self-hosted", "global.pelias-self-hosted"],
            "recommended_implementation_order": 0,
            "publication_state": "blocked",
        })
    summaries.sort(key=lambda item: (-item["best_source_score"], item["profile_id"]))
    for index, summary in enumerate(summaries, start=1):
        summary["recommended_implementation_order"] = index
    report["profile_summaries"] = summaries
    report["platform_integration"] = {
        "source_registry": "pipeline/source_registry.json",
        "status_registry": "docs/source-status.json",
        "profile_registry": "pipeline/geocoding/profiles.json",
        "publication_effect": "none; profile validation and ranking do not alter source status, readiness, release approval or publication eligibility",
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write the row-free report JSON to this path")
    args = parser.parse_args()
    report = build_geocoding_recon()
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
