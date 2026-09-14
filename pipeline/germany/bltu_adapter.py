"""Private BLtU export adapter; no geocoding or release promotion."""

from __future__ import annotations

import csv
import hashlib
import json
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
ACTIVITY_MAP = {"SH": "Meat Slaughter", "CP": "Meat Processing"}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def run(raw_path: Path, output_dir: Path, config: dict) -> dict:
    raw = raw_path.read_bytes()
    text = raw.decode("cp1252")
    rows = list(csv.reader(text.splitlines(), delimiter=";"))
    headers = rows[0] if rows else []
    parsed, normalized, quarantined = [], [], []
    for row_number, values in enumerate(rows[1:], start=2):
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
        activities = sorted({ACTIVITY_MAP[code] for code in activity_codes if code in ACTIVITY_MAP})
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
    manifest = {**config, "checksum_sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "adapter_version": ADAPTER_VERSION, "schema_version": SCHEMA_VERSION, "input_rows": len(parsed), "normalized_rows": len(normalized), "quarantined_rows": len(quarantined), "release_state": "not-created"}
    (output_dir / "run-manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return manifest
