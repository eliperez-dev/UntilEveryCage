"""Build a private, row-free regression report from local real source snapshots.

The input files are existing V1 country snapshots. This harness never copies or
prints rows: it records file hashes, deterministic aggregate strata, and a
stable bounded sample count so a local operator can compare reruns safely.
It does not grant publication approval or imply that V1 files are raw source
captures.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Iterable


DEFAULT_COUNTRIES = ("ca", "de", "dk", "es", "fr", "mx", "nz", "uk", "us")


def _number(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except (TypeError, ValueError):
        return None


def _valid_point(latitude: float | None, longitude: float | None) -> bool:
    return latitude is not None and longitude is not None and -90 <= latitude <= 90 and -180 <= longitude <= 180 and (latitude != 0 or longitude != 0)


def _precision(value: str | None) -> str:
    if not value or _number(value) is None:
        return "missing"
    digits = len(value.strip().lstrip("+-").split(".", 1)[1].rstrip("0")) if "." in value else 0
    return "source-decimal-" + str(min(digits, 6))


def _category(row: dict[str, str]) -> str:
    keys = {key for key, value in row.items() if value and value.strip().lower() not in {"0", "false", "no", "none", "nan"}}
    if any("slaughter" in key for key in keys):
        return "slaughter-or-processing"
    if any("process" in key for key in keys):
        return "processing"
    return "other"


def _identity_quality(row: dict[str, str]) -> str:
    has_id = bool((row.get("establishment_id") or row.get("establishment_number") or "").strip())
    has_name = bool((row.get("establishment_name") or "").strip())
    has_city = bool((row.get("city") or "").strip())
    if has_id and has_name and has_city:
        return "strong"
    if has_id and (has_name or has_city):
        return "partial"
    return "weak-or-missing"


def _row_fingerprint(country: str, row: dict[str, str]) -> str:
    key = "\0".join((country, row.get("establishment_id", ""), row.get("establishment_number", ""), row.get("establishment_name", ""), row.get("city", "")))
    return hashlib.sha256(key.encode("utf-8", "surrogateescape")).hexdigest()


def _files(root: Path, countries: Iterable[str]) -> list[Path]:
    paths = [root / country / "locations.csv" for country in countries]
    missing = [path.as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ValueError("missing real corpus inputs: " + ", ".join(missing))
    return paths


def build_report(root: Path, *, countries: Iterable[str] = DEFAULT_COUNTRIES, max_records: int = 50_000, as_of: str = "") -> dict:
    if max_records <= 0:
        raise ValueError("max_records must be positive")
    paths = _files(root, countries)
    candidates: list[tuple[str, Path, dict[str, str]]] = []
    source_files = []
    for path in paths:
        country = path.parent.name
        source_files.append({"country": country, "path": path.as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size, "input_kind": "existing-v1-derived-snapshot"})
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                candidates.append((_row_fingerprint(country, row), path, row))
    selected = sorted(candidates, key=lambda item: item[0])[:max_records]
    strata = Counter()
    countries_count = Counter()
    sources_count = Counter()
    accepted = quarantined = 0
    for _, path, row in selected:
        country = path.parent.name
        identity = _identity_quality(row)
        coordinate_state = "valid" if _valid_point(_number(row.get("latitude")), _number(row.get("longitude"))) else "missing-or-invalid"
        state = "quarantined" if identity == "weak-or-missing" or coordinate_state == "missing-or-invalid" else "accepted-private"
        accepted += state == "accepted-private"
        quarantined += state == "quarantined"
        countries_count[country] += 1
        sources_count[f"v1.{country}.locations"] += 1
        latitude, longitude = _number(row.get("latitude")), _number(row.get("longitude"))
        coordinate_state = "valid" if _valid_point(latitude, longitude) else "missing-or-invalid"
        precision = _precision(row.get("latitude")) if coordinate_state == "valid" else "missing"
        strata[(country, f"v1.{country}.locations", _category(row), state, precision, identity)] += 1
    return {
        "schema_version": "real-corpus-regression-v1",
        "as_of_utc": as_of or None,
        "corpus_state": "private-regression-only",
        "publication_eligibility": "blocked",
        "selection": {"method": "stable-sha256-row-fingerprint", "max_records": max_records, "selected_records": len(selected), "available_records": len(candidates)},
        "coverage": {"country_count": len(paths), "source_profile_count": len(paths), "countries": dict(sorted(countries_count.items())), "sources": dict(sorted(sources_count.items()))},
        "funnel": {"selected": len(selected), "accepted_private": accepted, "quarantined": quarantined, "row_count_reconciles": len(selected) == accepted + quarantined},
        "strata": {"|".join(key): value for key, value in sorted(strata.items())},
        "source_files": source_files,
        "stages": {"raw_preservation": "not_exercised; only existing V1 snapshot hashes available", "normalization": "measured existing V1 derived rows; no new normalization claimed", "quarantine": "identity-quality quarantine measured", "candidate_handoff": "not_exercised", "private_import": "not_exercised", "test_only_api_export": "not_exercised"},
        "limitations": ["No raw source bytes are present in this checkout; this is not a reproducible raw-acquisition corpus.", "The nine V1 files provide nine country/source profiles, but not eight independently acquired V2 adapters.", "Row-level values, identifiers, addresses, coordinates, and samples are intentionally omitted from the report.", "No publication, release, or human review authorization is implied."],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("static_data"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-records", type=int, default=50_000)
    parser.add_argument("--as-of", default="")
    args = parser.parse_args()
    report = build_report(args.root, max_records=args.max_records, as_of=args.as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"selected_records": report["selection"]["selected_records"], "countries": report["coverage"]["country_count"], "source_profiles": report["coverage"]["source_profile_count"], "publication_eligibility": report["publication_eligibility"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
