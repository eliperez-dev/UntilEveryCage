"""Private, profile-explicit APHIS Public Search Tool CSV adapter.

APHIS exports are observations, not a facility master. This adapter keeps
registrations, inspections, annual animal-use reports, and amended report
versions source-local and separate. It never geocodes, merges identities, or
turns an APHIS row into an FSIS facility candidate.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest


ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

PROFILES = {
    "registrations": ("Account Name", "Certificate Number", "Certificate Status"),
    "annual_reports": ("Account Name", "Certificate Number", "Registration Type", "Year"),
    "inspections": ("Account Name", "Certificate Number", "Certificate Status"),
}

# The current Public Search Tool's annual-report export is intentionally a
# compact animal-use table: it omits the registrant/status columns that appear
# in the older documented fixture shape.  Keep this schema explicit so the
# live export is accepted without guessing a facility identity from it.
CURRENT_ANNUAL_REQUIRED = ("Customer Number", "Certificate Number", "Year")
CURRENT_INSPECTION_REQUIRED = ("Customer Number", "Certificate Number", "Inspection Date")

CUSTOMER_COLUMNS = ("Customer Number", "Customer Number_x", "Customer Number_y")
AMENDMENT_COLUMNS = (
    "Amendment Number", "Amendment ID", "Amendment Date", "Amended",
    "Amendment", "Report Version", "Version",
)
NON_ANIMAL_COLUMNS = {
    "Account Name", "Certificate Number", "Certificate Status", "Status Date",
    "Registration Type", "License Type", "Year", *CUSTOMER_COLUMNS,
    *AMENDMENT_COLUMNS, "Address Line 1", "Address Line 2", "City-State-Zip",
    "County", "City", "State", "Zip", "latitude", "longitude",
    "Geocodio Latitude", "Geocodio Longitude", "Exception Report",
    "Inspection Date", "Direct NCIs", "Non-Critical NCIs", "Critical NCIs",
    "Teachable Moments", "Site Name", "Legal Name", "License-Registration Type",
}


class AphisContractError(ValueError):
    """The captured artifact is not a supported APHIS profile."""


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _schema_fingerprint(headers: tuple[str, ...]) -> str:
    return hashlib.sha256(json.dumps(headers, separators=(",", ":")).encode()).hexdigest()


def _read(content: bytes) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    try:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = tuple(reader.fieldnames or ())
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise AphisContractError("malformed or unsupported UTF-8 APHIS CSV") from exc
    if (
        not headers
        or any(not _clean(header) for header in headers)
        or None in headers
        or len(headers) != len(set(headers))
    ):
        raise AphisContractError("APHIS schema drift or malformed header")
    # DictReader represents short rows with None-valued cells and extra
    # columns with a None key. Both are schema failures, not missing source
    # values: a genuinely blank cell is represented by an empty string.
    if not rows:
        raise AphisContractError("APHIS export contains no data rows")
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise AphisContractError("APHIS schema drift or malformed row")
    return headers, rows


def _unsupported() -> str:
    raise AphisContractError("profile is unsupported")


def _profile(headers: tuple[str, ...]) -> str:
    if set(CURRENT_ANNUAL_REQUIRED).issubset(headers):
        return "annual_reports"
    if set(CURRENT_INSPECTION_REQUIRED).issubset(headers):
        return "inspections"
    matches = [profile for profile, required in PROFILES.items() if set(required).issubset(headers)]
    # License Type and Registration Type are the meaningful discriminator when
    # an export happens to contain the common identity/status columns.
    if "Registration Type" in headers:
        # The current registrant export uses Registration Type, while older
        # fixtures use License Type.  Year is the explicit discriminator for
        # the annual animal-use view; Registration Type alone is a registry.
        return "annual_reports" if "Year" in headers else "registrations"
    if "License Type" in headers:
        return "registrations" if "registrations" in matches else _unsupported()
    if "inspections" in matches:
        return "inspections"
    return _unsupported()


def _customer_values(row: dict[str, Any]) -> dict[str, str | None]:
    return {
        "customer_number": _clean(row.get("Customer Number")),
        "customer_number_x": _clean(row.get("Customer Number_x")),
        "customer_number_y": _clean(row.get("Customer Number_y")),
    }


def _certificate_or_customer(row: dict[str, Any]) -> str | None:
    certificate = _clean(row.get("Certificate Number"))
    customers = _customer_values(row)
    return certificate or customers["customer_number"] or customers["customer_number_y"] or customers["customer_number_x"]


def _year(row: dict[str, Any]) -> str | None:
    return _clean(row.get("Year"))


def _inspection_date(row: dict[str, Any]) -> str | None:
    return _clean(row.get("Status Date")) or _clean(row.get("Inspection Date"))


def _amendment_version(row: dict[str, Any]) -> str | None:
    """Return an explicit amendment/version token, never an inferred one."""
    for column in AMENDMENT_COLUMNS:
        value = _clean(row.get(column))
        if value:
            return f"{column}={value}"
    return None


def _is_amendment(row: dict[str, Any]) -> bool:
    marker = _amendment_version(row)
    if not marker:
        return False
    # A version/date/number is explicit. Boolean-ish flags only count when
    # the source says the row was amended; false remains a base report.
    column, value = marker.split("=", 1)
    if column in {"Amended", "Amendment"}:
        return value.casefold() in {"true", "yes", "y", "1", "amended"}
    return True


def _observation_key(profile: str, row: dict[str, Any]) -> str | None:
    identity = _certificate_or_customer(row)
    if not identity:
        return None
    customers = _customer_values(row)
    parts = [
        f"certificate={_clean(row.get('Certificate Number')) or 'unknown'}",
        f"customer={customers['customer_number'] or 'unknown'}",
        f"customer_x={customers['customer_number_x'] or 'unknown'}",
        f"customer_y={customers['customer_number_y'] or 'unknown'}",
    ]
    if profile in {"annual_reports", "amendments"}:
        parts.append(f"year={_year(row) or 'unknown'}")
        parts.append(f"version={_amendment_version(row) or 'original'}")
    elif profile == "inspections":
        # A certificate/customer can have multiple inspection observations over
        # time.  Keep those observations distinct when the source supplies its
        # observation date; an undated duplicate remains quarantine-worthy.
        parts.append(f"status_date={_inspection_date(row) or 'unknown'}")
    return f"{profile}|" + "|".join(parts)


def _evidence_type(profile: str, row: dict[str, Any]) -> str:
    return "amendments" if profile == "annual_reports" and _is_amendment(row) else profile


def _record(profile: str, row: dict[str, Any], line: int) -> dict[str, Any]:
    certificate = _clean(row.get("Certificate Number"))
    customers = _customer_values(row)
    customer = customers["customer_number"] or customers["customer_number_y"] or customers["customer_number_x"]
    observation_key = _observation_key(profile, row)
    evidence_type = _evidence_type(profile, row)
    animal_use_fields = tuple(sorted(key for key, value in row.items() if key not in NON_ANIMAL_COLUMNS and _clean(value)))
    normalized = {
        # APHIS identifiers are deliberately source-native. The generic
        # establishment_id field remains null so a facility importer cannot
        # silently reinterpret this evidence.
        "establishment_id": None,
        "source_observation_key": observation_key,
        "country_code": "US",
        "evidence_type": evidence_type,
        "profile": profile,
        "account_name": _clean(row.get("Account Name")) or _clean(row.get("Site Name")) or _clean(row.get("Legal Name")),
        "certificate_number": certificate,
        "customer_number": customer,
        "customer_number_x": customers["customer_number_x"],
        "customer_number_y": customers["customer_number_y"],
        "registration_or_license_type": (
            _clean(row.get("Registration Type"))
            or _clean(row.get("License Type"))
            or _clean(row.get("License-Registration Type"))
        ),
        "status": _clean(row.get("Certificate Status")),
        "status_date": _inspection_date(row),
        "report_year": _year(row),
        "amendment_version": _amendment_version(row),
        "amendment_state": "amended" if evidence_type == "amendments" else "original_or_not_supplied",
        "animal_use_fields_present": animal_use_fields,
        "awa_coverage_state": "source_profile_only_unknown_completeness",
        "awa_coverage_limitations": (
            "APHIS Animal Welfare Act public-search evidence only; not a census of all animal-use activity",
            "annual reports describe reported use for the supplied year and may be amended",
            "absence is not closure, non-use, or non-coverage",
            "registrations, inspections, annual reports, and amendments are separate evidence types",
        ),
        "coordinates": None,
        "address_state": "source-address-retained-private-pending-review",
        "privacy_gate": "pending-review",
        "coordinate_gate": "review_required",
        "publication_gate": "blocked",
    }
    return {
        "source_id": CONFIG["source_id"],
        "source_row": line,
        "source_record_key": f"{evidence_type}:{observation_key or 'unknown'}",
        "source_values": {str(key): value for key, value in row.items()},
        "normalized": normalized,
    }


class AphisPublicSearchAdapter:
    source_id = CONFIG["source_id"]
    adapter_version = CONFIG["adapter_version"]
    schema_version = CONFIG["contract_version"]

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        digest = hashlib.sha256(content).hexdigest()
        headers, rows = _read(content)
        profile = _profile(headers)
        records = [_record(profile, row, line) for line, row in enumerate(rows, 2)]
        keys = [record["normalized"]["source_observation_key"] for record in records]
        duplicates = {key for key, count in Counter(key for key in keys if key).items() if count > 1}
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        for record, row in zip(records, rows):
            normalized = record["normalized"]
            reasons: list[str] = []
            if not _certificate_or_customer(row):
                reasons.append("missing_certificate_or_customer_id")
            if normalized["source_observation_key"] in duplicates:
                reasons.append("duplicate_observation_id")
            if profile == "annual_reports" and not _year(row):
                reasons.append("missing_report_year")
            if reasons:
                quarantined.append({"reasons": tuple(dict.fromkeys(reasons)), "record": record})
            else:
                accepted.append(record)
        return {
            "accepted": accepted,
            "quarantined": quarantined,
            "profile": profile,
            "headers": headers,
            "schema_fingerprint": _schema_fingerprint(headers),
            "source_sha256": digest,
            "input_rows": len(rows),
            "evidence_type_counts": dict(sorted(Counter(record["normalized"]["evidence_type"] for record in accepted).items())),
        }

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if artifact.sha256 != digest or artifact.byte_size != len(raw):
            raise ValueError("artifact provenance mismatch")
        result = self.parse_bytes(raw)
        accepted = result["accepted"]
        quarantined = result["quarantined"]
        parsed = accepted + [item["record"] for item in quarantined]
        _, parsed_sha, _ = atomic_jsonl(Path(run_dir) / "parsed/records.jsonl", parsed)
        _, normalized_sha, _ = atomic_jsonl(Path(run_dir) / "normalized/records.jsonl", accepted)
        atomic_jsonl(Path(run_dir) / "quarantined/records.jsonl", quarantined)
        anomalies = Counter(reason for item in quarantined for reason in item["reasons"])
        manifest = private_manifest(
            source_id=self.source_id,
            adapter_version=self.adapter_version,
            schema_version=self.schema_version,
            artifact=artifact,
            input_rows=result["input_rows"],
            normalized_rows=len(accepted),
            quarantined_rows=len(quarantined),
            normalized_sha256=normalized_sha,
            parsed_sha256=parsed_sha,
            anomaly_counts=dict(sorted(anomalies.items())),
        )
        manifest.update({
            "source_profile": result["profile"],
            "evidence_type_counts": result["evidence_type_counts"],
            "schema_fingerprint": result["schema_fingerprint"],
            "entity_policy": CONFIG["entity_policy"],
            "geocoding": "disabled",
            "publication_gate": "blocked",
            "test_only": True,
            "coverage": "APHIS Animal Care public-search observations for the captured profile only; AWA coverage, currentness, completeness, and facility equivalence remain unknown; no FSIS/facility merge",
            "coverage_limitations": [
                "The public-search export is not a complete census of animal use or all AWA-regulated entities.",
                "An annual report covers the supplied reporting year and may be amended; missing years are not closure or non-use.",
                "Registrations, inspections, annual reports, and amendments remain separate evidence types.",
                "Addresses and coordinates are retained only in private source evidence pending privacy review.",
            ],
        })
        atomic_json(Path(run_dir) / "manifest.json", manifest)
        return manifest
