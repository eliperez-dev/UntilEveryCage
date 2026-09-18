"""Private Wave 2 APHIS accountability-graph demonstration.

The input is a directory of operator-saved APHIS CSV exports.  The exports
are never treated as a facility master and are never copied into Git.  This
module keeps the full parsed rows in ignored private staging, then builds a
row-bearing private identity graph from exact APHIS certificate/customer IDs.
Names, addresses, and coordinates are not identity evidence.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl

from pipeline.sources.us.aphis.adapter import AphisPublicSearchAdapter
from pipeline.sources.us.aphis.acquire import profile_url
from pipeline.sources.us.accountability.current_identity import (
    build_current_identity_graph,
    write_current_identity_graph,
)


WAVE_VERSION = "us-aphis-accountability-wave2-v1"
SOURCE_ID = "us.aphis"
PROFILE_RETRIEVED_AT = {
    "annual_reports": "2026-09-18T17:54:55Z",
    "registrations": "2026-09-18T18:06:26Z",
    "inspections": "2026-09-18T18:17:14Z",
}
PUBLICATION = {
    "storage_state": "private",
    "publication_status": "not_eligible",
    "public_exposure": False,
    "release_state": "not-created",
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fingerprint(identifier_type: str, value: str) -> str:
    return hashlib.sha256(f"{identifier_type}|{value}".encode("utf-8")).hexdigest()[:12]


def _jsonl(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _classify(path: Path, adapter: AphisPublicSearchAdapter) -> tuple[str, dict[str, Any]]:
    raw = path.read_bytes()
    result = adapter.parse_bytes(raw)
    return result["profile"], {
        "path_private": str(path.resolve()),
        "artifact": path.name,
        "sha256": _sha256(raw),
        "byte_size": len(raw),
        "input_rows": result["input_rows"],
        "accepted_rows": len(result["accepted"]),
        "quarantined_rows": len(result["quarantined"]),
        "schema_fingerprint": result["schema_fingerprint"],
        "profile": result["profile"],
    }


def discover_exports(input_root: str | Path) -> tuple[dict[str, list[Path]], list[dict[str, str]]]:
    """Discover only operator-saved ``ExportData*.csv`` files.

    A malformed export is recorded as an input failure rather than silently
    becoming a zero-row observation.  The run may continue when another
    validated page set supplies the requested profile, but the failure remains
    visible in the row-free report.
    """
    root = Path(input_root)
    adapter = AphisPublicSearchAdapter()
    paths: dict[str, list[Path]] = defaultdict(list)
    failures: list[dict[str, str]] = []
    for path in sorted(root.glob("ExportData*.csv"), key=lambda value: value.name):
        try:
            profile, _ = _classify(path, adapter)
        except (OSError, ValueError) as error:
            failures.append({"artifact": path.name, "failure_class": type(error).__name__})
            continue
        if profile in {"annual_reports", "registrations", "inspections"}:
            paths[profile].append(path)
    return dict(paths), failures


def _load_profile(paths: list[Path], profile: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    adapter = AphisPublicSearchAdapter()
    records: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    for path in sorted(paths, key=lambda value: value.name):
        raw = path.read_bytes()
        result = adapter.parse_bytes(raw)
        if result["profile"] != profile:
            raise ValueError(f"{path.name} parsed as {result['profile']}, expected {profile}")
        _, metadata = _classify(path, adapter)
        artifacts.append(metadata)
        records.extend(result["accepted"])
        quarantined.extend(result["quarantined"])
    return records, quarantined, artifacts


def _ambiguous_keys(records: Iterable[Mapping[str, Any]]) -> tuple[set[str], dict[str, int]]:
    counts: Counter[str] = Counter(str(record["source_record_key"]) for record in records)
    return {key for key, count in counts.items() if count > 1}, dict(sorted(counts.items()))


def _profile_manifest(profile: str, records: list[dict[str, Any]], quarantined: list[dict[str, Any]], artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate = "\n".join(
        f"{item['artifact']}|{item['sha256']}|{item['byte_size']}|{item['input_rows']}"
        for item in sorted(artifacts, key=lambda value: value["artifact"])
    ).encode("utf-8")
    ambiguous, key_counts = _ambiguous_keys(records)
    return {
        "source_id": SOURCE_ID,
        "profile": profile,
        "source_url": profile_url(profile),
        "retrieved_at_utc": PROFILE_RETRIEVED_AT[profile],
        "page_count": len(artifacts),
        "input_rows": sum(int(item["input_rows"]) for item in artifacts),
        "accepted_rows": len(records),
        "adapter_quarantined_rows": len(quarantined),
        "distinct_source_observation_keys": len(key_counts),
        "duplicate_source_observation_keys": len(ambiguous),
        "duplicate_page_rows": sum(count - 1 for count in key_counts.values() if count > 1),
        "aggregate_artifact_sha256": _sha256(aggregate),
        "artifacts": artifacts,
    }


def _safe_example(candidate: Mapping[str, Any]) -> dict[str, Any]:
    identifiers = candidate.get("matched_identifiers") or {}
    return {
        "candidate_id": candidate.get("candidate_id"),
        "relationship_type": candidate.get("relationship_type"),
        "profiles": [candidate.get("left", {}).get("profile"), candidate.get("right", {}).get("profile")],
        "matched_identifier_types": sorted(identifiers),
        "identifier_fingerprints": {
            key: _fingerprint(key, str(value)) for key, value in sorted(identifiers.items())
        },
        "confidence": candidate.get("confidence"),
        "review_state": candidate.get("review_state"),
        "assertion_status": candidate.get("assertion_status"),
        "publication_status": candidate.get("publication", {}).get("publication_status"),
    }


def _bounded_query(
    candidates: list[Mapping[str, Any]],
    identifiers: Mapping[str, str],
    *,
    right_profile: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    matches = [
        candidate for candidate in candidates
        if (right_profile is None or candidate.get("right", {}).get("profile") == right_profile)
        if all((candidate.get("matched_identifiers") or {}).get(key) == value for key, value in identifiers.items())
    ]
    matches.sort(key=lambda candidate: str(candidate.get("candidate_id")))
    return {
        "requested_identifier_types": sorted(identifiers),
        "result_count_bounded": min(len(matches), limit),
        "limit": limit,
        "results": [_safe_example(candidate) for candidate in matches[:limit]],
    }


def _verify_controls() -> dict[str, bool]:
    fixture_path = Path(__file__).with_name("fixtures") / "current_identity.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    weak = copy.deepcopy(payload)
    report = weak["aphis"]["annual_reports"][0]
    report["normalized"]["certificate_number"] = ""
    report["normalized"]["customer_number"] = ""
    report["normalized"]["account_name"] = "Synthetic Laboratory Annex"
    report["source_values"]["Account Name"] = "Synthetic Laboratory Annex"
    weak_graph = build_current_identity_graph(
        aphis_records=weak["aphis"], fsis_records=weak["fsis"],
        fsis_observations=weak["fsis_observations"], provenance=weak["provenance"],
    )
    weak_edges = [item for item in weak_graph["candidates"] if item["right"]["profile"] == "annual_reports"]

    suppressed = copy.deepcopy(payload)
    suppressed["aphis"]["inspections"][0]["normalized"]["privacy_gate"] = "suppressed"
    suppressed_graph = build_current_identity_graph(
        aphis_records=suppressed["aphis"], fsis_records=suppressed["fsis"],
        fsis_observations=suppressed["fsis_observations"], provenance=suppressed["provenance"],
    )
    suppressed_edges = [item for item in suppressed_graph["candidates"] if item["right"]["profile"] == "inspections"]
    suppressed_queue = [item for item in suppressed_graph["quarantined"] if item["right"]["profile"] == "inspections"]
    return {
        "weak_name_address_similarity_not_asserted": not any(item.get("match_method") == "alternate_name_address_exact" for item in weak_edges),
        "suppressed_rows_do_not_enter_candidates": not suppressed_edges and any(item.get("quarantine_reason") == "suppressed_or_restricted" for item in suppressed_queue),
        "all_candidate_publication_is_blocked": all(item.get("publication", {}).get("publication_status") == "not_eligible" for item in weak_graph["candidates"]),
    }


def run_wave2(*, input_root: str | Path, run_dir: str | Path) -> dict[str, Any]:
    """Run the bounded private proof against saved APHIS exports."""
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths, failures = discover_exports(input_root)
    if any(not paths.get(profile) for profile in ("registrations", "annual_reports", "inspections")):
        raise ValueError("input root must contain at least one validated export for each APHIS profile")

    records_by_profile: dict[str, list[dict[str, Any]]] = {}
    quarantined_by_profile: dict[str, list[dict[str, Any]]] = {}
    profile_manifests: dict[str, dict[str, Any]] = {}
    all_artifacts: list[dict[str, Any]] = []
    graph_records: dict[str, list[dict[str, Any]]] = {}
    projection_quarantine: list[dict[str, Any]] = []
    for profile in ("registrations", "annual_reports", "inspections"):
        records, quarantined, artifacts = _load_profile(paths[profile], profile)
        records_by_profile[profile] = records
        quarantined_by_profile[profile] = quarantined
        profile_manifests[profile] = _profile_manifest(profile, records, quarantined, artifacts)
        all_artifacts.extend(artifacts)
        ambiguous, _ = _ambiguous_keys(records)
        graph_records[profile] = []
        for record in sorted(records, key=lambda value: (str(value["source_record_key"]), int(value.get("source_row") or 0))):
            if record["source_record_key"] in ambiguous:
                projection_quarantine.append({
                    "profile": profile,
                    "reason": "duplicate_source_observation_key_across_export_pages",
                    "source_record_key": record["source_record_key"],
                })
            elif not any(existing["source_record_key"] == record["source_record_key"] for existing in graph_records[profile]):
                graph_records[profile].append(record)

        atomic_jsonl(root / "private-rows" / f"{profile}-accepted.jsonl", _jsonl(records))
        atomic_jsonl(root / "private-rows" / f"{profile}-adapter-quarantine.jsonl", _jsonl(quarantined))
    atomic_jsonl(root / "private-rows" / "graph-projection-quarantine.jsonl", projection_quarantine)

    provenance = {
        (SOURCE_ID, profile): {
            "artifact_sha256": profile_manifests[profile]["aggregate_artifact_sha256"],
            "source_url": profile_manifests[profile]["source_url"],
            "retrieved_at_utc": profile_manifests[profile]["retrieved_at_utc"],
        }
        for profile in profile_manifests
    }
    graph = build_current_identity_graph(
        aphis_records=graph_records,
        fsis_records=(),
        fsis_observations=(),
        provenance=provenance,
    )
    first = write_current_identity_graph(root / "identity-graph", graph)
    second = write_current_identity_graph(root / "identity-graph-rerun", graph)

    candidates = list(graph["candidates"])
    by_profile: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_profile[str(candidate.get("right", {}).get("profile"))].append(candidate)
    examples: list[dict[str, Any]] = []
    bounded_queries: list[dict[str, Any]] = []
    for profile in ("annual_reports", "inspections"):
        pool = sorted(by_profile[profile], key=lambda item: str(item.get("candidate_id")))
        if not pool:
            continue
        selected = max(pool, key=lambda item: (len(item.get("matched_identifiers") or {}), str(item.get("candidate_id"))))
        examples.append(_safe_example(selected))
        bounded_queries.append({
            "name": f"exact_{profile}_representative",
            "relationship_profile": profile,
            **_bounded_query(
                candidates,
                selected.get("matched_identifiers") or {},
                right_profile=profile,
            ),
        })

    anomaly_counts = Counter(item.get("reason") for item in projection_quarantine)
    anomaly_counts.update(reason for item in graph["quarantined"] for reason in [item.get("quarantine_reason") or item.get("reason")])
    report = {
        "schema_version": WAVE_VERSION,
        "captured_for": "private/test-only",
        "input_root_private": str(Path(input_root).resolve()),
        "input_failures": failures,
        "profiles": profile_manifests,
        "graph_projection": {
            "source_rows_used": {profile: len(rows) for profile, rows in graph_records.items()},
            "source_rows_excluded_from_graph_projection": len(projection_quarantine),
            "projection_exclusion_reasons": dict(sorted(anomaly_counts.items())),
            "entities": len(graph["entities"]),
            "candidate_relationships": len(graph["candidates"]),
            "quarantined_relationships": len(graph["quarantined"]) + len(projection_quarantine),
            "candidate_relationship_types": graph["manifest"]["candidate_relationship_types"],
            "match_methods": graph["manifest"]["match_methods"],
            "review_state": "review_required",
            "confidence_states": dict(sorted(Counter(str(item.get("confidence")) for item in candidates).items())),
            "matched_identifier_types": dict(sorted(Counter(key for item in candidates for key in (item.get("matched_identifiers") or {})).items())),
        },
        "representative_examples": examples,
        "bounded_queries": bounded_queries,
        "controls": {
            **_verify_controls(),
            "rerun_idempotency_key_equal": first["idempotency_key"] == second["idempotency_key"],
            "public_surfaces": {"api": False, "map": False, "export": False, "cache": False, "history": False},
            **PUBLICATION,
        },
        "coverage_boundary": {
            "inspections": "21 saved Research Facility export pages / 2,100 rows from the displayed 15,726-row view; remaining rows were not acquired in this proof",
            "annual_reports": "FY2025 annual-report export pages only",
            "registrations": "saved registration export pages, including separate pagination/state evidence pages; duplicate source keys are not silently merged",
            "not_observed_semantics": "absence from a page or subset is not closure, non-use, or non-coverage",
        },
        "limitations": [
            "Raw, parsed, normalized, and quarantine rows remain in private ignored staging only.",
            "Exact APHIS identifiers link source observations; they do not establish ownership, operation, approval, or project publication.",
            "Addresses and names remain private source evidence and are not included in this aggregate report.",
            "Source terms, privacy review, factual review, project approval, and release publication remain separate gates.",
        ],
        "publication": PUBLICATION,
        "test_only": True,
    }
    atomic_json(root / "input-manifest.json", {"schema_version": f"{WAVE_VERSION}-inputs", "profiles": profile_manifests, "input_failures": failures})
    atomic_json(root / "wave2-report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run_wave2(input_root=args.input_root, run_dir=args.run_dir)
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "completed", "run_dir": str(args.run_dir), "candidate_relationships": report["graph_projection"]["candidate_relationships"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
