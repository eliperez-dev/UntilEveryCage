"""Private adapter for the MPI Registered Risk Management Programmes export."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

SOURCE_ID = "nz.locations"
SOURCE_URL = (
    "https://mpi.my.site.com/publicregister/s/RiskMeasureSearch"
    "?riskMeasureType=Risk%20Management%20Programme"
)
ADAPTER_VERSION = "nz-mpi-rmp-csv-v3"
SCHEMA_VERSION = "nz-mpi-rmp-extract-2026-10-v1"
HEADERS = (
    "MPI ID Number", "Risk Measure Type", "Programme Type", "Operator Business Name",
    "Operator Trading Name", "NZBN", "Status", "Effective Date", "Expiry Date",
    "Verification Agency", "Is Suspended", "Suspension Type", "Suspension Start Date",
    "Suspension End Date", "Suspended Operations", "Physical Address", "Physical Town/City",
    "Operator Local Authority", "Number of Locations", "Location Local Authority", "Dairy ULIs",
    "Fishing Vessel Name", "Intended Use", "Product/Material", "Primary", "Secondary Process", "Market",
)

# These are source-native activity/product words, not inferred project labels.
# Generic entries such as "Custom", "Food", "Storage" or "Transport" alone
# do not qualify a row for the animal-industry subset.
_ANIMAL_SCOPE = (
    "animal", "meat", "poultry", "slaughter", "abattoir", "dairy", "milk", "egg",
    "bee", "honey", "fish", "seafood", "aquatic", "shellfish", "venison", "beef",
    "lamb", "pork", "chicken", "render", "hide", "skin", "game", "gelatin", "gelatine",
)
_TRUE = {"true", "yes", "y", "1"}
_FALSE = {"false", "no", "n", "0"}


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value and value not in {"-", "—"} else None


def _source_row_id(row: dict[str, str], occurrence: int) -> str:
    payload = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"{payload}|{occurrence}".encode("utf-8")).hexdigest()


def _in_animal_scope(row: dict[str, str]) -> bool:
    evidence = " ".join(
        _clean(row.get(key)) or ""
        for key in ("Programme Type", "Product/Material", "Primary", "Secondary Process", "Intended Use")
    ).casefold()
    return any(term in evidence for term in _ANIMAL_SCOPE)


class NewZealandRmpAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        try:
            text = content.decode("utf-8-sig", errors="strict")
            reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
            headers = tuple(reader.fieldnames or ())
            if headers != HEADERS:
                raise ValueError("schema drift")
            rows = list(reader)
        except (UnicodeDecodeError, csv.Error) as error:
            raise ValueError("malformed or unsupported UTF-8 MPI RMP CSV") from error

        occurrences: Counter[str] = Counter()
        identifiers: Counter[str] = Counter(
            value for row in rows if (value := _clean(row.get("MPI ID Number"))) is not None
        )
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        activity_counts: Counter[str] = Counter()
        multi_location_rows = 0
        missing_identifiers = 0
        invalid_location_counts = 0
        for line_number, row in enumerate(rows, 2):
            if None in row or any(not isinstance(value, str) for value in row.values()):
                raise ValueError("schema drift: row has an unexpected field count")
            source_values = {key: row.get(key, "") for key in HEADERS}
            mpi_id = _clean(row.get("MPI ID Number"))
            row_fingerprint = json.dumps(source_values, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            occurrences[row_fingerprint] += 1
            reasons: list[str] = []
            if not mpi_id:
                missing_identifiers += 1
                reasons.append("missing_mpi_id_number")
            elif identifiers[mpi_id] > 1:
                reasons.append("duplicate_mpi_id_number")

            # The register is RMP-based.  Retain all native programme and
            # product fields, but exclude generic custom/business rows unless
            # the source itself gives an animal-product category or activity.
            in_scope = _in_animal_scope(row)
            if not in_scope:
                reasons.append("outside_narrow_animal_product_scope")

            raw_suspended = (_clean(row.get("Is Suspended")) or "").casefold()
            if raw_suspended and raw_suspended not in _TRUE | _FALSE:
                reasons.append("invalid_suspension_flag")
            suspended = raw_suspended in _TRUE if raw_suspended in _TRUE | _FALSE else None

            locations_raw = _clean(row.get("Number of Locations"))
            location_count: int | None = None
            if locations_raw:
                try:
                    location_count = int(locations_raw)
                    if location_count < 1:
                        raise ValueError
                except ValueError:
                    invalid_location_counts += 1
                    reasons.append("invalid_number_of_locations")
                    location_count = None
            if location_count and location_count > 1:
                multi_location_rows += 1

            activity = _clean(row.get("Programme Type")) or _clean(row.get("Product/Material")) or "unclassified"
            activity_counts[activity] += 1
            source_row_id = _source_row_id(source_values, occurrences[row_fingerprint])
            normalized = {
                "establishment_id": mpi_id,
                "mpi_risk_measure_id": mpi_id,
                "source_entity_type": "registered-risk-management-programme",
                "facility_identity_state": "programme-record; location cardinality is source-reported and may be multiple",
                "name": _clean(row.get("Operator Business Name")),
                "trading_name": _clean(row.get("Operator Trading Name")),
                "business_identifier": _clean(row.get("NZBN")),
                "business_identifier_type": "nzbn",
                "country_code": "NZ",
                "nation": "New Zealand",
                "risk_measure_type": _clean(row.get("Risk Measure Type")),
                "programme_type": _clean(row.get("Programme Type")),
                "product_material": _clean(row.get("Product/Material")),
                "primary_activity": _clean(row.get("Primary")),
                "secondary_activity": _clean(row.get("Secondary Process")),
                "intended_use": _clean(row.get("Intended Use")),
                "market": _clean(row.get("Market")),
                "status": _clean(row.get("Status")),
                "status_state": "source-value-preserved; does not prove current operation",
                "is_suspended": suspended,
                "effective_date": _clean(row.get("Effective Date")),
                "expiry_date": _clean(row.get("Expiry Date")),
                "suspension_type": _clean(row.get("Suspension Type")),
                "suspension_start_date": _clean(row.get("Suspension Start Date")),
                "suspension_end_date": _clean(row.get("Suspension End Date")),
                "suspended_operations": _clean(row.get("Suspended Operations")),
                "verification_agency": _clean(row.get("Verification Agency")),
                "address": _clean(row.get("Physical Address")),
                "address_state": "source-address; restricted pending privacy review" if _clean(row.get("Physical Address")) else "not-supplied",
                "location_role": "RMP-associated physical address; not verified as a unique operating facility",
                "municipality": _clean(row.get("Physical Town/City")),
                "operator_local_authority": _clean(row.get("Operator Local Authority")),
                "location_local_authority": _clean(row.get("Location Local Authority")),
                "location_count": location_count,
                "location_count_state": "source-reported" if location_count is not None else "unknown",
                "private_location_evidence": {
                    "address": _clean(row.get("Physical Address")),
                    "city": _clean(row.get("Physical Town/City")),
                    "country_code": "NZ",
                    "number_of_locations": row.get("Number of Locations", ""),
                    "location_count": location_count,
                },
                "dairy_ulis": _clean(row.get("Dairy ULIs")),
                "fishing_vessel_name": _clean(row.get("Fishing Vessel Name")),
                "activity_scope_state": "matched-source-native-animal-product-category" if in_scope else "not-in-narrow-source-subset",
                "classification_state": "source-native-values-preserved; no project activity mapping applied",
                "coordinates": None,
                "coordinate_state": "not-supplied-by-source",
                "coordinate_provenance_state": "not-supplied",
                "privacy_gate": "pending-review",
                "rights_gate": "review_required",
                "coordinate_gate": "review_required",
                "publication_gate": "blocked",
            }
            record = {
                "source_id": self.source_id,
                "source_row": line_number,
                "source_row_id": source_row_id,
                "source_record_key": mpi_id or source_row_id,
                "source_values": source_values,
                "normalized": normalized,
            }
            if reasons:
                quarantined.append({"reasons": tuple(dict.fromkeys(reasons)), "record": record})
            else:
                accepted.append(record)

        fingerprint = hashlib.sha256(json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        return {
            "accepted": accepted,
            "quarantined": quarantined,
            "input_rows": len(rows),
            "schema_fingerprint": fingerprint,
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "activity_counts": dict(sorted(activity_counts.items())),
            "multi_location_rows": multi_location_rows,
            "missing_identifiers": missing_identifiers,
            "invalid_location_counts": invalid_location_counts,
            "coordinate_columns": 0,
        }

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if artifact.sha256 != digest or artifact.byte_size != len(raw):
            raise ValueError("artifact provenance mismatch")
        parsed = self.parse_bytes(raw)
        root = Path(run_dir)
        accepted, quarantined = parsed["accepted"], parsed["quarantined"]
        all_rows = accepted + [item["record"] for item in quarantined]
        _, parsed_hash, _ = atomic_jsonl(root / "parsed" / "records.jsonl", all_rows)
        _, normalized_hash, _ = atomic_jsonl(root / "normalized" / "records.jsonl", accepted)
        atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        reasons = Counter(reason for item in quarantined for reason in item["reasons"])
        manifest = private_manifest(
            source_id=self.source_id, adapter_version=self.adapter_version,
            schema_version=self.schema_version, artifact=artifact,
            input_rows=parsed["input_rows"], normalized_rows=len(accepted),
            quarantined_rows=len(quarantined), normalized_sha256=normalized_hash,
            parsed_sha256=parsed_hash, anomaly_counts=dict(sorted(reasons.items())),
        )
        manifest.update({
            "schema_fingerprint": parsed["schema_fingerprint"],
            "coverage": "MPI RMP observations with explicit animal-product programme/product/activity terms; not a complete premises census",
            "geocoding": "disabled",
            "multi_location_rows": parsed["multi_location_rows"],
            "activity_counts": parsed["activity_counts"],
            "missing_identifiers": parsed["missing_identifiers"],
            "invalid_location_counts": parsed["invalid_location_counts"],
            "source_coordinate_columns": parsed["coordinate_columns"],
            "source_rows_are_programmes_not_unique_facilities": True,
        })
        atomic_json(root / "manifest.json", manifest)
        return manifest

    def write_candidate_handoff(self, run_dir: str | Path, artifact: SourceArtifact,
                                parsed: dict[str, Any]) -> dict[str, Any]:
        # RMP rows can cover several sites and this export provides no points;
        # do not manufacture one facility graph candidate from each programme.
        return write_handoff(run_dir, parsed["accepted"], artifact, source_id=self.source_id,
                             emit_graph_candidates=False)
