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
import json
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.common.review import write_operator_review_packet
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_bytes, atomic_json, atomic_jsonl, private_manifest
from pipeline.contracts.adapter_contract import SourceArtifact


SOURCE_ID = "au.npi.facilities"
ADAPTER_VERSION = "au-npi-facilities-v3"
SCHEMA_VERSION = "au-npi-csv-v2"
SOURCE_URL = (
    "https://data.gov.au/data/dataset/043f58e0-a188-4458-b61c-04e5b540aea4"
)
CATALOG_URL = "https://data.gov.au/data/api/3/action/package_show?id=043f58e0-a188-4458-b61c-04e5b540aea4"
CATALOG_PACKAGE_ID = "043f58e0-a188-4458-b61c-04e5b540aea4"
RESOURCE_ID = "f83cdee9-ebcb-4f24-941b-34bb2f0996cf"
RESOURCE_URL = (
    "https://data.gov.au/data/dataset/043f58e0-a188-4458-b61c-04e5b540aea4/"
    "resource/f83cdee9-ebcb-4f24-941b-34bb2f0996cf/download/facilities.csv"
)
LICENSE_TITLE = "Creative Commons Attribution 4.0 International"
LICENSE_URL = "http://creativecommons.org/licenses/by/4.0"
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _terms(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("source_id") != SOURCE_ID
            or data.get("decision") != "approved"
            or data.get("license") != LICENSE_TITLE
            or data.get("private_preview_only") is not True):
        raise ValueError("NPI terms review does not authorize this exact source for private preview")
    return data


def _request(url: str, *, timeout: float, max_bytes: int, opener: Any = None) -> tuple[bytes, dict[str, Any]]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "data.gov.au" or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("NPI acquisition URL is outside the approved HTTPS host")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "UntilEveryCage-private-preview/1.0", "Accept": "application/json" if url == CATALOG_URL else "text/csv"},
    )
    with (opener or urllib.request).urlopen(request, timeout=timeout) as response:
        final_url = response.geturl()
        final = urllib.parse.urlparse(final_url)
        if response.status < 200 or response.status >= 300 or final.scheme != "https" or final.hostname != "data.gov.au":
            raise ValueError("NPI response failed status or redirect validation")
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("NPI response exceeds the configured byte limit")
        headers = {str(k): str(v) for k, v in response.headers.items()}
        content_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        allowed = {"application/json", "application/ld+json"} if url == CATALOG_URL else {"text/csv", "application/csv", "application/octet-stream"}
        if content_type not in allowed:
            raise ValueError("NPI response has an unsupported content type")
        metadata = {"requested_url": url, "final_url": final_url, "response_headers": headers,
                    "content_type": headers.get("Content-Type"), "byte_size": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest()}
    return raw, metadata


