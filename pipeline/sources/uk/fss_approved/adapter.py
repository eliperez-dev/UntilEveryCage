"""Synthetic-only FSS Scotland approved-establishments adapter.

This module parses supplied bytes only. Acquisition, geocoding, release and
publication are deliberately outside its authority.
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.common.activity import classify_activities
from pipeline.common.privacy import address_privacy_risk

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
REQUIRED_COLUMNS = tuple(CONFIG["required_columns"])
ALLOWED_ACTIVITIES = frozenset(CONFIG["allowed_activities"])
ALLOWED_STATUSES = frozenset(CONFIG["allowed_statuses"])


class FssContractError(ValueError):
    """The supplied artifact cannot be interpreted under the pinned contract."""


@dataclass(frozen=True)
class ValidationResult:
    accepted: tuple[dict[str, Any], ...]
    quarantined: tuple[dict[str, Any], ...]
    source_sha256: str
    contract_version: str = CONFIG["contract_version"]
    release_allowed: bool = False
    coverage_counts: dict[str, int] | None = None
    anomaly_counts: dict[str, int] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _split(value: str | None) -> tuple[str, ...]:
    return tuple(part for part in (_clean(item) for item in (value or "").split(";")) if part)


def _record(row: dict[str, str], line: int) -> dict[str, Any]:
    approval = _clean(row.get("approval_number"))
    nation = _clean(row.get("nation"))
    return {"source_id": CONFIG["source_id"], "source_row": line,
            "source_record_key": f"{nation or 'unknown'}|{approval or 'unknown'}",
            "source_values": dict(row), "normalized": {
                "approval_number": approval,
                # Keep the source-native identifier and expose the shared
                # importer identity explicitly; neither value is inferred or
                # used to merge records across authorities.
                "establishment_id": _clean(row.get("approval_number")),
                "trading_name": _clean(row.get("trading_name")),
                "address_lines": tuple(_clean(row.get(f"address_line_{n}")) for n in range(1, 4)),
                "postcode": _clean(row.get("postcode")), "activities": _split(row.get("activities")),
                "activity_categories": classify_activities(_split(row.get("activities"))),
                "species": _clean(row.get("species")),
                "competent_authority": _clean(row.get("competent_authority")),
                "nation": nation, "status": _clean(row.get("status")),
                "remarks": _clean(row.get("remarks")), "published_date": _clean(row.get("published_date")),
                "coordinates": None}}


class FssApprovedEstablishmentsAdapter:
    source_id = CONFIG["source_id"]
    schema_version = CONFIG["contract_version"]
    adapter_version = CONFIG["adapter_version"]

    def parse_bytes(self, content: bytes) -> ValidationResult:
        digest = hashlib.sha256(content).hexdigest()
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content.decode("cp1252")
            except UnicodeDecodeError as exc:
                raise FssContractError("source is neither UTF-8 nor Windows-1252 CSV") from exc
        try:
            rows = list(csv.reader(text.splitlines(), strict=True))
        except csv.Error as exc:
            raise FssContractError("malformed CSV") from exc

        # The live FSS export has a four-row title/published-date preamble and
        # a blank first column.  The synthetic contract remains supported for
        # deterministic tests, but live parsing is pinned to the inspected
        # header rather than guessing from column positions.
        live_header = tuple(CONFIG.get("live_columns", ()))
        live_header_index = next((index for index, row in enumerate(rows) if tuple(row) == live_header), None)
        live = live_header_index is not None
        if not live and rows and tuple(rows[0]) == REQUIRED_COLUMNS:
            headers = rows[0]
            data_rows = rows[1:]
            mapped_rows = [{header: row[index] if index < len(row) else None for index, header in enumerate(headers)} for row in data_rows]
            line_numbers = range(2, len(rows) + 1)
        elif live:
            assert live_header_index is not None
            headers = rows[live_header_index]
            data_rows = rows[live_header_index + 1:]
            mapped_rows = []
            for row in data_rows:
                if len(row) != len(headers):
                    raise FssContractError("schema drift: a live row has the wrong column count")
                mapped_rows.append({(header if header else "source_column_0"): row[index] for index, header in enumerate(headers)})
            line_numbers = range(live_header_index + 2, len(rows) + 1)
        else:
            raise FssContractError("schema drift: expected pinned FSS or inspected live header")
        if any(len(row) != len(headers) for row in data_rows):
            raise FssContractError("schema drift: a row has the wrong column count")
        values = [_clean(row.get("approval_number") or row.get("Approval Number")) for row in mapped_rows]
        duplicates = {value for value in values if value and values.count(value) > 1}
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        anomalies: dict[str, int] = {}
        coverage: dict[str, int] = {}
        for line, row in zip(line_numbers, mapped_rows):
            reasons: list[str] = []
            if live:
                approval = _clean(row.get("Approval Number"))
                activities = tuple(value for key, value in row.items() if key in {"All Activities Approved", "Associated Activities"} or key.startswith("Part A - ") or key.startswith("Part B - ") if _clean(value))
                record_row = {
                    "approval_number": approval, "trading_name": row.get("Trading Name"),
                    "address_line_1": row.get("Address 1"), "address_line_2": row.get("Address 2"),
                    "address_line_3": row.get("Address 3"), "address_line_4": row.get("Address 4"),
                    "postcode": row.get("Post Code"), "activities": ";".join(activities),
                    "species": row.get("Species"), "competent_authority": row.get("Competent Authority"),
                    "nation": "Scotland", "status": None, "remarks": row.get("Remarks"),
                    "published_date": None, "source_url": None, "source_licence": None,
                    **{f"live_{key}": value for key, value in row.items()},
                }
                activities = tuple(_clean(value) for value in activities if _clean(value))
                missing_values = not approval or not _clean(row.get("Trading Name"))
            else:
                approval = _clean(row.get("approval_number"))
                activities = _split(row.get("activities"))
                record_row = row
                missing_values = any(value is None for value in row.values())
            if missing_values:
                reasons.append("malformed_row")
            if not approval:
                reasons.append("missing_approval_number")
            if approval in duplicates:
                reasons.append("duplicate_id")
            if not activities:
                reasons.append("missing_activity")
            elif not live and any(activity not in ALLOWED_ACTIVITIES for activity in activities):
                reasons.append("unknown_activity")
            elif live and not classify_activities(activities):
                reasons.append("no_relevant_activity")
            status = _clean(row.get("status")) if not live else None
            if status and status.lower() not in ALLOWED_STATUSES:
                reasons.append("unknown_status")
            if _clean(row.get("remarks")):
                reasons.append("remarks_present")
            address = " ".join(_clean(record_row.get(f"address_line_{n}")) or "" for n in range(1, 5 if live else 4))
            if address_privacy_risk(address):
                reasons.append("address_privacy_risk")
            nation = "Scotland" if live else (_clean(row.get("nation")) or "")
            coverage[nation] = coverage.get(nation, 0) + 1
            for reason in reasons:
                anomalies[reason] = anomalies.get(reason, 0) + 1
            record = _record(record_row, line)
            (quarantined if reasons else accepted).append({"reasons": tuple(reasons), "record": record} if reasons else record)
        return ValidationResult(tuple(accepted), tuple(quarantined), digest, coverage_counts=coverage, anomaly_counts=anomalies)

    def parse_file(self, path: str | Path) -> ValidationResult:
        return self.parse_bytes(Path(path).read_bytes())

    def run(self, raw_path: str | Path, run_dir: str | Path, config: SourceArtifact | dict[str, Any] | None = None) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        if isinstance(config, SourceArtifact):
            config = asdict(config)
            config["checksum_sha256"] = config["sha256"]
        elif config is None:
            # Retain the fixture-only convenience used by the original unit
            # tests; real lifecycle runs must supply a typed artifact.
            config = {"source_url": "synthetic-fixture://fss", "retrieved_at_utc": "2026-01-01T00:00:00Z",
                      "checksum_sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
                      "code_version": self.adapter_version, "config_version": self.schema_version,
                      "coverage": "Scotland synthetic fixture"}
        if config.get("checksum_sha256") or "byte_size" in config:
            if config.get("checksum_sha256") != hashlib.sha256(raw).hexdigest() or int(config.get("byte_size", -1)) != len(raw):
                raise FssContractError("source checksum or byte size mismatch")
        else:
            # Legacy fixture callers supplied only a URL/timestamp.  Fill the
            # facts locally for compatibility; typed lifecycle callers always
            # arrive with the shared SourceArtifact integrity fields above.
            config["checksum_sha256"] = hashlib.sha256(raw).hexdigest()
            config["byte_size"] = len(raw)
        result = self.parse_bytes(raw)
        root = Path(run_dir)
        _write_jsonl(root / "parsed" / "records.jsonl", list(result.accepted) + [item["record"] for item in result.quarantined])
        normalized_sha256 = _write_jsonl(root / "normalized" / "records.jsonl", list(result.accepted))
        _write_jsonl(root / "quarantined" / "records.jsonl", list(result.quarantined))
        (root / "released").mkdir(parents=True, exist_ok=True)
        manifest = {"source_id": self.source_id, "country_code": "GB", "adapter_version": self.adapter_version,
                    "schema_version": self.schema_version, "checksum_sha256": result.source_sha256,
                    "sha256": result.source_sha256,
                    "byte_size": len(raw), "input_rows": len(result.accepted) + len(result.quarantined),
                    "normalized_rows": len(result.accepted), "normalized_sha256": normalized_sha256,
                    "quarantined_rows": len(result.quarantined),
                    "coverage_counts": result.coverage_counts or {}, "anomaly_counts": result.anomaly_counts or {},
                    "release_state": "not-created", "publication_state": "private-candidate",
                    "acquisition": dict(config), "source_url": config.get("source_url"),
                    "retrieved_at_utc": config.get("retrieved_at_utc") or config.get("retrieved_at"), "effective_date": config.get("effective_date"),
                    "publication_date": config.get("publication_date"), "code_version": config.get("code_version", self.adapter_version),
                    "config_version": config.get("config_version", self.schema_version), "coverage": config.get("coverage"),
                    "rights_caveat": config.get("rights_caveat"), "privacy_caveat": config.get("privacy_caveat")}
        _atomic(root / "manifest.json", (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
        return manifest

    def write_restricted_result(self, result: ValidationResult, path: str | Path) -> None:
        output = Path(path)
        payload = json.dumps(result.as_dict(), ensure_ascii=False, sort_keys=True, indent=2, default=list) + "\n"
        _atomic(output, payload.encode())


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    payload = b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True, default=list) + "\n").encode() for row in rows)
    _atomic(path, payload)
    return hashlib.sha256(payload).hexdigest()


def _atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
