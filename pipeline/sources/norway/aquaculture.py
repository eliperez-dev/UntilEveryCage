"""Fiskeridirektoratet Aquaculture Register locality layer.

Only animal aquaculture localities are candidate-normalized. Official source
pages are preserved privately; this module never publishes, geocodes, or uses
permit-holder mailing addresses as facility locations.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from pipeline.common.review import write_operator_review_packet
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

SOURCE_ID = "no.fiskeridir.aquaculture"
SOURCE_URL = "https://gis.fiskeridir.no/server/rest/services/Yggdrasil/Akvakulturregisteret/MapServer/0"
QUERY_URL = SOURCE_URL + "/query"
LICENSE_URL = "https://www.fiskeridir.no/statistikk-tall-og-analyse/lisens-for-bruk-av-fiskeridirektoratets-data"
LICENSE = "Norwegian Licence for Open Government Data (NLOD)"
LICENSE_VERSION = "2.0"
LICENSE_TEXT_URL = "https://data.norge.no/nlod/en/2.0"
ADAPTER_VERSION = "no-fiskeridir-aquaculture-v1"
SCHEMA_VERSION = "no-fiskeridir-mapserver-geojson-v1"
COVERAGE = "Norway; registered aquaculture locality points; animal-species localities only; not a census of farms or permit holders"
MAX_BYTES = 24 * 1024 * 1024
MAX_PAGES = 32
MAX_PAGE_SIZE = 500
NORWAY_WGS84_BOUNDS = (3.0, 32.0, 57.0, 72.0)  # west, east, south, north; validation only
REQUIRED_FIELDS = {"objectid", "loknr", "til_arter", "symbol", "status_lokalitet", "kommune", "fylke"}
ALGAL_SYMBOLS = {"alger", "algae"}
ALGAL_ONLY = re.compile(r"^(?:alger|algae|tang|tare)(?:\s*[,;/|]\s*(?:alger|algae|tang|tare))*$", re.I)


def bundle_digest(root: Path) -> tuple[str, int]:
    """Hash retained response files by sorted relative path and bytes."""
    digest = hashlib.sha256()
    size = 0
    files = [path for path in sorted(root.iterdir()) if path.is_file() and path.name.startswith("page-")]
    for path in files:
        name = path.name.encode("utf-8")
        raw = path.read_bytes()
        digest.update(len(name).to_bytes(8, "big")); digest.update(name)
        digest.update(len(raw).to_bytes(8, "big")); digest.update(raw)
        size += len(raw)
    return digest.hexdigest(), size


def _feature_collections(raw_path: Path) -> Iterable[dict[str, Any]]:
    if raw_path.is_dir():
        files = sorted(raw_path.glob("page-*.geojson"))
        if not files:
            raise ValueError("schema drift: acquired page bundle is empty")
        for file in files:
            yield _parse_collection(file.read_bytes())
    else:
        yield _parse_collection(raw_path.read_bytes())


def _parse_collection(content: bytes) -> dict[str, Any]:
    try:
        doc = json.loads(content.decode("utf-8-sig", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("malformed Norway aquaculture GeoJSON") from error
    if doc.get("type") != "FeatureCollection" or not isinstance(doc.get("features"), list):
        raise ValueError("schema drift: expected a GeoJSON FeatureCollection")
    return doc


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _safe_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _is_algal_only(properties: dict[str, Any]) -> bool:
    symbol = _text(properties.get("symbol")).casefold()
    species = _text(properties.get("til_arter"))
    return symbol in ALGAL_SYMBOLS or bool(ALGAL_ONLY.fullmatch(species))


class NorwayAquacultureAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION
    source_kind = "facility_master"
    source_url = SOURCE_URL
    coverage = COVERAGE

    def parse(self, raw_path: str | Path) -> dict[str, Any]:
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        scope_counts: Counter[str] = Counter()
        seen_localities: set[str] = set()
        row_number = 0
        fingerprint_fields: set[str] = set()
        for collection in _feature_collections(Path(raw_path)):
            for feature in collection["features"]:
                row_number += 1
                if not isinstance(feature, dict) or feature.get("type") != "Feature":
                    quarantined.append({"source_row": row_number, "reasons": ["invalid_feature_object"], "record": {"source_id": SOURCE_ID, "source_row": row_number, "source_record_key": f"invalid-row-{row_number}", "source_values": {}, "normalized": {}}})
                    scope_counts["invalid_feature_object"] += 1
                    continue
                properties = feature.get("properties")
                if not isinstance(properties, dict):
                    raise ValueError("schema drift: GeoJSON feature properties must be an object")
                fingerprint_fields.update(str(key) for key in properties)
                if REQUIRED_FIELDS - properties.keys():
                    raise ValueError("schema drift: aquaculture locality layer is missing required fields")
                locality_id = properties.get("loknr")
                object_id = properties.get("objectid")
                locality_key = str(locality_id).strip() if locality_id is not None else ""
                object_key = str(object_id).strip() if object_id is not None else ""
                species = _text(properties.get("til_arter"))
                reasons: list[str] = []
                if not locality_key:
                    reasons.append("missing_locality_identifier")
                if not object_key:
                    reasons.append("missing_source_object_identifier")
                if not species:
                    reasons.append("missing_species_scope")
                if reasons:
                    quarantined.append({"source_row": row_number, "reasons": reasons, "record": {"source_id": SOURCE_ID, "source_row": row_number, "source_record_key": object_key or f"row-{row_number}", "source_values": {}, "normalized": {}}})
                    for reason in reasons:
                        scope_counts[reason] += 1
                    continue
                if _is_algal_only(properties):
                    quarantined.append({"source_row": row_number, "reasons": ["out_of_animal_aquaculture_scope"], "record": {"source_id": SOURCE_ID, "source_row": row_number, "source_record_key": object_key, "source_values": {"locality_identifier": locality_key}, "normalized": {}}})
                    scope_counts["out_of_animal_aquaculture_scope"] += 1
                    continue
                if locality_key in seen_localities:
                    quarantined.append({"source_row": row_number, "reasons": ["duplicate_locality_identifier"], "record": {"source_id": SOURCE_ID, "source_row": row_number, "source_record_key": object_key, "source_values": {"locality_identifier": locality_key}, "normalized": {}}})
                    scope_counts["duplicate_locality_identifier"] += 1
                    continue
                seen_localities.add(locality_key)
                geometry = feature.get("geometry")
                coordinates: dict[str, Any] = {}
                coord_reasons: list[str] = []
                if not isinstance(geometry, dict) or geometry.get("type") != "Point":
                    coord_reasons.append("non_point_source_geometry")
                else:
                    pair = geometry.get("coordinates")
                    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                        coord_reasons.append("missing_source_coordinates")
                    else:
                        longitude, latitude = _safe_number(pair[0]), _safe_number(pair[1])
                        west, east, south, north = NORWAY_WGS84_BOUNDS
                        if longitude is None or latitude is None or not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
                            coord_reasons.append("invalid_wgs84_coordinates")
                        elif not (west <= longitude <= east and south <= latitude <= north):
                            coord_reasons.append("coordinates_outside_norway_envelope")
                        else:
                            coordinates = {"longitude": longitude, "latitude": latitude,
                                           "precision": "source-precision-unknown",
                                           "source_crs": "EPSG:4326",
                                           "location_semantics": "registered aquaculture locality point; not permit-holder mailing address"}
                if coord_reasons:
                    quarantined.append({"source_row": row_number, "reasons": coord_reasons, "record": {"source_id": SOURCE_ID, "source_row": row_number, "source_record_key": object_key, "source_values": {"locality_identifier": locality_key}, "normalized": {}}})
                    for reason in coord_reasons:
                        scope_counts[reason] += 1
                    continue
                status = _text(properties.get("status_lokalitet")) or "unknown"
                municipality = _text(properties.get("kommune")) or "unknown"
                region = _text(properties.get("fylke")) or "unknown"
                normalized = {
                    "establishment_id": locality_key,
                    "facility_grouping": "source-aquaculture-locality-number",
                    "country_code": "NO", "nation": "Norway",
                    "region": region, "municipality": municipality,
                    "activity_categories": ["animal-aquaculture"],
                    "source_species_scope": species,
                    "source_locality_status": status,
                    "source_observed_at": None,
                    "source_object_id": object_key,
                    "coordinates": coordinates,
                    "coordinate_state": "source-point-pending-review",
                    "coordinate_precision": "source-precision-unknown",
                    "privacy_gate": "pending-review",
                    "rights_gate": f"{LICENSE}, version {LICENSE_VERSION}; attribution required; private preview",
                    "publication_gate": "blocked",
                }
                accepted.append({"source_id": SOURCE_ID, "source_row": row_number,
                                 "source_record_key": f"locality:{locality_key}",
                                 "source_values": {"locality_identifier": locality_key,
                                                   "source_species_scope": species,
                                                   "locality_status": status,
                                                   "municipality": municipality,
                                                   "region": region},
                                 "normalized": normalized})
        fingerprint = hashlib.sha256(json.dumps(sorted(fingerprint_fields), separators=(",", ":")).encode()).hexdigest()
        return {"accepted": accepted, "quarantined": quarantined,
                "input_rows": row_number, "scope_counts": dict(sorted(scope_counts.items())),
                "schema_fingerprint": fingerprint,
                "locality_ids_unique": len(seen_localities) == len(accepted)}

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        path = Path(raw_path)
        if path.is_dir():
            digest, size = bundle_digest(path)
        else:
            raw = path.read_bytes(); digest, size = hashlib.sha256(raw).hexdigest(), len(raw)
        if digest != artifact.sha256 or size != artifact.byte_size:
            raise ValueError("Norway aquaculture acquisition provenance mismatch")
        parsed = self.parse(path)
        root = Path(run_dir)
        accepted, quarantined = parsed["accepted"], parsed["quarantined"]
        _, parsed_hash, _ = atomic_jsonl(root / "parsed" / "records.jsonl", accepted + [item["record"] for item in quarantined])
        _, normalized_hash, _ = atomic_jsonl(root / "normalized" / "records.jsonl", accepted)
        atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        manifest = private_manifest(source_id=SOURCE_ID, adapter_version=ADAPTER_VERSION,
                                    schema_version=SCHEMA_VERSION, artifact=artifact,
                                    input_rows=parsed["input_rows"], normalized_rows=len(accepted),
                                    quarantined_rows=len(quarantined), normalized_sha256=normalized_hash,
                                    parsed_sha256=parsed_hash, anomaly_counts=parsed["scope_counts"])
        manifest.update({"source_title": "Fiskeridirektoratet Aquaculture Register localities",
                         "license": LICENSE, "license_version": LICENSE_VERSION,
                         "license_url": LICENSE_URL, "coverage": COVERAGE,
                         "schema_fingerprint": parsed["schema_fingerprint"],
                         "source_row_count": parsed["input_rows"],
                         "animal_locality_candidates": len(accepted),
                         "scope_counts": parsed["scope_counts"],
                         "source_crs": "EPSG:25833; acquisition requested EPSG:4326 for explicit longitude/latitude",
                         "coordinate_envelope_validation": "passed; aggregate bounds not written to repository or report",
                         "attribution": "Source: Fiskeridirektoratet",
                         "geocoding": "disabled", "graph_relationships_emitted": 0})
        atomic_json(root / "manifest.json", manifest)
        write_operator_review_packet(root, manifest, source_scope=COVERAGE,
            checks=("confirm locality points and source precision before any public mapping",
                    "verify animal species scope; algal-only localities are excluded",
                    "confirm source locality status and avoid treating permit holders as site locations",
                    "retain Fiskeridirektoratet attribution and do not imply endorsement"),
            blockers=("private preview only; no publication or project approval",
                      "source precision and facility-level privacy review remain pending",
                      "aquaculture locality candidates are not a census of all animal facilities"))
        return manifest

    def write_candidate_handoff(self, run_dir: str | Path, artifact: SourceArtifact,
                                accepted: list[dict[str, Any]]) -> dict[str, Any]:
        return write_handoff(run_dir, accepted, artifact, source_id=SOURCE_ID,
                             emit_graph_candidates=False)


__all__ = ["SOURCE_ID", "SOURCE_URL", "QUERY_URL", "LICENSE", "LICENSE_URL",
           "ADAPTER_VERSION", "SCHEMA_VERSION", "COVERAGE", "NorwayAquacultureAdapter", "bundle_digest"]
