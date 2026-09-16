"""Private, profile-explicit APHIS Public Search Tool CSV adapter."""
from __future__ import annotations
import csv, hashlib, json
from collections import Counter
from pathlib import Path
from typing import Any
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
PROFILES = {
    "registrations": ("Account Name", "Customer Number", "Certificate Number", "License Type", "Certificate Status", "Status Date"),
    "annual_reports": ("Account Name", "Customer Number_y", "Certificate Number", "Registration Type", "Certificate Status", "Year"),
    "inspections": ("Account Name", "Customer Number", "Certificate Number", "Certificate Status", "Status Date"),
}

class AphisContractError(ValueError):
    pass

def _clean(value: Any) -> str | None:
    if value is None: return None
    value = str(value).strip()
    return value or None

def _read(content: bytes) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    try:
        reader = csv.DictReader(content.decode("utf-8-sig").splitlines(), strict=True)
        headers = tuple(reader.fieldnames or ()); rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise AphisContractError("malformed or unsupported APHIS CSV") from exc
    if not headers or None in headers or len(headers) != len(set(headers)) or any(None in row for row in rows):
        raise AphisContractError("APHIS schema drift or malformed row")
    return headers, rows

def _profile(headers: tuple[str, ...]) -> str:
    if "License Type" in headers and set(PROFILES["registrations"]).issubset(headers):
        return "registrations"
    if "Registration Type" in headers and set(PROFILES["annual_reports"]).issubset(headers):
        return "annual_reports"
    if set(PROFILES["inspections"]).issubset(headers):
        return "inspections"
    raise AphisContractError("profile is unsupported")

def _observation_key(profile: str, row: dict[str, Any]) -> str | None:
    key = _clean(row.get("Certificate Number")) or _clean(row.get("Customer Number")) or _clean(row.get("Customer Number_y"))
    if key and profile == "annual_reports":
        return f"{key}:{_clean(row.get('Year'))}"
    return key

def _record(profile: str, row: dict[str, Any], line: int) -> dict[str, Any]:
    certificate = _clean(row.get("Certificate Number"))
    customer = _clean(row.get("Customer Number")) or _clean(row.get("Customer Number_y"))
    key = certificate or customer
    observation_key = _observation_key(profile, row)
    normalized = {
        "establishment_id": None,
        "source_observation_key": observation_key,
        "country_code": "US",
        "evidence_type": profile,
        "account_name": _clean(row.get("Account Name")),
        "certificate_number": certificate,
        "customer_number": customer,
        "registration_or_license_type": _clean(row.get("Registration Type")) or _clean(row.get("License Type")),
        "status": _clean(row.get("Certificate Status")),
        "status_date": _clean(row.get("Status Date")),
        "report_year": _clean(row.get("Year")),
        "animal_use_fields_present": tuple(sorted(key for key, value in row.items() if key not in {"Account Name", "Customer Number", "Customer Number_y", "Certificate Number", "Registration Type", "License Type", "Certificate Status", "Status Date", "Year", "Address Line 1", "Address Line 2", "City-State-Zip", "County", "City", "State", "Zip", "latitude", "longitude", "Geocodio Latitude", "Geocodio Longitude", "Exception Report"} and _clean(value))),
        "coordinates": None,
        "address_state": "source-address-retained-private-pending-review",
        "privacy_gate": "pending-review",
        "coordinate_gate": "review_required",
        "publication_gate": "blocked",
    }
    return {"source_id": CONFIG["source_id"], "source_row": line, "source_record_key": f"{profile}:{observation_key or 'unknown'}", "source_values": {str(k): v for k, v in row.items()}, "normalized": normalized}

class AphisPublicSearchAdapter:
    source_id = CONFIG["source_id"]
    adapter_version = CONFIG["adapter_version"]
    schema_version = CONFIG["contract_version"]

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        digest = hashlib.sha256(content).hexdigest(); headers, rows = _read(content); profile = _profile(headers)
        keys = [_observation_key(profile, row) for row in rows]
        duplicates = {key for key, count in Counter(key for key in keys if key).items() if count > 1}
        accepted=[]; quarantined=[]
        for line, row in enumerate(rows, 2):
            key = (_clean(row.get("Certificate Number")) or _clean(row.get("Customer Number")) or _clean(row.get("Customer Number_y")))
            duplicate_key = _observation_key(profile, row)
            reasons=[]
            if not key: reasons.append("missing_certificate_or_customer_id")
            if duplicate_key is not None and duplicate_key in duplicates: reasons.append("duplicate_observation_id")
            if profile == "annual_reports" and not _clean(row.get("Year")): reasons.append("missing_report_year")
            record = _record(profile, row, line); (quarantined if reasons else accepted).append({"reasons": tuple(dict.fromkeys(reasons)), "record": record} if reasons else record)
        return {"accepted": accepted, "quarantined": quarantined, "profile": profile, "headers": headers, "schema_fingerprint": hashlib.sha256(json.dumps(headers, separators=(",", ":")).encode()).hexdigest(), "source_sha256": digest, "input_rows": len(rows)}

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw=Path(raw_path).read_bytes(); digest=hashlib.sha256(raw).hexdigest()
        if artifact.sha256 != digest or artifact.byte_size != len(raw): raise ValueError("artifact provenance mismatch")
        result=self.parse_bytes(raw); accepted=result["accepted"]; quarantined=result["quarantined"]; parsed=accepted+[item["record"] for item in quarantined]
        _, parsed_sha, _=atomic_jsonl(Path(run_dir)/"parsed/records.jsonl", parsed); _, normalized_sha, _=atomic_jsonl(Path(run_dir)/"normalized/records.jsonl", accepted); atomic_jsonl(Path(run_dir)/"quarantined/records.jsonl", quarantined)
        anomalies=Counter(reason for item in quarantined for reason in item["reasons"])
        manifest=private_manifest(source_id=self.source_id, adapter_version=self.adapter_version, schema_version=self.schema_version, artifact=artifact, input_rows=result["input_rows"], normalized_rows=len(accepted), quarantined_rows=len(quarantined), normalized_sha256=normalized_sha, parsed_sha256=parsed_sha, anomaly_counts=dict(sorted(anomalies.items())))
        manifest.update({"source_profile": result["profile"], "schema_fingerprint": result["schema_fingerprint"], "entity_policy": CONFIG["entity_policy"], "geocoding": "disabled", "coverage": f"APHIS Public Search Tool {result['profile']} observations only; other APHIS profiles excluded"})
        atomic_json(Path(run_dir)/"manifest.json", manifest); return manifest
