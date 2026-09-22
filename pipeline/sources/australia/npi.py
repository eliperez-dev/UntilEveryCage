"""Private, deterministic adapter for Australia's National Pollutant Inventory.

The NPI is an environmental reporting overlay, not a complete slaughter or
farm register.  This adapter preserves that distinction: ANZSIC and activity
values remain source evidence and are never promoted into a stronger facility
classification.  Acquisition is deliberately outside this module; callers
must provide a preserved local artifact and its provenance.
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
from collections import Counter
from pathlib import Path
from typing import Any

from pipeline.common.review import write_operator_review_packet
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest
from pipeline.contracts.adapter_contract import SourceArtifact


SOURCE_ID = "au.npi.facilities"
ADAPTER_VERSION = "au-npi-facilities-v1"
SCHEMA_VERSION = "au-npi-csv-v1"
SOURCE_URL = (
    "https://data.gov.au/data/dataset/043f58e0-a188-4458-b61c-04e5b540aea4"
)
REQUIRED_COLUMNS = {
    "facility_id", "jurisdiction_code", "jurisdiction_facility_id",
    "registered_business_name", "facility_name", "abn", "acn",
    "street_address", "suburb", "state", "postcode", "latitude",
    "longitude", "primary_anzsic_class_code", "primary_anzsic_class_name",
    "main_activities", "facility_website", "first_report_year",
    "latest_report_year", "latest_report_id", "latest_report_url", "reports",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _coordinate(row: dict[str, str]) -> tuple[float | None, float | None, str]:
    lat_text, lon_text = _clean(row.get("latitude")), _clean(row.get("longitude"))
    if not lat_text and not lon_text:
        return None, None, "not-supplied-by-source"
    try:
        lat, lon = float(lat_text), float(lon_text)
    except ValueError:
        return None, None, "invalid-source-coordinate"
    if not (math.isfinite(lat) and math.isfinite(lon)) or not (-44.0 <= lat <= -10.0 and 110.0 <= lon <= 155.0):
        return None, None, "invalid-source-coordinate"
    return lat, lon, "source"


class NpiFacilitiesAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION
    source_url = SOURCE_URL
    source_kind = "facility_master"
    coverage = "Australian NPI reporting facilities; environmental overlay, not complete animal-facility coverage"

    @staticmethod
    def validate_schema(content: bytes) -> str:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        headers = set(reader.fieldnames or ())
        missing = sorted(REQUIRED_COLUMNS - headers)
        if missing:
            raise ValueError("schema drift: missing NPI columns: " + ", ".join(missing))
        return hashlib.sha256("|".join(sorted(headers)).encode()).hexdigest()

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        schema_fingerprint = self.validate_schema(content)
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        seen: Counter[str] = Counter()
        for line, raw in enumerate(reader, start=2):
            row = {str(key): _clean(value) for key, value in raw.items() if key is not None}
            facility_id = _clean(row.get("facility_id"))
            seen[facility_id] += 1
            reasons: list[str] = []
            if not facility_id:
                reasons.append("missing_facility_id")
            elif seen[facility_id] > 1:
                reasons.append("duplicate_facility_id")
            lat, lon, coordinate_state = _coordinate(row)
            if coordinate_state == "invalid-source-coordinate":
                reasons.append("invalid_source_coordinate")
            record = {
                "source_id": SOURCE_ID,
                "source_row": line,
                "source_record_key": facility_id or f"row-{line}",
                "source_values": row,
                "normalized": {
                    "establishment_id": facility_id,
                    "name": _clean(row.get("facility_name")) or _clean(row.get("registered_business_name")),
                    "trading_name": _clean(row.get("facility_name")) or _clean(row.get("registered_business_name")),
                    "registered_business_name": _clean(row.get("registered_business_name")),
                    "facility_name": _clean(row.get("facility_name")),
                    "address": None,
                    "address_state": "source-value-present-pending-review" if _clean(row.get("street_address")) else "unknown",
                    "city": _clean(row.get("suburb")),
                    "postal_code": _clean(row.get("postcode")),
                    "state": _clean(row.get("state")),
                    "country_code": "AU",
                    "coordinates": {"latitude": lat, "longitude": lon} if lat is not None else None,
                    "coordinate_state": coordinate_state,
                    "primary_anzsic_class_code": _clean(row.get("primary_anzsic_class_code")),
                    "primary_anzsic_class_name": _clean(row.get("primary_anzsic_class_name")),
                    "main_activities": _clean(row.get("main_activities")),
                    "first_report_year": _clean(row.get("first_report_year")),
                    "latest_report_year": _clean(row.get("latest_report_year")),
                    "latest_report_id": _clean(row.get("latest_report_id")),
                    "observation_state": "listed-at-retrieval",
                    "classification_state": "source-reported-environmental-classification",
                    "privacy_gate": "pending-review",
                    "coordinate_gate": "review_required",
                    "publication_gate": "blocked",
                },
            }
            if reasons:
                quarantined.append({"reasons": tuple(reasons), "record": record})
            else:
                accepted.append(record)
        return {
            "accepted": accepted,
            "quarantined": quarantined,
            "input_rows": len(accepted) + len(quarantined),
            "schema_fingerprint": schema_fingerprint,
        }

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if artifact.sha256 != digest or artifact.byte_size != len(raw):
            raise ValueError("artifact provenance mismatch")
        parsed = self.parse_bytes(raw)
        accepted, quarantined = parsed["accepted"], parsed["quarantined"]
        root = Path(run_dir)
        parsed_rows = accepted + [item["record"] for item in quarantined]
        _, parsed_sha, _ = atomic_jsonl(root / "parsed" / "records.jsonl", parsed_rows)
        _, normalized_sha, _ = atomic_jsonl(root / "normalized" / "records.jsonl", accepted)
        atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        anomaly_counts = Counter(reason for item in quarantined for reason in item["reasons"])
        manifest = private_manifest(
            source_id=SOURCE_ID,
            adapter_version=ADAPTER_VERSION,
            schema_version=SCHEMA_VERSION,
            artifact=artifact,
            input_rows=parsed["input_rows"],
            normalized_rows=len(accepted),
            quarantined_rows=len(quarantined),
            normalized_sha256=normalized_sha,
            parsed_sha256=parsed_sha,
            anomaly_counts=dict(sorted(anomaly_counts.items())),
        )
        manifest.update({
            "country_code": "AU",
            "source_kind": "facility_master",
            "schema_fingerprint": parsed["schema_fingerprint"],
            "coverage": self.coverage,
            "geocoding": "disabled",
            "coordinate_counts": {"source": sum(item["normalized"]["coordinate_state"] == "source" for item in accepted), "unresolved": sum(item["normalized"]["coordinate_state"] != "source" for item in accepted)},
        })
        atomic_json(root / "manifest.json", manifest)
        write_operator_review_packet(
            root,
            manifest,
            source_scope=self.coverage,
            checks=(
                "keep NPI environmental reporting separate from complete facility registries",
                "review address and coordinate precision before any public map use",
                "treat ANZSIC and activities as source classifications, not proof of current operation",
                "attribute DCCEEW/Commonwealth source and confirm dataset-specific reuse",
            ),
            blockers=(
                "private candidate; no public projection",
                "no completeness claim for Australian animal facilities",
                "privacy, terms, and project publication approval remain pending",
            ),
        )
        return manifest
