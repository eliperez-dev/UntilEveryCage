"""Convert a bounded legacy V1 corpus into a private V2-shaped rehearsal.

This is a migration rehearsal, not an acquisition adapter. It references the
existing V1 snapshots as raw inputs, preserves each row under source_values in
ignored staging, and marks every normalized record as legacy/private. No
release is promoted and the row-free report never contains record payloads.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# File-path invocation is part of the documented maintenance workflow. Add
# the repository root before importing shared pipeline contracts so this entry
# point behaves the same as `python -m ...`.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

COUNTRIES = ("ca", "de", "dk", "es", "fr", "mx", "nz", "uk", "us")
REHEARSAL_VERSION = "legacy-v1-to-v2-rehearsal-v1"


def _fingerprint(country: str, row: dict[str, str]) -> str:
    value = "\0".join((country, row.get("establishment_id", ""), row.get("establishment_number", ""), row.get("establishment_name", ""), row.get("city", "")))
    return hashlib.sha256(value.encode("utf-8", "surrogateescape")).hexdigest()


def _valid_point(row: dict[str, str]) -> bool:
    try:
        lat, lon = float(row.get("latitude", "")), float(row.get("longitude", ""))
    except (TypeError, ValueError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180 and (lat != 0 or lon != 0)


def _category(row: dict[str, str]) -> list[str]:
    keys = {key for key, value in row.items() if value and value.strip().lower() not in {"0", "false", "no", "none", "nan"}}
    categories = []
    if any("slaughter" in key for key in keys):
        categories.append("slaughter")
    if any("process" in key for key in keys):
        categories.append("processing")
    return categories or ["unclassified"]


def _source_url(registry: dict[str, Any], country: str) -> str:
    wanted = {f"{country}.locations", f"{country}.smiley"}
    for source in registry.get("sources", []):
        if source.get("source_id") in wanted and source.get("url"):
            return str(source["url"])
        if any(f"static_data/{country}/locations.csv" in str(path) for path in source.get("legacy_paths", [])) and source.get("url"):
            return str(source["url"])
    return f"legacy://static_data/{country}/locations.csv"


def _normalize(country: str, row: dict[str, str], fingerprint: str) -> dict[str, Any]:
    establishment_id = (row.get("establishment_id") or row.get("establishment_number") or "").strip()
    has_identity = bool(establishment_id)
    coordinates = None
    if _valid_point(row):
        coordinates = [float(row["longitude"]), float(row["latitude"])]
    return {
        "establishment_id": establishment_id or None,
        "trading_name": (row.get("establishment_name") or "").strip() or None,
        "address_lines": [(row.get("street") or "").strip()] if row.get("street") else [],
        "postcode": (row.get("zip") or "").strip() or None,
        "city": (row.get("city") or "").strip() or None,
        "country_code": country.upper() if len(country) == 2 else "ZZ",
        "nation": country.upper(),
        "activity_categories": _category(row),
        "coordinates": coordinates,
        "coordinate_state": "source-supplied-pending-review" if coordinates else "unknown",
        "coordinate_precision": "source-precision-unspecified" if coordinates else "not-supplied",
        "privacy_gate": "pending-review",
        "coordinate_gate": "review_required",
        "publication_gate": "blocked",
        "source_origin": "legacy-v1-derived-snapshot",
        "legacy_label": "legacy snapshot; freshness and source retrieval date unknown",
        "identity_state": "accepted" if has_identity else "quarantined",
        "conversion_fingerprint": fingerprint,
    }


def build_rehearsal(*, root: Path, output: Path, registry_path: Path, max_records: int = 50_000, as_of_utc: str = "2026-09-16T00:00:00Z") -> dict[str, Any]:
    if max_records <= 0:
        raise ValueError("max_records must be positive")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    candidates: list[tuple[str, str, Path, dict[str, str]]] = []
    for country in COUNTRIES:
        path = root / country / "locations.csv"
        if not path.is_file():
            raise ValueError(f"missing legacy input: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                candidates.append((_fingerprint(country, row), country, path, row))
    selected = sorted(candidates, key=lambda item: item[0])[:max_records]
    grouped: dict[str, list[tuple[str, Path, dict[str, str]]]] = defaultdict(list)
    for fingerprint, country, path, row in selected:
        grouped[country].append((fingerprint, path, row))

    started = time.perf_counter()
    source_counts: dict[str, dict[str, int]] = {}
    strata = Counter()
    input_files = []
    for country in sorted(grouped):
        path = grouped[country][0][1]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        input_files.append({"country": country, "path": path.as_posix(), "sha256": digest, "byte_size": path.stat().st_size, "source_url": _source_url(registry, country), "retrieved_at_utc": None, "provenance_state": "legacy-retrieval-unknown"})
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        for row_number, (fingerprint, _, row) in enumerate(grouped[country], 1):
            record = {"source_id": f"legacy.v1.{country}.locations", "source_row": row_number, "source_record_key": (row.get("establishment_id") or row.get("establishment_number") or "") or None, "source_artifact_sha256": digest, "source_values": row, "normalized": _normalize(country, row, fingerprint)}
            (accepted if record["normalized"]["identity_state"] == "accepted" else quarantined).append(record)
            normalized = record["normalized"]
            strata[(country, "+".join(_category(row)), normalized["identity_state"], normalized["coordinate_precision"])] += 1
        run = output / country
        _, normalized_hash, _ = atomic_jsonl(run / "normalized" / "records.jsonl", accepted)
        _, handoff_hash, _ = atomic_jsonl(run / "candidate-handoff" / "normalized" / "records.jsonl", accepted)
        _, parsed_hash, _ = atomic_jsonl(run / "parsed" / "records.jsonl", accepted + quarantined)
        atomic_jsonl(run / "quarantined" / "records.jsonl", quarantined)
        artifact = SourceArtifact(source_url=_source_url(registry, country), retrieved_at_utc=as_of_utc, sha256=digest, byte_size=path.stat().st_size, code_version=REHEARSAL_VERSION, config_version=REHEARSAL_VERSION, coverage=f"legacy V1 {country} snapshot; source date unknown")
        manifest = private_manifest(source_id=f"legacy.v1.{country}.locations", adapter_version=REHEARSAL_VERSION, schema_version=REHEARSAL_VERSION, artifact=artifact, input_rows=len(accepted) + len(quarantined), normalized_rows=len(accepted), quarantined_rows=len(quarantined), normalized_sha256=normalized_hash, parsed_sha256=parsed_hash, anomaly_counts={"missing_identity": len(quarantined)})
        manifest.update({"country_code": country.upper(), "profile": "legacy-private-test-only", "legacy": True, "retrieval_semantics": "processing timestamp only; original source retrieval unknown", "publication_eligibility": "blocked"})
        atomic_json(run / "manifest.json", manifest)
        atomic_json(run / "candidate-handoff" / "manifest.json", {"source_id": manifest["source_id"], "manifest_sha256": hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode()).hexdigest(), "normalized_sha256": handoff_hash, "normalized_rows": len(accepted), "publication_eligibility": "blocked", "legacy": True})
        atomic_json(run / "review-packet.json", {"source_id": manifest["source_id"], "review_state": "review_required", "publication_eligibility": "blocked", "checks": ["preserve legacy label", "review source terms and privacy", "do not promote or expose stale rows"], "row_counts": {"input": manifest["input_rows"], "normalized": manifest["normalized_rows"], "quarantined": manifest["quarantined_rows"]}})
        source_counts[country] = {"input": len(accepted) + len(quarantined), "normalized": len(accepted), "quarantined": len(quarantined)}
    report = {"schema_version": "real-v2-rehearsal-v1", "rehearsal_id": output.name, "rehearsal_at_utc": as_of_utc, "legacy_label": "legacy V1-derived snapshot; not current and not publication-approved", "publication_eligibility": "blocked", "selection": {"method": "stable-sha256-row-fingerprint", "available_records": len(candidates), "selected_records": len(selected), "max_records": max_records}, "source_counts": source_counts, "totals": {key: sum(value[key] for value in source_counts.values()) for key in ("input", "normalized", "quarantined")}, "strata": {"|".join(key): value for key, value in sorted(strata.items())}, "source_files": input_files, "stages": {"conversion": "complete", "normalization": "complete", "quarantine": "complete", "candidate_handoff": "private normalized handoff produced", "import": "not attempted by this offline command", "api_export": "not attempted", "suppression": "not attempted", "delta": "not attempted", "backup_restore": "not attempted"}, "elapsed_seconds": round(time.perf_counter() - started, 3), "limitations": ["This conversion references existing V1-derived snapshots; it does not recreate original acquisition bytes or source retrieval times.", "The processing timestamp is not a claim that the legacy source is current.", "Database/API/export/suppression/backup stages require a disposable local database and are separate commands.", "Raw and derived rows remain in caller-selected private staging and are not committed."]}
    atomic_json(output / "rehearsal-report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("static_data"))
    parser.add_argument("--registry", type=Path, default=Path("pipeline/source_registry.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-records", type=int, default=50_000)
    parser.add_argument("--as-of", default="2026-09-16T00:00:00Z")
    args = parser.parse_args()
    report = build_rehearsal(root=args.root, output=args.output, registry_path=args.registry, max_records=args.max_records, as_of_utc=args.as_of)
    print(json.dumps({"selected": report["selection"]["selected_records"], "normalized": report["totals"]["normalized"], "quarantined": report["totals"]["quarantined"], "publication_eligibility": report["publication_eligibility"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
