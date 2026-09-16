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

def audit(root: Path, sample_size: int = 20, as_of: str | None = None):
    files = sorted(root.glob("*/locations.csv"))
    funnel = Counter(); countries = Counter(); strata = Counter(); sample_buckets = {}
    file_manifest = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        file_manifest.append({"country": path.parent.name, "path": path.as_posix(), "sha256": digest, "bytes": path.stat().st_size})
        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = csv.DictReader(fh)
            for row in rows:
                funnel["total"] += 1; country = path.parent.name; countries[country] += 1
                lat, lon = num(row.get("latitude")), num(row.get("longitude"))
                coord = "source_coordinate_valid" if valid_point(lat, lon) else "source_coordinate_invalid_or_missing"
                funnel[coord] += 1
                address = " ".join(filter(None, (row.get("street"), row.get("zip"), row.get("city"), row.get("state"))))
                quality = "address_complete" if row.get("street") and row.get("city") and row.get("zip") else ("city_only" if row.get("city") else "address_missing")
                privacy = "privacy_restricted_candidate" if PRIVATE_RE.search(address) else "privacy_not_flagged"
                if coord == "source_coordinate_valid": outcome = "map_ready_under_current_rules" if privacy == "privacy_not_flagged" else "privacy_restricted"
                elif privacy != "privacy_not_flagged": outcome = "privacy_restricted"
                elif quality == "city_only": outcome = "city_coarse_candidate"
                elif quality == "address_complete": outcome = "geocode_candidate"
                else: outcome = "unresolved"
                funnel[outcome] += 1; strata[(country, quality, coord)] += 1
                key = hashlib.sha256((country + "\0" + row.get("establishment_id", "") + "\0" + address).encode()).hexdigest()
                bucket = sample_buckets.setdefault((country, quality, coord), [])
                bucket.append((key, {"country": country, "address_quality": quality, "coordinate_state": coord, "outcome": outcome}))
    samples = []
    for bucket in sample_buckets.values():
        samples.extend(sorted(bucket)[:sample_size])
    samples = [v for _, v in sorted(samples)[:sample_size * max(1, len(files))]]
    composition = Counter("|".join((x["country"], x["address_quality"], x["coordinate_state"])) for x in samples)
    return {"schema_version": "geospatial-readiness-audit/v1", "as_of": as_of or datetime.now(timezone.utc).isoformat(), "method": "offline deterministic audit; no geocoder calls", "funnel": dict(sorted(funnel.items())), "country_counts": dict(sorted(countries.items())), "strata_counts": {"|".join(k): v for k,v in sorted(strata.items())}, "sample": {"size": len(samples), "composition": dict(composition)}, "sample_rows": samples, "source_files": file_manifest, "provenance_fields_required_for_any_geocode": ["provider", "query_hash", "queried_at", "precision", "review_state"], "publication_rule": "map-ready requires current privacy eligibility and release approval; geocoding success alone never grants publication permission"}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--root", type=Path, default=Path("static_data")); ap.add_argument("--output", type=Path, required=True); ap.add_argument("--sample-size", type=int, default=20); ap.add_argument("--as-of")
    args = ap.parse_args(); report = audit(args.root, args.sample_size, args.as_of); args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"total": report["funnel"].get("total", 0), "funnel": report["funnel"], "sample_size": report["sample"]["size"]}, sort_keys=True))
if __name__ == "__main__": main()
