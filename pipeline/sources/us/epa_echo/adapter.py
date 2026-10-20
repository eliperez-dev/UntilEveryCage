"""Private EPA ECHO CWA/livestock classification normalizer."""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

from . import SOURCE_ID
from .acquire import FIELDS, MAX_RECORDS, SIC_CODES

SCHEMA_VERSION = "us-epa-echo-facilities-cwa-animal-production-v1"
ADAPTER_VERSION = "us-epa-echo-animal-adapter-v1"
_NAICS = re.compile(r"(?<!\d)112\d{3}(?!\d)")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _codes(value: Any) -> list[str]:
    if value is None:
        return []
    return list(dict.fromkeys(re.findall(r"\d{4,6}", str(value))))


def _coordinate_pair(attributes: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    lat_raw, lon_raw = attributes.get("FAC_LAT"), attributes.get("FAC_LONG")
    if lat_raw in (None, "") and lon_raw in (None, ""):
        return None, None
    if lat_raw in (None, "") or lon_raw in (None, ""):
        return None, "incomplete_coordinate_pair"
    try:
        latitude, longitude = float(lat_raw), float(lon_raw)
    except (TypeError, ValueError):
        return None, "invalid_coordinate_pair"
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180) or (latitude == 0 and longitude == 0):
        return None, "coordinate_out_of_range_or_zero_zero"
    return {
        "latitude": latitude, "longitude": longitude,
        "precision": "source-precision-unknown",
        "collection_method": _text(attributes.get("FAC_COLLECTION_METHOD")),
        "reference_point": _text(attributes.get("FAC_REFERENCE_POINT")),
        "accuracy_meters": attributes.get("FAC_ACCURACY_METERS"),
    }, None


class EpaEchoAnimalAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        if not content or len(content) > 64 * 1024 * 1024:
            raise ValueError("EPA artifact is empty or exceeds the configured bound")
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        seen_registry_ids: set[str] = set()
        object_ids: set[int] = set()
        page_count = 0
        coordinate_rejections: Counter[str] = Counter()
        try:
            with zipfile.ZipFile(__import__("io").BytesIO(content)) as archive:
                names = archive.namelist()
                if len(names) < 3 or len(names) != len(set(names)) or any(Path(name).name != name for name in names):
                    raise ValueError("EPA response archive has an invalid entry layout")
                if names[:2] != ["result-count.json", "object-ids.json"]:
                    raise ValueError("EPA response archive metadata entries are missing")
                count_payload = json.loads(archive.read(names[0]))
                ids_payload = json.loads(archive.read(names[1]))
                expected_count = count_payload.get("count")
                expected_ids = ids_payload.get("objectIds")
                if not isinstance(expected_count, int) or not 1 <= expected_count <= MAX_RECORDS or not isinstance(expected_ids, list):
                    raise ValueError("EPA response archive count metadata is invalid")
                if len(expected_ids) != expected_count or len(set(expected_ids)) != expected_count:
                    raise ValueError("EPA response archive IDs do not reconcile")
                for name in names[2:]:
                    if not re.fullmatch(r"response-\d{4}\.json", name):
                        raise ValueError("EPA response archive contains an unsupported entry")
                    payload = json.loads(archive.read(name))
                    features = payload.get("features") if isinstance(payload, dict) else None
                    if not isinstance(features, list):
                        raise ValueError("EPA response archive feature page is invalid")
                    page_count += 1
                    for feature in features:
                        attributes = feature.get("attributes") if isinstance(feature, dict) else None
                        if not isinstance(attributes, dict) or any(field not in attributes for field in FIELDS):
                            raise ValueError("EPA feature schema drift")
                        object_id = attributes.get("OBJECTID")
                        registry_id = _text(attributes.get("REGISTRY_ID"))
                        if not isinstance(object_id, int) or object_id in object_ids:
                            raise ValueError("EPA feature has invalid or repeated object ID")
                        object_ids.add(object_id)
                        naics = _codes(attributes.get("CWA_NAICS"))
                        sics = _codes(attributes.get("CWA_SICS"))
                        matched_naics = [code for code in naics if _NAICS.fullmatch(code)]
                        matched_sics = [code for code in sics if code in SIC_CODES]
                        if _text(attributes.get("NPDES_FLAG")) != "Y" or not (matched_naics or matched_sics):
                            raise ValueError("EPA feature does not satisfy the selected permit and industry scope")
                        reasons = []
                        if not registry_id:
                            reasons.append("missing_epa_registry_id")
                        elif registry_id in seen_registry_ids:
                            reasons.append("duplicate_epa_registry_id")
                        else:
                            seen_registry_ids.add(registry_id)
                        coordinates, coordinate_issue = _coordinate_pair(attributes)
                        if coordinate_issue:
                            coordinate_rejections[coordinate_issue] += 1
                        source_values = {
                            "epa_registry_id": registry_id,
                            "npdes_ids": _text(attributes.get("NPDES_IDS")),
                            "cwa_permit_types": _text(attributes.get("CWA_PERMIT_TYPES")),
                            "cwa_naics": _text(attributes.get("CWA_NAICS")),
                            "cwa_sics": _text(attributes.get("CWA_SICS")),
                            "fac_naics_codes": _text(attributes.get("FAC_NAICS_CODES")),
                            "fac_sic_codes": _text(attributes.get("FAC_SIC_CODES")),
                        }
                        normalized = {
                            "establishment_id": registry_id,
                            "epa_registry_id": registry_id,
                            "facility_grouping": "epa-registry-id-source-scoped",
                            "facility_identity_state": "EPA-registry identifier; no cross-source merge performed",
                            "name": _text(attributes.get("FAC_NAME")),
                            "address": _text(attributes.get("FAC_STREET")),
                            "city": _text(attributes.get("FAC_CITY")),
                            "state": _text(attributes.get("FAC_STATE")),
                            "postal_code": _text(attributes.get("FAC_ZIP")),
                            "country_code": "US",
                            "coordinates": coordinates,
                            "coordinate_state": "source-value-present-pending-review" if coordinates else "unknown-or-source-coordinate-rejected",
                            "coordinate_gate": "review_required",
                            "coordinate_provenance_state": "EPA ECHO source-reported facility coordinate; origin and facility-point precision require review" if coordinates else "not-supplied-or-rejected",
                            "source_active_flag": _text(attributes.get("FAC_ACTIVE_FLAG")),
                            "source_active_flag_semantics": "EPA FRS flag only; not independent proof of current operation",
                            "regulated_program": "Clean Water Act / NPDES-associated ECHO record",
                            "industry_classification_basis": {
                                "naics_codes": matched_naics,
                                "sic_codes": matched_sics,
                                "matching_rule": "native CWA_NAICS prefix 112 or selected livestock/poultry CWA_SIC codes",
                            },
                            "facility_semantics": "livestock/poultry industry-classified facility associated with CWA/NPDES data; not confirmed CAFO",
                            "cafo_status": "not-established",
                            "operating_status": "not-established",
                            "privacy_gate": "pending-review",
                            "rights_gate": "review_required",
                            "publication_gate": "blocked",
                        }
                        record = {
                            "source_id": SOURCE_ID,
                            "source_row": object_id,
                            "source_record_key": registry_id or f"missing-registry-{object_id}",
                            "source_values": source_values,
                            "normalized": normalized,
                        }
                        (quarantined if reasons else accepted).append({"reasons": reasons, "record": record} if reasons else record)
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("malformed EPA response archive") from error
        if len(object_ids) != expected_count or object_ids != set(expected_ids):
            raise ValueError("EPA feature rows do not reconcile to captured object IDs")
        if expected_count and page_count == 0:
            raise ValueError("EPA response archive omitted feature pages")
        fingerprint = hashlib.sha256(json.dumps(FIELDS, separators=(",", ":")).encode()).hexdigest()
        return {
            "accepted": accepted, "quarantined": quarantined,
            "input_rows": expected_count, "response_pages": page_count,
            "coordinate_rejections": dict(sorted(coordinate_rejections.items())),
            "schema_fingerprint": fingerprint,
            "source_sha256": hashlib.sha256(content).hexdigest(),
        }

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        content = Path(raw_path).read_bytes()
        if hashlib.sha256(content).hexdigest() != artifact.sha256 or len(content) != artifact.byte_size:
            raise ValueError("artifact provenance mismatch")
        parsed = self.parse_bytes(content)
        accepted = parsed["accepted"]
        quarantined = parsed["quarantined"]
        all_records = accepted + [item["record"] for item in quarantined]
        root = Path(run_dir)
        _, parsed_hash, _ = atomic_jsonl(root / "parsed" / "records.jsonl", all_records)
        _, normalized_hash, _ = atomic_jsonl(root / "normalized" / "records.jsonl", accepted)
        atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        anomaly_counts = Counter(reason for item in quarantined for reason in item["reasons"])
        manifest = private_manifest(
            source_id=SOURCE_ID, adapter_version=self.adapter_version,
            schema_version=self.schema_version, artifact=artifact,
            input_rows=parsed["input_rows"], normalized_rows=len(accepted),
            quarantined_rows=len(quarantined), normalized_sha256=normalized_hash,
            parsed_sha256=parsed_hash, anomaly_counts=dict(sorted(anomaly_counts.items())),
        )
        manifest.update({
            "schema_fingerprint": parsed["schema_fingerprint"],
            "coverage": "EPA ECHO CWA/NPDES-associated facility records filtered by native livestock/poultry NAICS/SIC classifications; not a confirmed CAFO list or complete inventory",
            "coordinate_rejections": parsed["coordinate_rejections"],
            "response_pages": parsed["response_pages"],
            "geocoding": "disabled",
            "publication_state": "private-candidate",
            "publication_gate": "blocked",
        })
        atomic_json(root / "manifest.json", manifest)
        return manifest
