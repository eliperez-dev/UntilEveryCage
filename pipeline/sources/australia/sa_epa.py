"""Private adapter for South Australia EPA licensed activity points.

The source reports approximate points and repeats licence identifiers across
activities. Licence records and their activity observations stay distinct;
this is an environmental overlay, never proof of animal use or operation.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from pipeline.common.review import write_operator_review_packet
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

SOURCE_ID = "au.sa.epa.licensed-activities"
ADAPTER_VERSION = "au-sa-epa-licensed-activities-v1"
SCHEMA_VERSION = "au-sa-epa-geojson-v1"
SOURCE_URL = "https://data.sa.gov.au/data/dataset/8fdb86ff-d3d1-4f9e-85a5-bed4080d5ee1"
RESOURCE_URL = "https://data.sa.gov.au/data/dataset/8fdb86ff-d3d1-4f9e-85a5-bed4080d5ee1/resource/26e076f3-c37f-4089-8f28-3f7c9afd997e/download/topo_epa_activities_wgs84.geojson"
REQUIRED_PROPERTIES = {"OBJECTID", "EPALICENCE", "ACTIVITY", "LICENCE_NAME", "PR_LINK"}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _point(geometry: Any) -> tuple[float | None, float | None, str]:
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        return None, None, "unresolved-geometry"
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        return None, None, "unresolved-geometry"
    try:
        lon, lat = float(coords[0]), float(coords[1])
    except (TypeError, ValueError):
        return None, None, "unresolved-coordinate"
    if not (math.isfinite(lon) and math.isfinite(lat) and 129 <= lon <= 141 and -39 <= lat <= -25):
        return None, None, "unresolved-coordinate"
    # The source explicitly describes these points as approximate. Do not
    # promote them to exact facility coordinates or geocode from them.
    return round(lat, 2), round(lon, 2), "approximate-source-point"


class SaEpaLicensedActivitiesAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION
    source_url = SOURCE_URL
    source_kind = "facility_master"
    coverage = "South Australia EPA licensed activities; approximate points, not a meat or animal-facility census"

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("malformed GeoJSON") from exc
        if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
            raise ValueError("schema drift: expected GeoJSON FeatureCollection")
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        seen_object_ids: set[str] = set()
        licences: dict[str, dict[str, Any]] = {}
        child_keys: set[tuple[str, str]] = set()
        schema_fields: set[str] = set()
        for index, feature in enumerate(payload["features"], 1):
            props = feature.get("properties") if isinstance(feature, dict) else None
            props = props if isinstance(props, dict) else {}
            reasons: list[str] = []
            if not REQUIRED_PROPERTIES <= set(props):
                raise ValueError("schema drift: missing required EPA properties")
            schema_fields.update(props)
            object_id, licence = _text(props.get("OBJECTID")), _text(props.get("EPALICENCE"))
            activity = _text(props.get("ACTIVITY"))
            if not object_id:
                reasons.append("missing_object_id")
            elif object_id in seen_object_ids:
                reasons.append("duplicate_object_id")
            else:
                seen_object_ids.add(object_id)
            if not licence:
                reasons.append("missing_licence_id")
            if not activity:
                reasons.append("missing_activity")
            lat, lon, point_state = _point(feature.get("geometry") if isinstance(feature, dict) else None)
            if point_state.startswith("unresolved"):
                reasons.append(point_state.replace("-", "_"))
            record = {
                "source_id": SOURCE_ID,
                "source_row": index,
                "source_record_key": f"{licence or 'unknown'}|{object_id or f'row-{index}' }",
                "source_values": {"properties": props, "geometry": feature.get("geometry") if isinstance(feature, dict) else None},
                "normalized": {
                    "licence_id": licence,
                    "establishment_id": licence,
                    "activity_observation_id": object_id,
                    "activity": activity,
                    "licence_name": _text(props.get("LICENCE_NAME")),
                    "public_register_link": _text(props.get("PR_LINK")),
                    "country_code": "AU",
                    "state": "SA",
                    "coordinates": {"latitude": lat, "longitude": lon} if lat is not None else None,
                    "coordinate_state": point_state,
                    "coordinate_precision": "coarse-approximate-0.01-degree",
                    "privacy_gate": "review-required",
                    "publication_gate": "blocked",
                    "observation_unit": "licence_activity",
                    "licence_aggregation": "parent-licence; activity rows retained as children",
                },
            }
            if reasons:
                quarantined.append({"reasons": tuple(reasons), "record": record})
                continue
            assert licence is not None and activity is not None and object_id is not None
            child = (licence, object_id)
            if child in child_keys:
                quarantined.append({"reasons": ("duplicate_licence_activity_observation",), "record": record})
                continue
            child_keys.add(child)
            parent = licences.setdefault(licence, {
                "source_id": SOURCE_ID,
                "source_row": index,
                "source_record_key": licence,
                "normalized": {
                    "licence_id": licence,
                    "establishment_id": licence,
                    "licence_name": _text(props.get("LICENCE_NAME")),
                    "public_register_link": _text(props.get("PR_LINK")),
                    "country_code": "AU", "state": "SA",
                    "observation_unit": "environmental_licence",
                    "activity_observations": [],
                    "coordinates": {"latitude": lat, "longitude": lon},
                    "coordinate_state": point_state,
                    "coordinate_precision": "coarse-approximate-0.01-degree",
                    "privacy_gate": "review-required", "publication_gate": "blocked",
                },
                "source_values": {"licence_id": licence},
            })
            child_observation = {
                "source_record_key": f"{licence}|{object_id}", "activity": activity, "object_id": object_id,
                "licence_name": _text(props.get("LICENCE_NAME")),
                "public_register_link": _text(props.get("PR_LINK")),
                "coordinates": {"latitude": lat, "longitude": lon},
                "coordinate_state": point_state,
            }
            parent["normalized"]["activity_observations"].append(child_observation)
            if parent["normalized"]["coordinates"] != child_observation["coordinates"]:
                parent["normalized"]["coordinates"] = None
                parent["normalized"]["coordinate_state"] = "ambiguous-within-licence"
            names = parent["normalized"].setdefault("licence_name_values", [])
            if child_observation["licence_name"] is not None and child_observation["licence_name"] not in names:
                names.append(child_observation["licence_name"])
            if len(names) > 1:
                parent["normalized"]["licence_name"] = None
                parent["normalized"]["licence_name_state"] = "conflicting-source-values"
            else:
                parent["normalized"]["licence_name_state"] = "single-source-value"
            accepted.append(record)
        parents = list(licences.values())
        for parent in parents:
            parent["normalized"]["activity_observations"].sort(key=lambda item: (item["activity"], item["source_record_key"]))
            parent["normalized"]["licence_name_values"].sort()
        fingerprint = hashlib.sha256(json.dumps(sorted(schema_fields) + ["geometry:Point"], separators=(",", ":")).encode()).hexdigest()
        return {"accepted": accepted, "quarantined": quarantined, "licences": parents,
                "input_rows": len(payload["features"]), "schema_fingerprint": fingerprint,
                "licence_count": len(parents), "activity_observation_count": len(accepted)}

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        if artifact.sha256 != hashlib.sha256(raw).hexdigest() or artifact.byte_size != len(raw):
            raise ValueError("artifact provenance mismatch")
        parsed = self.parse_bytes(raw)
        root = Path(run_dir)
        all_rows = parsed["licences"] + parsed["accepted"] + [entry["record"] for entry in parsed["quarantined"]]
        _, parsed_sha, _ = atomic_jsonl(root / "parsed" / "records.jsonl", all_rows)
        # Shared lifecycle counts are feature observations. Licence parents
        # are a second normalized projection, never a replacement for children.
        _, normalized_sha, _ = atomic_jsonl(root / "normalized" / "records.jsonl", parsed["accepted"])
        atomic_jsonl(root / "normalized" / "licences.jsonl", parsed["licences"])
        atomic_jsonl(root / "quarantined" / "records.jsonl", parsed["quarantined"])
        manifest = private_manifest(source_id=SOURCE_ID, adapter_version=ADAPTER_VERSION, schema_version=SCHEMA_VERSION,
            artifact=artifact, input_rows=parsed["input_rows"], normalized_rows=len(parsed["accepted"]),
            quarantined_rows=len(parsed["quarantined"]), normalized_sha256=normalized_sha, parsed_sha256=parsed_sha,
            anomaly_counts={reason: sum(reason in item["reasons"] for item in parsed["quarantined"]) for reason in sorted({r for item in parsed["quarantined"] for r in item["reasons"]})})
        manifest.update({"country_code": "AU", "source_kind": "environmental_licence", "coverage": self.coverage,
            "schema_fingerprint": parsed["schema_fingerprint"], "source_activity_observations": parsed["activity_observation_count"],
            "source_licence_count": parsed["licence_count"], "geocoding": "disabled", "coordinate_precision": "coarse-approximate-0.01-degree",
            "terms_state": "unresolved", "privacy_state": "review-required", "publication_eligibility": "blocked",
            "release_state": "not-created", "publication_state": "private-candidate"})
        atomic_json(root / "manifest.json", manifest)
        write_operator_review_packet(root, manifest, source_scope=self.coverage,
            checks=("aggregate by EPA licence while retaining distinct child activity observations", "keep source points coarse and approximate; do not geocode", "treat activity labels as environmental licence evidence, not proof of slaughter or current operation"),
            blockers=("source reuse terms require confirmation", "licence-name and approximate-location privacy review required", "no map, graph, or public release approval"))
        return manifest
