"""Fail-closed private adapter for the FSIS MPI directory CSV."""
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

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
V1_HEADER = Path(__file__).resolve().parents[4] / "static_data/us/locations.csv"
V1_COLUMNS = tuple(next(csv.reader([V1_HEADER.read_text(encoding="utf-8-sig").splitlines()[0]])))
CORE_COLUMNS = ("establishment_id", "establishment_number", "establishment_name", "street", "city", "state", "zip", "phone", "grant_date", "type", "dbas", "district", "circuit", "size", "latitude", "longitude", "county", "fips_code")
ACTIVITY_COLUMNS = frozenset(column for column in V1_COLUMNS if column.endswith("_slaughter") or column.endswith("_processing") or column in {"slaughter", "processing", "egg_processing", "ratite_processing", "siluriformes_processing"})
ALLOWED_STATES = frozenset("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC PR VI GU AS MP".split())


class FsisContractError(ValueError):
    """The captured artifact is not a supported FSIS profile."""


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _schema_fingerprint(headers: tuple[str, ...]) -> str:
    return hashlib.sha256(json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _csv(content: bytes) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    try:
        reader = csv.DictReader(content.decode("utf-8-sig").splitlines(), strict=True)
        headers = tuple(reader.fieldnames or ())
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise FsisContractError("malformed or unsupported UTF-8 CSV") from exc
    if not headers:
        raise FsisContractError("missing FSIS header")
    if None in headers or len(set(headers)) != len(headers):
        raise FsisContractError("duplicate or unnamed FSIS columns")
    if any(None in row for row in rows):
        raise FsisContractError("schema drift: row has extra columns")
    if not {"establishment_id", "establishment_name", "state"}.issubset(headers):
        raise FsisContractError("unsupported FSIS profile: missing facility identity fields")
    return headers, rows


def _record(row: dict[str, Any], line: int) -> dict[str, Any]:
    source_values = {str(key): value for key, value in row.items()}
    activities = tuple(key for key in sorted(ACTIVITY_COLUMNS) if _clean(row.get(key)))
    normalized = {
        "establishment_id": _clean(row.get("establishment_id")),
        "establishment_number": _clean(row.get("establishment_number")),
        "canonical_name": _clean(row.get("establishment_name")),
        "country_code": "US",
        "city": _clean(row.get("city")), "state": _clean(row.get("state")), "postal_code": _clean(row.get("zip")),
        "county": _clean(row.get("county")), "district": _clean(row.get("district")), "circuit": _clean(row.get("circuit")),
        "size": _clean(row.get("size")), "source_type": _clean(row.get("type")), "activities": activities,
        "activity_categories": tuple(sorted({"slaughter" if key.endswith("_slaughter") or key == "slaughter" else "processing" for key in activities})),
        "grant_date": _clean(row.get("grant_date")), "coordinates": None,
        "coordinate_state": "source-value-present-pending-review" if _clean(row.get("latitude")) or _clean(row.get("longitude")) else "unknown",
        "address_state": "source-address-retained-private-pending-review" if _clean(row.get("street")) else "unknown",
        "privacy_gate": "pending-review", "coordinate_gate": "review_required", "publication_gate": "blocked",
    }
    return {"source_id": CONFIG["source_id"], "source_row": line, "source_record_key": normalized["establishment_id"], "source_values": source_values, "normalized": normalized}


class FsisMpiAdapter:
    source_id = CONFIG["source_id"]
    adapter_version = CONFIG["adapter_version"]
    schema_version = CONFIG["contract_version"]

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        digest = hashlib.sha256(content).hexdigest()
        headers, rows = _csv(content)
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        keys = [_clean(row.get("establishment_id")) for row in rows]
        duplicates = {key for key, count in Counter(key for key in keys if key).items() if count > 1}
        for line, row in enumerate(rows, 2):
            reasons: list[str] = []
            identifier = _clean(row.get("establishment_id")); state = (_clean(row.get("state")) or "").upper()
            if not identifier: reasons.append("missing_establishment_id")
            if identifier in duplicates: reasons.append("duplicate_establishment_id")
            if state and state not in ALLOWED_STATES: reasons.append("unknown_state")
            if not _clean(row.get("establishment_name")): reasons.append("missing_establishment_name")
            record = _record(row, line)
            (quarantined if reasons else accepted).append({"reasons": tuple(dict.fromkeys(reasons)), "record": record} if reasons else record)
        return {"accepted": accepted, "quarantined": quarantined, "source_sha256": digest, "schema_fingerprint": _schema_fingerprint(headers), "headers": headers, "input_rows": len(rows)}

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes(); digest = hashlib.sha256(raw).hexdigest()
        if artifact.sha256 != digest or artifact.byte_size != len(raw): raise ValueError("artifact provenance mismatch")
        result = self.parse_bytes(raw); accepted = result["accepted"]; quarantined = result["quarantined"]
        parsed = accepted + [item["record"] for item in quarantined]
        _, parsed_sha, _ = atomic_jsonl(Path(run_dir) / "parsed/records.jsonl", parsed)
        _, normalized_sha, _ = atomic_jsonl(Path(run_dir) / "normalized/records.jsonl", accepted)
        atomic_jsonl(Path(run_dir) / "quarantined/records.jsonl", quarantined)
        anomalies = Counter(reason for item in quarantined for reason in item["reasons"])
        manifest = private_manifest(source_id=self.source_id, adapter_version=self.adapter_version, schema_version=self.schema_version, artifact=artifact, input_rows=result["input_rows"], normalized_rows=len(accepted), quarantined_rows=len(quarantined), normalized_sha256=normalized_sha, parsed_sha256=parsed_sha, anomaly_counts=dict(sorted(anomalies.items())))
        manifest.update({"schema_fingerprint": result["schema_fingerprint"], "source_profile": "fsis-mpi-directory-plus-demographics", "geocoding": "disabled", "coverage": "FSIS-regulated meat, poultry, and egg establishments in the captured edition; state-inspection programs and non-FSIS populations excluded"})
        atomic_json(Path(run_dir) / "manifest.json", manifest)
        return manifest

    def write_candidate_handoff(self, run_dir: str | Path, artifact: SourceArtifact, *, output_dir: str | Path | None = None) -> dict[str, Any]:
        root = Path(run_dir)
        rows = [json.loads(line) for line in (root / "normalized/records.jsonl").read_text(encoding="utf-8").splitlines() if line]
        return write_handoff(output_dir or root, rows, artifact, source_id=self.source_id, profile="us-fsis-test-only")
