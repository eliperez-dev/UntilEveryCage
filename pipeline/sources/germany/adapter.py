"""Typed private adapter for the BVL BLtU general-list export."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest
from pipeline.germany.bltu_adapter import EXPECTED_HEADERS

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
CURRENT_ID_INDEX = 5
NAME_INDEX = 1
STATE_INDEX = 0
STREET_INDEX = 2
CITY_INDEX = 3
ACTIVITY_START = 7
ACTIVITY_END = 41
ACTIVITY_MAP = {"SH": "slaughter", "CP": "processing"}


def _source_columns(headers: list[str], values: list[str]) -> list[dict[str, str]]:
    return [{"header": headers[index], "value": values[index]} for index in range(len(headers))]


class BltuAdapter:
    source_id = CONFIG["source_id"]
    adapter_version = CONFIG["adapter_version"]
    schema_version = CONFIG["schema_version"]

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        try:
            text = content.decode("utf-8-sig")
            encoding = "utf-8-sig"
        except UnicodeDecodeError:
            text = content.decode("cp1252")
            encoding = "cp1252"
        rows = list(csv.reader(text.splitlines(), delimiter=";", strict=True))
        headers = rows[0] if rows else []
        matched = headers == list(EXPECTED_HEADERS)
        id_counts = Counter(values[CURRENT_ID_INDEX].strip() for values in rows[1:] if len(values) > CURRENT_ID_INDEX and values[CURRENT_ID_INDEX].strip())
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        anomalies: Counter[str] = Counter()
        categories: Counter[str] = Counter()
        for line, values in enumerate(rows[1:], start=2):
            source = {"source_row": line, "source_headers": headers, "source_values": values}
            reasons: list[str] = []
            if not matched:
                reasons.append("unrecognized_header_schema")
            if len(values) != len(EXPECTED_HEADERS):
                reasons.append("physical_column_count_mismatch")
            current_id = values[CURRENT_ID_INDEX].strip() if len(values) > CURRENT_ID_INDEX else ""
            name = values[NAME_INDEX].strip() if len(values) > NAME_INDEX else ""
            if not current_id:
                reasons.append("missing_current_approval_id")
            elif id_counts[current_id] > 1:
                reasons.append("duplicate_current_approval_id")
            if not name:
                reasons.append("missing_establishment_name")
            activity_codes = [headers[index] for index in range(ACTIVITY_START, min(ACTIVITY_END, len(values))) if values[index].strip()]
            if not activity_codes:
                reasons.append("missing_activity_code")
            if any(code not in ACTIVITY_MAP for code in activity_codes):
                reasons.append("unmapped_activity_code")
            mapped = tuple(dict.fromkeys(ACTIVITY_MAP[code] for code in activity_codes if code in ACTIVITY_MAP))
            if not mapped and "missing_activity_code" not in reasons:
                reasons.append("unmapped_activity_code")
            for category in mapped:
                categories[category] += 1
            record = {"source_id": self.source_id, "source_row": line, "source_record_key": f"{current_id or 'unknown'}|{line}", "source_values": source, "normalized": {"establishment_id": current_id or None, "approval_number": current_id or None, "name": name or None, "trading_name": name or None, "country_code": "DE", "nation": "Germany", "state": values[STATE_INDEX].strip() if len(values) > STATE_INDEX else None, "city": values[CITY_INDEX].strip() if len(values) > CITY_INDEX else None, "address": None, "address_state": "source-present-pending-privacy-review" if len(values) > STREET_INDEX and values[STREET_INDEX].strip() else "unknown", "activity_codes": tuple(activity_codes), "activity_categories": mapped, "source_activity_categories": mapped, "classification_state": "mapped" if mapped and not any(code not in ACTIVITY_MAP for code in activity_codes) else "unresolved", "coordinates": None, "coordinate_state": "unknown", "coordinate_precision": "not-supplied", "privacy_gate": "pending-review", "coordinate_gate": "review_required", "publication_gate": "blocked"}}
            if reasons:
                unique = tuple(dict.fromkeys(reasons))
                for reason in unique:
                    anomalies[reason] += 1
                quarantined.append({"reasons": unique, "record": record})
            else:
                accepted.append(record)
        return {"accepted": accepted, "quarantined": quarantined, "input_rows": len(rows) - 1 if rows else 0, "source_sha256": hashlib.sha256(content).hexdigest(), "schema_status": "matched" if matched else "unrecognized", "schema_fingerprint": hashlib.sha256(json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(), "encoding": encoding, "row_length_counts": dict(Counter(str(len(row)) for row in rows[1:])), "coverage_counts": dict(categories), "anomaly_counts": dict(sorted(anomalies.items()))}

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if artifact.sha256 != digest or artifact.byte_size != len(raw):
            raise ValueError("BLtU artifact provenance mismatch")
        result = self.parse_bytes(raw)
        if result["schema_status"] != "matched":
            # Header drift is a source-contract failure, not a row-level
            # anomaly. Do not let an empty or shifted export look healthy.
            raise ValueError("BLtU schema drift: unrecognized header schema")
        root = Path(run_dir)
        parsed = result["accepted"] + [item["record"] for item in result["quarantined"]]
        _, parsed_sha, _ = atomic_jsonl(root / "parsed" / "records.jsonl", parsed)
        _, normalized_sha, _ = atomic_jsonl(root / "normalized" / "records.jsonl", result["accepted"])
        atomic_jsonl(root / "quarantined" / "records.jsonl", result["quarantined"])
        manifest = private_manifest(source_id=self.source_id, adapter_version=self.adapter_version, schema_version=self.schema_version, artifact=artifact, input_rows=result["input_rows"], normalized_rows=len(result["accepted"]), quarantined_rows=len(result["quarantined"]), normalized_sha256=normalized_sha, parsed_sha256=parsed_sha, anomaly_counts=result["anomaly_counts"])
        manifest.update({"country_code": "DE", "coverage": CONFIG["coverage"], "geocoding": "disabled", "schema_status": result["schema_status"], "schema_fingerprint": result["schema_fingerprint"], "encoding": result["encoding"], "row_length_counts": result["row_length_counts"], "coverage_counts": result["coverage_counts"], "release_gate": "restricted_pending_terms"})
        atomic_json(root / "manifest.json", manifest)
        return manifest

    def write_candidate_handoff(self, run_dir: str | Path, artifact: SourceArtifact, parsed: dict[str, Any]) -> dict[str, Any]:
        return write_handoff(run_dir, parsed["accepted"], artifact, source_id=self.source_id)
