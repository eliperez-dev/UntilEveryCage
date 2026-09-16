"""Deterministic, row-free geospatial readiness audit for normalized CSV corpora.

This intentionally does not geocode. It measures source-coordinate quality and
safe candidate readiness without emitting addresses, names, IDs, or coordinates.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PRIVATE_RE = re.compile(r"\b(private|residential|home|farmhouse|c/o|care of)\b", re.I)

def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def valid_point(lat, lon):
    return lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0)

def _audit_rows(files, sample_size, as_of, corpus):
    funnel = Counter(); countries = Counter(); strata = Counter(); sample_buckets = {}
    file_manifest = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        file_manifest.append({"country": path.parent.name, "path": path.as_posix(), "sha256": digest, "bytes": path.stat().st_size})
        if path.suffix == ".jsonl":
            rows = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        else:
            rows = csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines())
        for row in rows:
                funnel["total"] += 1; country = path.parent.name; countries[country] += 1
                normalized = row.get("normalized", row)
                if not isinstance(normalized, dict):
                    normalized = {}
                coordinates = normalized.get("coordinates")
                lat = num(row.get("latitude", normalized.get("latitude")))
                lon = num(row.get("longitude", normalized.get("longitude")))
                if isinstance(coordinates, (list, tuple)) and len(coordinates) == 2:
                    lon, lat = num(coordinates[0]), num(coordinates[1])
                coord = "source_coordinate_valid" if valid_point(lat, lon) else "source_coordinate_invalid_or_missing"
                funnel[coord] += 1
                address_values = (normalized.get("street", row.get("street")), normalized.get("zip", row.get("zip")), normalized.get("city", row.get("city")), normalized.get("state", row.get("state")))
                address = " ".join(filter(None, address_values))
                quality = "address_complete" if all(address_values) else ("city_only" if address_values[2] else "address_missing")
                privacy = "privacy_restricted_candidate" if PRIVATE_RE.search(address) else "privacy_not_flagged"
                if coord == "source_coordinate_valid": outcome = "map_ready_under_current_rules" if privacy == "privacy_not_flagged" else "privacy_restricted"
                elif privacy != "privacy_not_flagged": outcome = "privacy_restricted"
                elif quality == "city_only": outcome = "city_coarse_candidate"
                elif quality == "address_complete": outcome = "geocode_candidate"
                else: outcome = "unresolved"
                funnel[outcome] += 1; strata[(country, quality, coord)] += 1
                key = hashlib.sha256((country + "\0" + str(normalized.get("establishment_id", row.get("establishment_id", ""))) + "\0" + address).encode()).hexdigest()
                bucket = sample_buckets.setdefault((country, quality, coord), [])
                bucket.append((key, {"country": country, "address_quality": quality, "coordinate_state": coord, "outcome": outcome}))
    samples = []
    for bucket in sample_buckets.values():
        samples.extend(sorted(bucket)[:sample_size])
    samples = [v for _, v in sorted(samples)[:sample_size * max(1, len(files))]]
    composition = Counter("|".join((x["country"], x["address_quality"], x["coordinate_state"])) for x in samples)
    funnel.setdefault("total", 0)
    return {"corpus": corpus, "schema_version": "geospatial-readiness-audit/v1", "as_of": as_of or datetime.now(timezone.utc).isoformat(), "method": "offline deterministic audit; no geocoder calls", "funnel": dict(sorted(funnel.items())), "country_counts": dict(sorted(countries.items())), "strata_counts": {"|".join(k): v for k,v in sorted(strata.items())}, "sample": {"size": len(samples), "composition": dict(composition)}, "sample_rows": samples, "source_files": file_manifest, "provenance_fields_required_for_any_geocode": ["provider", "query_hash", "queried_at", "precision", "review_state"], "publication_rule": "map-ready requires current privacy eligibility and release approval; geocoding success alone never grants publication permission"}

def _v2_files(root: Path):
    manifests = sorted(root.rglob("manifest.json")) if root.exists() else []
    files, availability = [], []
    for manifest_path in manifests:
        try: manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): continue
        records = manifest_path.parent / "normalized" / "records.jsonl"
        source_id = manifest.get("source_id", manifest_path.parent.name)
        entry = {"source_id": source_id, "manifest": manifest_path.as_posix(), "records": records.as_posix(), "available": records.is_file(), "normalized_rows_declared": manifest.get("normalized_rows")}
        availability.append(entry)
        if records.is_file(): files.append(records)
    return files, availability

def audit(root: Path, sample_size: int = 20, as_of: str | None = None, *, v2_root: Path | None = None):
    v1 = _audit_rows(sorted(root.glob("*/locations.csv")), sample_size, as_of, "V1-legacy-static-data")
    v2_root = v2_root or root
    v2_files, availability = _v2_files(v2_root)
    v2 = _audit_rows(v2_files, sample_size, as_of, "V2-normalized-manifest-runs")
    v2["availability"] = {"searched_root": v2_root.as_posix(), "manifests_found": len(availability), "sources": availability, "note": "No V2 records are inferred from V1 rows; absent manifests/records remain unavailable."}
    # Keep the original V1 shape available to existing callers; new consumers
    # must use the explicitly named v1/v2 sections.
    return {"schema_version": "geospatial-readiness-audit/v2", "as_of": as_of or datetime.now(timezone.utc).isoformat(), "v1": v1, "v2": v2, "funnel": v1["funnel"], "country_counts": v1["country_counts"], "strata_counts": v1["strata_counts"], "sample": v1["sample"], "sample_rows": v1["sample_rows"], "source_files": v1["source_files"]}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--root", type=Path, default=Path("static_data")); ap.add_argument("--output", type=Path, required=True); ap.add_argument("--sample-size", type=int, default=20); ap.add_argument("--as-of")
    args = ap.parse_args(); report = audit(args.root, args.sample_size, args.as_of); args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"v1_total": report["v1"]["funnel"].get("total", 0), "v2_total": report["v2"]["funnel"].get("total", 0), "v2_manifests": report["v2"]["availability"]["manifests_found"]}, sort_keys=True))
if __name__ == "__main__": main()
