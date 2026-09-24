"""Live acquisition and private candidate adapter for South Australia EPA licences.

This dataset is a South Australia environmental-licence overlay. Its activity
field is a broad Schedule 1 category, not an individual activity code. Rows are
included only when that exact category and a narrowly named regulated animal
activity in LICENCE_NAME agree. This is a candidate-selection rule, not proof
of a particular operation at a site.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.common.review import write_operator_review_packet
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_bytes, atomic_json, atomic_jsonl, private_manifest

SOURCE_ID = "au.sa.epa.licensed-activities"
SOURCE_TITLE = "EPA Licensed Activities"
SOURCE_URL = (
    "https://data.sa.gov.au/data/dataset/8fdb86ff-d3d1-4f9e-85a5-bed4080d5ee1/"
    "resource/26e076f3-c37f-4089-8f28-3f7c9afd997e/download/"
    "topo_epa_activities_wgs84.geojson"
)
CATALOG_URL = (
    "https://data.gov.au/data/api/3/action/package_show?"
    "id=https-www-waterconnect-sa-gov-au-content-downloads-dewnr-topo-epa-activities-sag-shp-zip"
)
RESOURCE_ID = "26e076f3-c37f-4089-8f28-3f7c9afd997e"
CATALOG_PACKAGE_ID = "8fdb86ff-d3d1-4f9e-85a5-bed4080d5ee1"
LICENSE_TITLE = "Creative Commons Attribution 3.0 Australia"
LICENSE_URL = "http://creativecommons.org/licenses/by/3.0/au/"
ADAPTER_VERSION = "au-sa-epa-licensed-activities-v1"
SCHEMA_VERSION = "au-sa-epa-geojson-v1"
COVERAGE = "South Australia only; EPA-licensed activities in the current resource, not a national or complete animal-facility register"
REQUIRED_PROPERTIES = {"OBJECTID", "EPALICENCE", "ACTIVITY", "LICENCE_NAME", "PR_LINK"}
ANIMAL_CATEGORY = "Animal Husbandry and Other Activities"
FOOD_CATEGORY = "Food Production and Animal Plant Processing"
KNOWN_CATEGORIES = {
    "Resource Recovery Waste Disposal and Related", "Hydrocarbon and Chemical",
    "Other", "Manufacturing and Mineral Processing", "Materials Handling and Transportation",
    FOOD_CATEGORY, ANIMAL_CATEGORY, "Desalination Plants", "Activities in Specified Areas",
    "Hydrocarbon and Chemica",
}

# The source supplies only these category labels, not the activity item. The
# precise named terms anchor a candidate to a known Schedule 1 animal-activity
# family; loose "animal", "farm", "food", or "processing" matches are barred.
INTENSIVE_TERMS = re.compile(r"\b(?:pigger(?:y|ies)|poultry|broiler|feedlot|hatchery)\b", re.I)
SLAUGHTER_TERMS = re.compile(r"\b(?:abattoir|abattoirs|slaughterhouse|slaughterhouses|slaughter works|slaughtering works)\b", re.I)
ANIMAL_PRODUCT_TERMS = re.compile(r"\b(?:meat|meatworks|rendering|fellmongery|animal products?|dairy|milk)\b", re.I)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _terms(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("source_id") != SOURCE_ID
            or data.get("decision") != "approved"
            or data.get("license") != LICENSE_TITLE
            or data.get("private_preview_only") is not True):
        raise ValueError("SA EPA terms review is missing or does not approve the exact private-only source and license")
    return data


def _request(url: str, *, timeout: float, max_bytes: int, opener: Any = None) -> tuple[bytes, dict[str, Any]]:
    parsed = urllib.parse.urlparse(url)
    allowed_host = "data.gov.au" if url == CATALOG_URL else "data.sa.gov.au"
    if parsed.scheme != "https" or parsed.hostname != allowed_host or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("SA EPA acquisition URL is outside the approved HTTPS host")
    request = urllib.request.Request(url, headers={"User-Agent": "UntilEveryCage-private-preview/1.0", "Accept": "application/json" if url == CATALOG_URL else "application/geo+json, application/json"})
    with (opener or urllib.request).urlopen(request, timeout=timeout) as response:
        final = urllib.parse.urlparse(response.geturl())
        if response.status < 200 or response.status >= 300 or final.scheme != "https" or final.hostname != allowed_host:
            raise ValueError("SA EPA response failed status or redirect validation")
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("SA EPA response exceeds the configured byte limit")
        headers = {str(k): str(v) for k, v in response.headers.items()}
        content_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        allowed_types = ({"application/json", "application/ld+json"} if url == CATALOG_URL
                         else {"application/geo+json", "application/json", "application/octet-stream"})
        if content_type not in allowed_types:
            raise ValueError("SA EPA response has an unsupported content type")
        metadata = {"requested_url": url, "final_url": response.geturl(), "response_headers": headers,
                    "content_type": headers.get("Content-Type"), "byte_size": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest()}
    return raw, metadata


def fetch(*, output_root: Path, run_id: str, terms_review_path: Path,
          timeout_seconds: float = 60.0, max_bytes: int = 64 * 1024 * 1024,
          opener: Any = None) -> dict[str, Any]:
    terms = _terms(terms_review_path)
    catalog_bytes, catalog_facts = _request(CATALOG_URL, timeout=timeout_seconds, max_bytes=4 * 1024 * 1024, opener=opener)
    catalog = json.loads(catalog_bytes.decode("utf-8", errors="strict"))
    if catalog.get("success") is not True or not isinstance(catalog.get("result"), dict):
        raise ValueError("SA EPA catalog metadata response is invalid")
    package = catalog["result"]
    resource = next((item for item in package.get("resources", []) if item.get("id") == RESOURCE_ID), None)
    if (package.get("id") != CATALOG_PACKAGE_ID
            or not isinstance(resource, dict) or resource.get("url") != SOURCE_URL
            or package.get("title") != SOURCE_TITLE
            or package.get("license_title") != LICENSE_TITLE
            or package.get("license_url") != LICENSE_URL
            or not resource.get("last_modified")):
        raise ValueError("SA EPA catalog title, resource URL, or license changed; acquisition is held for review")
    requested_at = _utc_now()
    raw, artifact_facts = _request(SOURCE_URL, timeout=timeout_seconds, max_bytes=max_bytes, opener=opener)
    target = output_root / SOURCE_ID / run_id
    target.mkdir(parents=True, exist_ok=True)
    artifact_path = target / "source.geojson"
    atomic_bytes(artifact_path, raw)
    retrieved_at = _utc_now()
    metadata = {
        "source_id": SOURCE_ID, "source_title": SOURCE_TITLE, "run_id": run_id,
        "acquisition_method": "official_catalog_verified_live_geojson_download",
        "catalog_url": CATALOG_URL, "catalog_final_url": catalog_facts["final_url"],
        "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        "catalog_metadata_modified": package.get("metadata_modified"),
        "catalog_resource_updated_at": resource.get("last_modified"),
        "catalog_resource_size_bytes": resource.get("size"),
        "requested_url": artifact_facts["requested_url"], "final_url": artifact_facts["final_url"],
        "canonical_url": SOURCE_URL, "retrieved_at_utc": retrieved_at, "requested_at_utc": requested_at,
        "publication_date": resource.get("last_modified"), "effective_date": resource.get("last_modified"),
        "resource_title": resource.get("name"), "license": package.get("license_title"),
        "license_url": package.get("license_url"), "coverage": COVERAGE,
        "rights_caveat": f"{LICENSE_TITLE}; attribute South Australia EPA and link the source resource; private preview only.",
        "privacy_caveat": "EPA points are approximate and unspecified precision; privacy and site-identity review remain pending.",
        "byte_size": artifact_facts["byte_size"], "sha256": artifact_facts["sha256"],
        "content_type": artifact_facts["content_type"], "response_headers": artifact_facts["response_headers"],
        "artifact_path": str(artifact_path), "terms_review": terms,
        "adapter_version": ADAPTER_VERSION, "config_version": SCHEMA_VERSION,
    }
    atomic_json(target / "acquisition-metadata.json", metadata)
    return metadata


def _key(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return str(int(value)) if float(value).is_integer() else str(value)
    text = str(value).strip()
    return text or None


def _animal_rule(activity: Any, title: Any) -> tuple[str | None, str | None]:
    if not isinstance(activity, str) or not isinstance(title, str):
        return None, None
    if activity == ANIMAL_CATEGORY and INTENSIVE_TERMS.search(title):
        return "intensive-animal-keeping", "Animal Husbandry and Other Activities + explicit piggery/poultry/broiler/feedlot/hatchery title term"
    if activity == FOOD_CATEGORY:
        if SLAUGHTER_TERMS.search(title):
            return "slaughtering", "Food Production and Animal Plant Processing + explicit abattoir/slaughter works title term"
        if ANIMAL_PRODUCT_TERMS.search(title):
            return "animal-product-processing", "Food Production and Animal Plant Processing + explicit meat/rendering/fellmongery/animal-product/dairy/milk title term"
    return None, None


class SouthAustraliaEpaAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION
    source_kind = "facility_master"
    source_url = SOURCE_URL
    coverage = COVERAGE

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        try:
            doc = json.loads(content.decode("utf-8-sig", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("malformed SA EPA GeoJSON") from error
        if doc.get("type") != "FeatureCollection" or not isinstance(doc.get("features"), list):
            raise ValueError("schema drift: expected a GeoJSON FeatureCollection")
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        coordinate_quarantine: list[dict[str, Any]] = []
        out_of_scope = rejected = 0
        activity_counts: Counter[str] = Counter()
        coordinate_counts: Counter[str] = Counter()
        observed_categories: set[str] = set()
        for row_number, feature in enumerate(doc["features"], start=1):
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                quarantined.append({"source_row": row_number, "reasons": ["invalid_feature_object"], "record": {"source_id": SOURCE_ID, "source_row": row_number, "source_record_key": f"invalid-row-{row_number}", "source_values": {}, "normalized": {}}})
                rejected += 1
                continue
            properties = feature.get("properties")
            if not isinstance(properties, dict):
                raise ValueError("schema drift: feature properties must be an object")
            if REQUIRED_PROPERTIES - set(properties):
                raise ValueError("schema drift: SA EPA feature is missing required properties")
            geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else {}
            if geometry.get("type") != "Point":
                raise ValueError("schema drift: SA EPA feature geometry is not a Point")
            activity = properties.get("ACTIVITY")
            title = properties.get("LICENCE_NAME")
            activity_key = activity.strip() if isinstance(activity, str) else ""
            if activity_key:
                observed_categories.add(activity_key)
            scope, scope_rule = _animal_rule(activity_key, title)
            source_values = {key: properties.get(key) for key in sorted(REQUIRED_PROPERTIES)}
            raw_coordinates = geometry.get("coordinates")
            reasons: list[str] = []
            if not scope:
                out_of_scope += 1
                quarantined.append({"source_row": row_number, "reasons": ["out_of_scope_animal_activity_rule"],
                                    "record": {"source_id": SOURCE_ID, "source_row": row_number,
                                               "source_record_key": f"out-of-scope-{row_number}",
                                               "source_values": source_values, "normalized": {}}})
                continue
            object_id = _key(properties.get("OBJECTID"))
            licence = _key(properties.get("EPALICENCE"))
            if not object_id:
                reasons.append("missing_objectid")
            if not licence:
                reasons.append("missing_epalicence")
            if not isinstance(activity, str) or not isinstance(title, str) or "PR_LINK" not in properties:
                reasons.append("required_property_missing")
            record_key = f"{licence or 'missing-license'}|{object_id or f'row-{row_number}'}"
            coordinates: dict[str, Any] = {}
            coordinate_reason = None
            if geometry.get("type") != "Point" or not isinstance(raw_coordinates, (list, tuple)) or len(raw_coordinates) < 2:
                coordinate_reason = "missing_or_non_point_geometry"
            else:
                try:
                    lon, lat = float(raw_coordinates[0]), float(raw_coordinates[1])
                except (TypeError, ValueError, OverflowError):
                    coordinate_reason = "unparseable_source_coordinates"
                else:
                    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                        coordinate_reason = "source_coordinates_out_of_range"
                    elif lat == 0 and lon == 0:
                        coordinate_reason = "zero_zero_source_coordinates"
                    elif not (-39.2 <= lat <= -25.2 and 128.5 <= lon <= 141.2):
                        coordinate_reason = "source_coordinates_outside_south_australia_envelope"
                    else:
                        coordinates = {"latitude": lat, "longitude": lon,
                                       "precision": "source-precision-unknown"}
            if coordinate_reason:
                coordinate_counts[coordinate_reason] += 1
                coordinate_quarantine.append({"source_row": row_number, "source_record_key": record_key,
                                              "reasons": [coordinate_reason], "source_coordinates": raw_coordinates})
            if reasons:
                quarantined.append({"source_row": row_number, "reasons": reasons,
                                    "record": {"source_id": SOURCE_ID, "source_row": row_number,
                                               "source_record_key": record_key, "source_values": source_values,
                                               "normalized": {}}})
                rejected += 1
                continue
            activity_counts[scope] += 1
            normalized = {
                "establishment_id": licence, "facility_grouping": "source-epa-licence-number",
                "country_code": "AU", "nation": "Australia", "region": "South Australia",
                "activity_categories": [activity_key], "activity_code": activity_key,
                "activity_description": scope, "activity_scope_rule": scope_rule,
                "source_observed_at": None, "source_activity_category": activity_key,
                "source_row_objectid": object_id, "source_canonical_url": properties.get("PR_LINK"),
                "coordinates": coordinates,
                "coordinate_state": "source-approximate-pending-review" if coordinates else "source-coordinate-claim-rejected",
                "coordinate_precision": "source-precision-unknown" if coordinates else "unresolved",
                "privacy_gate": "pending-review", "rights_gate": "CC BY 3.0 Australia; private-preview-only",
                "publication_gate": "blocked",
            }
            accepted.append({"source_id": SOURCE_ID, "source_row": row_number,
                            "source_record_key": record_key, "source_values": source_values,
                            "normalized": normalized})
        if observed_categories - KNOWN_CATEGORIES:
            raise ValueError("schema drift: SA EPA resource has an unrecognized ACTIVITY category")
        schema_fingerprint = hashlib.sha256(json.dumps({"properties": sorted(REQUIRED_PROPERTIES), "geometry": "Point",
                                                        "categories": sorted(observed_categories)}, separators=(",", ":")).encode()).hexdigest()
        return {"accepted": accepted, "quarantined": quarantined,
                "coordinate_quarantine": coordinate_quarantine, "coordinate_counts": dict(sorted(coordinate_counts.items())),
                "activity_counts": dict(sorted(activity_counts.items())),
                "observed_categories": sorted(observed_categories),
                "out_of_scope_rows": out_of_scope, "rejected_rows": rejected,
                "input_rows": len(doc["features"]),
                "schema_fingerprint": schema_fingerprint,
                "total_feature_count": len(doc["features"])}

    def write_candidate_handoff(self, run_dir: str | Path, artifact: SourceArtifact,
                                accepted: list[dict[str, Any]]) -> dict[str, Any]:
        return write_handoff(run_dir, accepted, artifact, source_id=SOURCE_ID,
                             emit_graph_candidates=False)

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != artifact.sha256 or len(raw) != artifact.byte_size:
            raise ValueError("SA EPA acquisition provenance mismatch")
        parsed = self.parse_bytes(raw)
        for row in parsed["accepted"]:
            row["normalized"]["source_observed_at"] = artifact.effective_date or artifact.publication_date
        root = Path(run_dir)
        accepted = parsed["accepted"]
        quarantined = parsed["quarantined"]
        _, parsed_hash, _ = atomic_jsonl(root / "parsed" / "records.jsonl", accepted + [item["record"] for item in quarantined])
        _, normalized_hash, _ = atomic_jsonl(root / "normalized" / "records.jsonl", accepted)
        atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        atomic_jsonl(root / "quarantined" / "coordinate-claims.jsonl", parsed["coordinate_quarantine"])
        manifest = private_manifest(
            source_id=SOURCE_ID, adapter_version=ADAPTER_VERSION, schema_version=SCHEMA_VERSION,
            artifact=artifact, input_rows=parsed["input_rows"], normalized_rows=len(accepted),
            quarantined_rows=len(quarantined), normalized_sha256=normalized_hash,
            parsed_sha256=parsed_hash, anomaly_counts={"out_of_scope_animal_activity_rule": parsed["out_of_scope_rows"], **parsed["coordinate_counts"]},
        )
        manifest.update({
            "source_title": SOURCE_TITLE, "canonical_url": SOURCE_URL, "license": LICENSE_TITLE,
            "license_url": LICENSE_URL, "coverage": COVERAGE, "activity_counts": parsed["activity_counts"],
            "source_feature_count": parsed["total_feature_count"], "accepted_rows": len(accepted),
            "rejected_rows": parsed["rejected_rows"], "out_of_scope_rows": parsed["out_of_scope_rows"],
            "quarantined_coordinate_claims": len(parsed["coordinate_quarantine"]),
            "coordinate_quarantine_reasons": parsed["coordinate_counts"],
            "observed_activity_categories": parsed["observed_categories"],
            "schema_fingerprint": parsed["schema_fingerprint"], "source_kind": "facility_master",
            "graph_relationships_emitted": 0, "geocoding": "disabled",
        })
        atomic_json(root / "manifest.json", manifest)
        write_operator_review_packet(root, manifest, source_scope=COVERAGE,
            checks=("source ACTIVITY is category-level; each included title match is only a regulated-activity candidate",
                    "SA EPA states points are approximate and may not represent large licensed areas",
                    "review personal/mixed-use names and locations before any broader access"),
            blockers=("private preview only; no public release or approval",
                      "source includes South Australia EPA licence categories only, not all Australian animal facilities",
                      "no verified cross-source identity or graph relationship contract; none emitted"))
        return manifest


__all__ = ["SOURCE_ID", "SOURCE_TITLE", "SOURCE_URL", "CATALOG_URL", "CATALOG_PACKAGE_ID", "LICENSE_TITLE", "LICENSE_URL",
           "ADAPTER_VERSION", "SCHEMA_VERSION", "COVERAGE", "SouthAustraliaEpaAdapter", "fetch"]