def fetch(*, output_root: Path, run_id: str, terms_review_path: Path,
          timeout_seconds: float = 60.0, max_bytes: int = 16 * 1024 * 1024,
          opener: Any = None) -> dict[str, Any]:
    """Verify the official catalogue and atomically retain its current CSV."""
    terms = _terms(terms_review_path)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
        raise ValueError("NPI acquisition run ID has an invalid format")
    target = output_root / SOURCE_ID / run_id
    if target.exists():
        raise FileExistsError("NPI acquisition run ID already exists; use a new ID to preserve retrieval history")
    catalog_bytes, catalog_facts = _request(CATALOG_URL, timeout=timeout_seconds, max_bytes=4 * 1024 * 1024, opener=opener)
    try:
        catalog = json.loads(catalog_bytes.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("NPI catalogue response is malformed") from error
    if catalog.get("success") is not True or not isinstance(catalog.get("result"), dict):
        raise ValueError("NPI catalogue response is invalid")
    package = catalog["result"]
    resource = next((item for item in package.get("resources", []) if item.get("id") == RESOURCE_ID), None)
    if (package.get("id") != CATALOG_PACKAGE_ID or package.get("title") != "National Pollutant Inventory"
            or package.get("license_title") != LICENSE_TITLE or package.get("license_url") != LICENSE_URL
            or not isinstance(resource, dict) or resource.get("format", "").upper() != "CSV"
            or resource.get("name") != "Facilities" or resource.get("url") != RESOURCE_URL
            or not resource.get("last_modified")):
        raise ValueError("NPI catalog title, CSV resource URL, update date, or licence changed; acquisition held for review")
    requested_at = _utc_now()
    raw, artifact_facts = _request(RESOURCE_URL, timeout=timeout_seconds, max_bytes=max_bytes, opener=opener)
    NpiFacilitiesAdapter.validate_schema(raw)
    target.mkdir(parents=True, exist_ok=False)
    artifact_path = target / "source.csv"
    atomic_bytes(artifact_path, raw)
    retrieved_at = _utc_now()
    metadata = {
        "source_id": SOURCE_ID, "source_title": "National Pollutant Inventory", "run_id": run_id,
        "acquisition_method": "official_catalog_verified_live_csv_download",
        "catalog_url": CATALOG_URL, "catalog_final_url": catalog_facts["final_url"],
        "catalog_sha256": catalog_facts["sha256"], "catalog_metadata_modified": package.get("metadata_modified"),
        "catalog_resource_updated_at": resource.get("last_modified"), "catalog_resource_size_bytes": resource.get("size"),
        "requested_url": artifact_facts["requested_url"], "final_url": artifact_facts["final_url"],
        "canonical_url": RESOURCE_URL, "requested_at_utc": requested_at, "retrieved_at_utc": retrieved_at,
        "publication_date": resource.get("last_modified"), "effective_date": resource.get("last_modified"),
        "resource_title": resource.get("name"), "license": package.get("license_title"),
        "license_url": package.get("license_url"),
        "rights_caveat": "CC BY 4.0; attribute Commonwealth of Australia, DCCEEW, and National Pollutant Inventory, with dataset source link; private preview only.",
        "privacy_caveat": "Facility addresses and source coordinates remain private and pending residential, mixed-use, and precision review.",
        "coverage": NpiFacilitiesAdapter.coverage,
        "byte_size": artifact_facts["byte_size"], "sha256": artifact_facts["sha256"],
        "content_type": artifact_facts["content_type"], "response_headers": artifact_facts["response_headers"],
        "artifact_path": str(artifact_path), "terms_review": terms,
        "adapter_version": ADAPTER_VERSION, "config_version": SCHEMA_VERSION,
    }
    atomic_json(target / "acquisition-metadata.json", metadata)
    return metadata


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


def _address_review_signals(value: str) -> list[str]:
    """Flag address text that needs review; never declare a site residential-safe."""
    text = value.casefold()
    signals = []
    if re.search(r"\b(?:po\s*box|p\.?\s*o\.?\s*box|locked\s+bag|postal\s+box)\b", text):
        signals.append("possible-mailing-address")
    if re.search(r"\b(?:unit|flat|apartment|apt\.?|suite|level|residence)\b", text):
        signals.append("possible-mixed-use-or-residential-address")
    return signals


class NpiFacilitiesAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION
    source_url = SOURCE_URL
    source_kind = "facility_master"
    coverage = "Australian NPI reporting facilities; environmental overlay, not complete animal-facility coverage"

    @staticmethod
    def validate_schema(content: bytes) -> str:
        try:
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="strict")), strict=True)
        except UnicodeDecodeError as error:
            raise ValueError("malformed or unsupported NPI CSV encoding") from error
        headers = set(reader.fieldnames or ())
        missing = sorted(REQUIRED_COLUMNS - headers)
        if missing:
            raise ValueError("schema drift: missing NPI columns: " + ", ".join(missing))
        return hashlib.sha256("|".join(sorted(headers)).encode()).hexdigest()

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        schema_fingerprint = self.validate_schema(content)
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="strict")), strict=True)
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        seen: Counter[str] = Counter()
        relevance_counts: Counter[str] = Counter()
        code_counts: Counter[str] = Counter()
        address_signal_counts: Counter[str] = Counter()
        for line, raw in enumerate(reader, start=2):
            if None in raw:
                raise ValueError("schema drift: NPI row contains extra fields")
            row = {str(key): _clean(value) for key, value in raw.items() if key is not None}
            facility_id = _clean(row.get("facility_id"))
            relevance = {
                "0171": "poultry-meat-farming-industry-candidate",
                "1111": "meat-processing-industry-candidate",
                "1112": "poultry-processing-industry-candidate",
                "1113": "cured-meat-smallgoods-industry-candidate",
                "1192": "animal-feed-industry-adjacent",
            }.get(_clean(row.get("primary_anzsic_class_code")), "not-indicated-by-primary-anzsic")
            relevance_counts[relevance] += 1
            code_counts[_clean(row.get("primary_anzsic_class_code")) or "unknown"] += 1
            address_signal_counts.update(_address_review_signals(_clean(row.get("street_address"))))
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
                    "address": _clean(row.get("street_address")),
                    "address_state": "source-value-present-pending-review" if _clean(row.get("street_address")) else "unknown",
                    "location_role": "source-reported-facility-location",
                    "location_semantics": "NPI reporting location; current facility operation and precise site identity are not independently established",
                    "residential_or_mixed_use_screen": "pending-human-review",
                    "address_review_signals": _address_review_signals(_clean(row.get("street_address"))),
                    "city": _clean(row.get("suburb")),
                    "postal_code": _clean(row.get("postcode")),
                    "state": _clean(row.get("state")),
                    "country_code": "AU",
                    # Source coordinates are preserved privately as location
                    # evidence. Scope and public release remain separate gates.
                    "coordinates": ({"latitude": lat, "longitude": lon, "precision": "source-precision-unknown"}
                                    if coordinate_state == "source" else None),
                    "coordinate_state": "source-value-present-pending-privacy-review" if coordinate_state == "source" else coordinate_state,
                    "coordinate_precision": "source-provided; precision semantics not documented" if coordinate_state == "source" else "unresolved",
                    "in_default_map_scope": False,
                    "map_scope_reason": "source coordinates require residential, mixed-use, site-identity, and precision review",
                    "primary_anzsic_class_code": _clean(row.get("primary_anzsic_class_code")),
                    "primary_anzsic_class_name": _clean(row.get("primary_anzsic_class_name")),
                    "animal_relevance": relevance,
                    "activity_categories": ["processing"] if _clean(row.get("primary_anzsic_class_code")) in {"1111", "1112", "1113"} else [],
                    "main_activities": _clean(row.get("main_activities")),
                    "first_report_year": _clean(row.get("first_report_year")),
                    "latest_report_year": _clean(row.get("latest_report_year")),
                    "latest_report_id": _clean(row.get("latest_report_id")),
                    "observation_state": "reported-in-source-snapshot; operational-status-unknown",
                    "operation_state": "unknown; NPI reporting does not prove current operation",
                    "classification_state": "source-reported-primary-anzsic; industry-code candidate only",
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
            "industry_relevance_counts": dict(sorted(relevance_counts.items())),
            "primary_anzsic_code_counts": dict(sorted(code_counts.items())),
            "address_review_signal_counts": dict(sorted(address_signal_counts.items())),
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
            "coordinate_counts": {
                "source_pairs_retained_in_private_source_values": sum(
                    bool(item["source_values"].get("latitude")) and bool(item["source_values"].get("longitude"))
                    for item in accepted
                ),
                "normalized_preview_pairs": sum(item["normalized"].get("coordinates") is not None for item in accepted),
                "privacy_review_pending": sum(item["normalized"]["coordinate_state"] == "source-value-present-pending-privacy-review" for item in accepted),
                "unresolved": sum(item["normalized"]["coordinate_state"] == "not-supplied-by-source" for item in accepted),
            },
            "public_projection": {"rows": 0, "edges": 0},
            "private_preview_only": True,
            "industry_relevance_counts": parsed["industry_relevance_counts"],
            "primary_anzsic_code_counts": parsed["primary_anzsic_code_counts"],
            "address_review_signal_counts": parsed["address_review_signal_counts"],
        })
        atomic_json(root / "manifest.json", manifest)
        write_handoff(root / "candidate-handoff", accepted, artifact, source_id=SOURCE_ID, emit_graph_candidates=False)
        write_operator_review_packet(
            root,
            manifest,
            source_scope=self.coverage,
            checks=(
                "keep NPI environmental reporting separate from complete facility registries",
                "review address and coordinate precision before any public map use",
            "treat ANZSIC and activities as source classifications, not proof of current operation",
            "review mailing-address and unit/residential address signals before any location display",
                "attribute DCCEEW/Commonwealth source and confirm dataset-specific reuse",
            ),
            blockers=(
                "private candidate; no public projection",
                "no completeness claim for Australian animal facilities",
                "privacy, terms, and project publication approval remain pending",
            ),
        )
        return manifest
