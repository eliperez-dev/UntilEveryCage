#!/usr/bin/env python3
"""Synthetic-only foundation for the Germany V2 adapter.

The adapter accepts an already-acquired local artifact. It does not fetch, geocode,
publish, or promote records. Source values are retained with every parsed and
normalized record so later review can distinguish evidence from interpretation.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

ADAPTER_VERSION = "de-v2-foundation-1"
SCHEMA_VERSION = "location-v2-foundation-1"
REQUIRED_METADATA = {
    "source_url",
    "retrieval_timestamp",
    "checksum_sha256",
    "byte_size",
    "source_publication_date",
}
REQUIRED_COLUMNS = {
    "source_id",
    "name",
    "activity_code",
    "species_codes",
    "street",
    "city",
    "zip",
    "latitude",
    "longitude",
}
ACTIVITY_MAP = {
    "CP": "Meat Processing",
    "GME": "Meat Processing",
    "SH": "Meat Slaughter",
}


def source_metadata(raw: bytes, config: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic manifest fragment for an acquired artifact."""
    return {
        **config,
        "checksum_sha256": hashlib.sha256(raw).hexdigest(),
        "byte_size": len(raw),
        "adapter_version": ADAPTER_VERSION,
        "schema_version": SCHEMA_VERSION,
    }


def _validate_metadata(metadata: dict[str, Any]) -> None:
    missing = REQUIRED_METADATA - metadata.keys()
    if missing:
        raise ValueError(f"missing provenance fields: {', '.join(sorted(missing))}")
    if not metadata.get("source_url"):
        raise ValueError("source_url must be non-empty")


def parse(raw: bytes, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse CSV into evidence-preserving records; do not classify or geocode."""
    _validate_metadata(metadata)
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="strict")))
    if not reader.fieldnames:
        raise ValueError("missing source header")
    missing = REQUIRED_COLUMNS - set(reader.fieldnames)
    if missing:
        raise ValueError(f"missing source columns: {', '.join(sorted(missing))}")
    records = []
    for row_number, row in enumerate(reader, start=2):
        records.append(
            {
                "source_id": (row["source_id"] or "").strip(),
                "source_values": dict(row),
                "source_row": row_number,
                "provenance": metadata,
            }
        )
    return records


def normalize(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return normalized records and explicit quarantine records."""
    normalized: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    for record in records:
        source = record["source_values"]
        activity_code = (source.get("activity_code") or "").strip()
        activity = ACTIVITY_MAP.get(activity_code)
        if not record["source_id"] or not (source.get("name") or "").strip():
            quarantine.append({**record, "quarantine_reason": "missing identity"})
            continue
        if activity is None:
            quarantine.append({**record, "quarantine_reason": "unknown activity code"})
            continue
        lat_text, lon_text = (source.get("latitude") or "").strip(), (source.get("longitude") or "").strip()
        coordinate_status = "source"
        lat: float | None
        lon: float | None
        try:
            lat, lon = float(lat_text), float(lon_text)
        except ValueError:
            lat, lon, coordinate_status = None, None, "unresolved"
        if lat is not None and lon is not None and not (math.isfinite(lat) and math.isfinite(lon)):
            lat, lon, coordinate_status = None, None, "unresolved"
        if lat == 0.0 and lon == 0.0:
            lat, lon, coordinate_status = None, None, "unresolved"
        if lat is not None and lon is not None and not (47.0 <= lat <= 55.2 and 5.8 <= lon <= 15.1):
            quarantine.append({**record, "quarantine_reason": "coordinates outside configured Germany bounds"})
            continue
        normalized.append(
            {
                "schema_version": SCHEMA_VERSION,
                "source_id": record["source_id"],
                "establishment_id": record["source_id"],
                "establishment_name": source["name"].strip(),
                "type": activity,
                "street": (source.get("street") or "").strip(),
                "city": (source.get("city") or "").strip(),
                "zip": (source.get("zip") or "").strip(),
                "latitude": lat,
                "longitude": lon,
                "coordinate_status": coordinate_status,
                "source_values": source,
                "provenance": record["provenance"],
            }
        )
    return normalized, quarantine


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def run(raw_path: Path, output_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Process a local artifact into parsed/normalized/quarantined states only."""
    raw = raw_path.read_bytes()
    metadata = source_metadata(raw, config)
    if config.get("checksum_sha256") and config["checksum_sha256"] != metadata["checksum_sha256"]:
        raise ValueError("source checksum does not match configured checksum")
    parsed = parse(raw, metadata)
    normalized, quarantine = normalize(parsed)
    _write_jsonl_atomic(output_dir / "parsed" / "records.jsonl", parsed)
    _write_jsonl_atomic(output_dir / "normalized" / "records.jsonl", normalized)
    _write_jsonl_atomic(output_dir / "quarantined" / "records.jsonl", quarantine)
    manifest = {
        **metadata,
        "input_rows": len(parsed),
        "normalized_rows": len(normalized),
        "quarantined_rows": len(quarantine),
        "release_state": "not-created",
    }
    (output_dir / "released").mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "run-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
