"""Private BLtU export adapter; no geocoding or release promotion."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path

SCHEMA_VERSION = "de-bltu-v1"
ADAPTER_VERSION = "de-bltu-adapter-1"
EXPECTED_COLUMNS = 50
CURRENT_ID_INDEX = 5
NAME_INDEX = 1
STATE_INDEX = 0
STREET_INDEX = 2
CITY_INDEX = 3
ACTIVITY_START = 7
ACTIVITY_END = 44
MAPPING_VERSION = "de-bltu-activity-map-1"
ACTIVITY_MAP = {"SH": "Meat Slaughter", "CP": "Meat Processing"}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows))
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def run(raw_path: Path, output_dir: Path, config: dict) -> dict:
    raw = raw_path.read_bytes()
    text = raw.decode("cp1252")
    rows = list(csv.reader(text.splitlines(), delimiter=";"))
    headers = rows[0] if rows else []
    parsed, normalized, quarantined = [], [], []
    lengths, activity_counts, mapping_counts = {}, {}, {}
    for row_number, values in enumerate(rows[1:], start=2):
        lengths[str(len(values))] = lengths.get(str(len(values)), 0) + 1
        evidence = {"source_row": row_number, "source_headers": headers, "source_values": values, "provenance": config}
        parsed.append(evidence)
        if len(values) != EXPECTED_COLUMNS:
            quarantined.append({**evidence, "quarantine_reason": f"physical column count {len(values)} != {EXPECTED_COLUMNS}"})
            continue
        current_id = values[CURRENT_ID_INDEX].strip()
        name = values[NAME_INDEX].strip()
        if not current_id:
            quarantined.append({**evidence, "quarantine_reason": "missing current approval id"})
            continue
        if not name:
            quarantined.append({**evidence, "quarantine_reason": "missing establishment name"})
            continue
        activity_codes = [headers[i].strip() for i in range(ACTIVITY_START, ACTIVITY_END) if values[i].strip() and headers[i].strip()]
        for code in activity_codes:
            activity_counts[code] = activity_counts.get(code, 0) + 1
        activities = sorted({ACTIVITY_MAP[code] for code in activity_codes if code in ACTIVITY_MAP})
        for activity in activities:
            mapping_counts[activity] = mapping_counts.get(activity, 0) + 1
        if not activities:
            quarantined.append({**evidence, "quarantine_reason": "unmapped activity code"})
            continue
        source_columns = [{"header": headers[i], "value": values[i]} for i in range(EXPECTED_COLUMNS)]
        normalized.append({
            "schema_version": SCHEMA_VERSION,
            "source_id": current_id,
            "establishment_id": current_id,
            "establishment_name": name,
            "type": "; ".join(activities),
            "interpretation": {"status": "mapped", "mapping_version": MAPPING_VERSION, "source_codes": activity_codes},
            "state": values[STATE_INDEX].strip(),
            "street": values[STREET_INDEX].strip(),
            "city": values[CITY_INDEX].strip(),
            "latitude": None,
            "longitude": None,
            "coordinate_status": "source_unavailable",
            "source_columns": source_columns,
            "provenance": config,
        })
    output_dir.mkdir(parents=True, exist_ok=True)
    for state, values in (("parsed", parsed), ("normalized", normalized), ("quarantined", quarantined)):
        _write_jsonl(output_dir / state / "records.jsonl", values)
    (output_dir / "released").mkdir(exist_ok=True)
    schema_fingerprint = hashlib.sha256(json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    config_fingerprint = hashlib.sha256(json.dumps({"mapping_version": MAPPING_VERSION, "activity_map": ACTIVITY_MAP, "expected_columns": EXPECTED_COLUMNS}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    diagnostics = {"row_length_counts": lengths, "source_activity_code_counts": activity_counts, "mapped_activity_counts": mapping_counts, "quarantine_reason_counts": {reason: sum(1 for row in quarantined if row["quarantine_reason"] == reason) for reason in sorted({row["quarantine_reason"] for row in quarantined})}, "coordinate_status_counts": {"source_unavailable": len(normalized)}}
    (output_dir / "validation-report.json").write_text(json.dumps(diagnostics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {**config, "checksum_sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "adapter_version": ADAPTER_VERSION, "schema_version": SCHEMA_VERSION, "mapping_version": MAPPING_VERSION, "schema_fingerprint": schema_fingerprint, "config_fingerprint": config_fingerprint, "input_rows": len(parsed), "normalized_rows": len(normalized), "quarantined_rows": len(quarantined), "release_state": "not-created", "release_gate": "restricted_pending_terms", "geocoding": "disabled"}
    (output_dir / "run-manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return manifest
