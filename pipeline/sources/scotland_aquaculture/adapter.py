"""Private adapter for the Scottish Government aquaculture-sites WFS.

WFS feature rows are grouped by the authority's native site identifier because
one registered site can have several facility/species/stage observations.
Fishery sites are explicitly excluded from animal-production candidates.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline.common.review import write_operator_review_packet
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

SOURCE_ID = "gb.scot.marine.aquaculture"
CATALOG_URL = "https://www.data.gov.uk/dataset/28c43af0-ed74-4072-bd5a-446a6da13fad/aquaculture-finfish-and-shellfish-farms-including-fishery-sites"
LICENSE = "Open Government Licence v3.0"
LICENSE_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
ATTRIBUTION = "Contains information from Scottish Government (Marine Scotland) licensed under the Open Government Licence v3.0."
ADAPTER_VERSION = "gb-scot-marine-aquaculture-v1"
SCHEMA_VERSION = "gb-scot-aquaculture-wfs-geojson-v1"
COVERAGE = "Scottish finfish and shellfish aquaculture production sites from the Fish Health Inspectorate Aquadat layer; fishery sites excluded; repeated feature observations grouped by native site identifier"
REQUIRED_PROPERTIES = frozenset({
    "siteno", "sitename", "sitecatcd", "sitestatcd", "sitetype", "unitauth",
    "regionname", "watertype", "easting", "northing", "osgridref",
    "facilitytp", "speciescd", "stagecode",
})
STATUS_LABELS = {"A": "active", "I": "inactive", "D": "deregistered"}
ALLOWED_SITE_TYPES = {"fish": "animal-aquaculture-finfish", "shellfish": "animal-aquaculture-shellfish"}
# Published dataset extent; a validation envelope, not an inferred location.
WGS84_BOUNDS = (-7.75714, -0.53202, 54.53297, 61.46459)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def parse_geojson(raw: bytes) -> dict[str, Any]:
    try:
        document = json.loads(raw.decode("utf-8-sig", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("malformed Scottish aquaculture GeoJSON") from error
    if document.get("type") != "FeatureCollection" or not isinstance(document.get("features"), list):
        raise ValueError("schema drift: expected a GeoJSON FeatureCollection")
    count = len(document["features"])
    for key in ("numberMatched", "numberReturned", "totalFeatures"):
        value = document.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value != count:
            raise ValueError("incomplete WFS response: feature count metadata does not reconcile")
    timestamp = document.get("timeStamp")
    if not isinstance(timestamp, str):
        raise ValueError("schema drift: WFS response timestamp is missing")
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("schema drift: WFS response timestamp is invalid") from error
    return document


class ScotlandAquacultureAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION
    source_kind = "facility_master"
    source_url = CATALOG_URL
    coverage = COVERAGE

    def parse_bytes(self, raw: bytes) -> dict[str, Any]:
        document = parse_geojson(raw)
        groups: dict[str, list[tuple[int, dict[str, Any], dict[str, Any]]]] = defaultdict(list)
        quarantine: list[dict[str, Any]] = []
        type_counts: Counter[str] = Counter()
        fingerprint: set[str] = set()

        for row_number, feature in enumerate(document["features"], start=1):
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                quarantine.append({"source_row": row_number, "reasons": ["invalid_feature_object"],
                                   "source_values": {}, "normalized": {}})
                continue
            properties = feature.get("properties")
            if not isinstance(properties, dict):
                raise ValueError("schema drift: GeoJSON feature properties must be an object")
            fingerprint.update(str(key) for key in properties)
            missing = REQUIRED_PROPERTIES - properties.keys()
            if missing:
                raise ValueError("schema drift: aquaculture feature properties are missing required fields")
            site_id = _clean(properties.get("siteno"))
            if not site_id:
                quarantine.append({"source_row": row_number, "reasons": ["missing_site_identifier"],
                                   "source_values": {"source_properties": properties}, "normalized": {}})
                continue
            geometry = feature.get("geometry")
            if not isinstance(geometry, dict) or geometry.get("type") != "Point":
                quarantine.append({"source_row": row_number, "reasons": ["non_point_source_geometry"],
                                   "source_values": {"source_properties": properties}, "normalized": {}})
                continue
            pair = geometry.get("coordinates")
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                quarantine.append({"source_row": row_number, "reasons": ["missing_source_coordinates"],
                                   "source_values": {"source_properties": properties}, "normalized": {}})
                continue
            lon, lat = _number(pair[0]), _number(pair[1])
            west, east, south, north = WGS84_BOUNDS
            if lon is None or lat is None or not (west <= lon <= east and south <= lat <= north):
                quarantine.append({"source_row": row_number, "reasons": ["invalid_or_out_of_extent_source_coordinates"],
                                   "source_values": {"source_properties": properties}, "normalized": {}})
                continue
            groups[site_id].append((row_number, properties, {"longitude": lon, "latitude": lat}))

        accepted: list[dict[str, Any]] = []
        anomaly_counts: Counter[str] = Counter()
        for site_id, observations in sorted(groups.items()):
            types = {_clean(row.get("sitetype")) for _, row, _ in observations}
            statuses = {_clean(row.get("sitestatcd")) for _, row, _ in observations}
            names = {_clean(row.get("sitename")) for _, row, _ in observations}
            locations = {(point["longitude"], point["latitude"]) for _, _, point in observations}
            projected_locations = {
                (_number(row.get("easting")), _number(row.get("northing")), _clean(row.get("osgridref")))
                for _, row, _ in observations
            }
            source_rows = [number for number, _, _ in observations]
            source_properties = [row for _, row, _ in observations]
            first = source_properties[0]
            common = {"site_identifier": site_id, "source_rows": source_rows,
                      "source_observations": source_properties}
            reason: str | None = None
            site_type = next(iter(types)) if len(types) == 1 else None
            if len(types) != 1:
                reason = "conflicting_site_types"
            elif site_type == "Fishery Site":
                reason = "out_of_animal_aquaculture_scope_fishery_site"
            elif not isinstance(site_type, str) or site_type.casefold() not in ALLOWED_SITE_TYPES:
                reason = "unrecognized_site_type"
            elif len(names) != 1:
                reason = "conflicting_site_names"
            elif next(iter(names)) is None:
                reason = "missing_site_name"
            elif len(statuses) != 1 or next(iter(statuses)) not in STATUS_LABELS:
                reason = "missing_or_conflicting_source_status"
            elif len(locations) != 1:
                reason = "conflicting_source_site_coordinates"
            elif len(projected_locations) != 1:
                reason = "conflicting_source_projected_coordinates"
            if reason:
                quarantine.append({"source_row": source_rows[0], "reasons": [reason],
                                   "source_values": common, "normalized": {}})
                anomaly_counts[reason] += 1
                continue

            assert isinstance(site_type, str)
            status_code = next(iter(statuses))
            categories = [ALLOWED_SITE_TYPES[site_type.casefold()]]
            point = observations[0][2]
            facility_types = sorted({value for row in source_properties if (value := _clean(row.get("facilitytp")))})
            species_codes = sorted({value for row in source_properties if (value := _clean(row.get("speciescd")))})
            stages = sorted({value for row in source_properties if (value := _clean(row.get("stagecode")))})
            coordinates = {**point, "source_crs": "EPSG:4326", "precision": "source-reported-unknown",
                           "location_semantics": "Scottish aquaculture registered site point; not operator correspondence address"}
            normalized = {
                "establishment_id": site_id, "facility_grouping": "source-native-aquaculture-site-id",
                "facility_name": _clean(first.get("sitename")), "country_code": "GB", "nation": "Scotland",
                "region": _clean(first.get("regionname")), "municipality": _clean(first.get("unitauth")),
                "activity_categories": categories, "source_site_type": site_type,
                "source_site_category_code": _clean(first.get("sitecatcd")),
                "source_status_code": status_code, "source_status": STATUS_LABELS[status_code],
                "source_facility_types": facility_types, "source_species_codes": species_codes,
                "source_production_stages": stages, "coordinates": coordinates,
                "coordinate_state": "source-point-pending-review", "coordinate_precision": "source-reported-unknown",
                "source_projected_coordinates": {"easting": _number(first.get("easting")),
                                                  "northing": _number(first.get("northing")),
                                                  "crs": "EPSG:27700", "grid_reference": _clean(first.get("osgridref"))},
                "source_feature_count": len(observations), "source_feature_rows": source_rows,
                "privacy_gate": "pending-review", "rights_gate": f"{LICENSE}; attribution required; private preview",
                "publication_gate": "blocked",
            }
            accepted.append({"source_id": SOURCE_ID, "source_row": source_rows[0],
                             "source_record_key": site_id, "source_values": common, "normalized": normalized})
            type_counts[site_type] += 1

        # Lifecycle rows are site groups plus individually quarantined
        # malformed features.  Source feature count is separately retained.
        input_sites = len(accepted) + len(quarantine)
        result = {
            "accepted": accepted, "quarantined": quarantine, "input_rows": input_sites,
            "source_feature_rows": len(document["features"]), "normalized_rows": len(accepted),
            "quarantined_rows": len(quarantine),
            "source_feature_type_counts": dict(sorted(Counter(
                _clean(feature.get("properties", {}).get("sitetype")) or "unknown"
                for feature in document["features"] if isinstance(feature, dict) and isinstance(feature.get("properties"), dict)
            ).items())),
            "site_type_counts": dict(sorted(type_counts.items())),
            "anomaly_counts": dict(sorted(anomaly_counts.items())),
            "schema_fingerprint": hashlib.sha256(json.dumps(sorted(fingerprint), separators=(",", ":")).encode()).hexdigest(),
        }
        if result["input_rows"] != result["normalized_rows"] + result["quarantined_rows"]:
            raise AssertionError("site-level input/accepted/quarantined counts do not reconcile")
        return result

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != artifact.sha256 or len(raw) != artifact.byte_size:
            raise ValueError("Scottish aquaculture acquisition provenance mismatch")
        parsed = self.parse_bytes(raw)
        root = Path(run_dir)
        _, parsed_hash, _ = atomic_jsonl(root / "parsed" / "records.jsonl", parsed["accepted"] + parsed["quarantined"])
        _, normalized_hash, _ = atomic_jsonl(root / "normalized" / "records.jsonl", parsed["accepted"])
        atomic_jsonl(root / "quarantined" / "records.jsonl", parsed["quarantined"])
        manifest = private_manifest(source_id=SOURCE_ID, adapter_version=ADAPTER_VERSION,
                                    schema_version=SCHEMA_VERSION, artifact=artifact,
                                    input_rows=parsed["input_rows"], normalized_rows=parsed["normalized_rows"],
                                    quarantined_rows=parsed["quarantined_rows"], normalized_sha256=normalized_hash,
                                    parsed_sha256=parsed_hash, anomaly_counts=parsed["anomaly_counts"])
        manifest.update({"source_title": "Scottish Government finfish and shellfish aquaculture sites",
                         "license": LICENSE, "license_url": LICENSE_URL, "attribution": ATTRIBUTION,
                         "coverage": COVERAGE, "source_feature_rows": parsed["source_feature_rows"],
                         "source_feature_type_counts": parsed["source_feature_type_counts"],
                         "site_type_counts": parsed["site_type_counts"],
                         "schema_fingerprint": parsed["schema_fingerprint"],
                         "source_crs": "EPSG:4326 for WFS geometry; native projected fields EPSG:27700 preserved",
                         "coordinate_semantics": "source-reported site point; precision not specified by source",
                         "geocoding": "disabled", "graph_relationships_emitted": 0})
        atomic_json(root / "manifest.json", manifest)
        write_operator_review_packet(root, manifest, source_scope=COVERAGE,
            checks=("confirm site-point precision and animal-farm semantics before any public mapping",
                    "review active/inactive/deregistered source status as reported; absence is not closure",
                    "review grouped facility/species/stage observations without treating them as separate site identities",
                    "retain the exact OGL attribution and do not imply Scottish Government endorsement"),
            blockers=("private preview only; no publication or project approval",
                      "coordinate precision and location privacy review remain pending",
                      "source snapshot is dated and not a census of all animal facilities"))
        return manifest

    def write_candidate_handoff(self, run_dir: str | Path, artifact: SourceArtifact,
                                accepted: list[dict[str, Any]]) -> dict[str, Any]:
        return write_handoff(run_dir, accepted, artifact, source_id=SOURCE_ID,
                             emit_graph_candidates=False)
