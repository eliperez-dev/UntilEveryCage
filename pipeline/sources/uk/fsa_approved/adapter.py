"""Synthetic-only FSA England/Wales/Northern Ireland adapter.

The CSV shape is a pinned test contract, not a claim about a live FSA file.
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
REQUIRED_COLUMNS = tuple(CONFIG["required_columns"])
ALLOWED_ACTIVITIES = frozenset(CONFIG["allowed_activities"])
ALLOWED_STATUSES = frozenset(CONFIG["allowed_statuses"])
AUTHORITY_BY_NATION = CONFIG["authority_by_nation"]
ADDRESS_RISK = re.compile(r"\b(flat|apartment|house|home|residential|c/o|care of|caravan|lodge)\b", re.I)


class FsaContractError(ValueError):
    """The supplied artifact cannot be interpreted under the assumed contract."""


@dataclass(frozen=True)
class ValidationResult:
    accepted: tuple[dict[str, Any], ...]
    quarantined: tuple[dict[str, Any], ...]
    source_sha256: str
    contract_version: str = CONFIG["contract_version"]
    release_allowed: bool = False

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
    nation = _clean(row.get("nation"))
    return {"source_id": CONFIG["source_id"], "source_row": line,
            "source_values": dict(row), "normalized": {
                "establishment_id": _clean(row.get("establishment_id")),
                "trading_name": _clean(row.get("trading_name")),
                "address_lines": tuple(_clean(row.get(f"address_line_{n}")) for n in range(1, 4)),
                "postcode": _clean(row.get("postcode")), "activities": _split(row.get("activities")),
                "species": _clean(row.get("species")),
                "competent_authority": _clean(row.get("competent_authority")),
                "nation": nation, "authority_nation_key": nation,
                "status": _clean(row.get("status")), "remarks": _clean(row.get("remarks")),
                "published_date": _clean(row.get("published_date")), "coordinates": None}}


class FsaApprovedEstablishmentsAdapter:
    source_id = CONFIG["source_id"]
    schema_version = CONFIG["contract_version"]
    adapter_version = CONFIG["adapter_version"]

    def parse_bytes(self, content: bytes) -> ValidationResult:
        digest = hashlib.sha256(content).hexdigest()
        try:
            text = content.decode("utf-8-sig")
            reader = csv.DictReader(text.splitlines(), strict=True)
            if tuple(reader.fieldnames or ()) != REQUIRED_COLUMNS:
                raise FsaContractError("schema drift: expected pinned synthetic FSA columns in exact order")
            rows = list(reader)
        except UnicodeDecodeError as exc:
            raise FsaContractError("source is not UTF-8 CSV") from exc
        except csv.Error as exc:
            raise FsaContractError("malformed CSV") from exc
        if any(None in row for row in rows):
            raise FsaContractError("schema drift: a row has extra columns")
        keys = [(_clean(row.get("nation")), _clean(row.get("establishment_id"))) for row in rows]
        duplicates = {key for key in keys if key[0] and key[1] and keys.count(key) > 1}
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        for line, row in enumerate(rows, 2):
            reasons: list[str] = []
            nation = _clean(row.get("nation"))
            identifier = _clean(row.get("establishment_id"))
            if any(value is None for value in row.values()):
                reasons.append("malformed_row")
            if not identifier:
                reasons.append("missing_establishment_id")
            if (nation, identifier) in duplicates:
                reasons.append("duplicate_id_within_nation")
            if nation not in CONFIG["covered_nations"]:
                reasons.append("unknown_nation")
            authority = _clean(row.get("competent_authority"))
            if nation in AUTHORITY_BY_NATION and authority != AUTHORITY_BY_NATION[nation]:
                reasons.append("authority_nation_mismatch")
            activities = _split(row.get("activities"))
            if not activities:
                reasons.append("missing_activity")
            elif any(activity not in ALLOWED_ACTIVITIES for activity in activities):
                reasons.append("unknown_activity")
            status = _clean(row.get("status"))
            if status and status.lower() not in ALLOWED_STATUSES:
                reasons.append("unknown_status")
            if _clean(row.get("remarks")):
                reasons.append("remarks_present")
            address = " ".join(_clean(row.get(f"address_line_{n}")) or "" for n in range(1, 4))
            if ADDRESS_RISK.search(address):
                reasons.append("address_privacy_risk")
            record = _record(row, line)
            (quarantined if reasons else accepted).append({"reasons": tuple(reasons), "record": record} if reasons else record)
        return ValidationResult(tuple(accepted), tuple(quarantined), digest)

    def parse_file(self, path: str | Path) -> ValidationResult:
        return self.parse_bytes(Path(path).read_bytes())

    def run(self, raw_path: str | Path, run_dir: str | Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        result = self.parse_bytes(raw)
        root = Path(run_dir)
        _write_jsonl(root / "parsed" / "records.jsonl", list(result.accepted) + [item["record"] for item in result.quarantined])
        normalized_sha256 = _write_jsonl(root / "normalized" / "records.jsonl", list(result.accepted))
        _write_jsonl(root / "quarantined" / "records.jsonl", list(result.quarantined))
        (root / "released").mkdir(parents=True, exist_ok=True)
        manifest = {"source_id": self.source_id, "adapter_version": self.adapter_version,
                    "schema_version": self.schema_version, "schema_status": CONFIG["schema_status"],
                    "checksum_sha256": result.source_sha256, "byte_size": len(raw),
                    "input_rows": len(result.accepted) + len(result.quarantined),
                    "normalized_rows": len(result.accepted), "normalized_sha256": normalized_sha256,
                    "quarantined_rows": len(result.quarantined),
                    "release_state": "not-created", "publication_state": "human-gate-required",
                    "acquisition": CONFIG["acquisition"], "source_url": (config or {}).get("source_url"),
                    "retrieved_at": (config or {}).get("retrieved_at")}
        _atomic(root / "manifest.json", (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
        return manifest


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    payload = b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True, default=list) + "\n").encode() for row in rows)
    _atomic(path, payload)
    return hashlib.sha256(payload).hexdigest()


def _atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
