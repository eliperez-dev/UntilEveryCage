"""Deterministic, livestock-only interpretation of the EEA site-point feed."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

CONFIG = json.loads(Path(__file__).with_name("config.json").read_text(encoding="utf-8"))
SOURCE_ID = CONFIG["source_id"]
SOURCE_URL = CONFIG["source_url"]
QUERY_URL = SOURCE_URL + "/query"
ADAPTER_VERSION = CONFIG["adapter_version"]
SCHEMA_VERSION = CONFIG["schema_version"]
COVERAGE = CONFIG["coverage"]
YEAR = CONFIG["reporting_year"]
WHERE = f"Site_reporting_year={YEAR} AND eea_activities='Livestock'"
REQUIRED_FIELDS = {"OBJECTID", "InspireSiteId", "siteName", "countryCode", "Site_reporting_year",
                   "eea_activities", "activity_details", "eprtr_AnnexIActivity", "nFacilities", "nInstallations"}
# Validation envelopes, not geocoding or proof of a parcel. Outliers retain
# their source values but remain unmapped for review. No coordinate repair.
COUNTRY_BOUNDS = {
    "AT": (9, 18, 46, 50), "BE": (2, 7, 49, 52), "BG": (22, 29, 41, 45),
    "CY": (32, 35, 34, 36), "DE": (5, 16, 47, 56), "DK": (8, 16, 54, 58),
    "EE": (21, 29, 57, 60), "ES": (-19, 5, 27, 44), "FI": (19, 32, 59, 71),
    "FR": (-6, 10, 41, 52), "GR": (19, 30, 34, 42), "HR": (13, 20, 42, 47),
    "HU": (16, 23, 45, 49), "IE": (-11, -5, 51, 56), "IT": (6, 19, 35, 48),
    "LT": (20, 27, 53, 57), "LU": (5, 7, 49, 51), "LV": (20, 29, 55, 59),
    "NL": (3, 8, 50, 54), "PL": (14, 25, 49, 55), "PT": (-32, -6, 30, 43),
    "RO": (20, 30, 43, 49), "RS": (18, 24, 41, 47), "SE": (10, 25, 55, 70),
    "SI": (13, 17, 45, 47),
}


def bundle_digest(root: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for path in sorted(root.glob("page-*.geojson")):
        raw, name = path.read_bytes(), path.name.encode()
        digest.update(len(name).to_bytes(8, "big")); digest.update(name)
        digest.update(len(raw).to_bytes(8, "big")); digest.update(raw)
        size += len(raw)
    return digest.hexdigest(), size


def coordinate_pair(geometry: Any, country: str) -> tuple[float, float] | None:
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        return None
    pair = geometry.get("coordinates")
    if not isinstance(pair, list) or len(pair) != 2 or any(isinstance(v, bool) for v in pair):
        return None
    try:
        lon, lat = map(float, pair)
    except (TypeError, ValueError, OverflowError):
        return None
    if country not in COUNTRY_BOUNDS or not all(map(math.isfinite, (lon, lat))):
        return None
    west, east, south, north = COUNTRY_BOUNDS[country]
    return (lon, lat) if west <= lon <= east and south <= lat <= north else None


class EeaLivestockAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION
    source_kind = "facility_master"
    coverage = COVERAGE

    def parse(self, raw_path: str | Path) -> dict[str, Any]:
        path = Path(raw_path)
        files = sorted(path.glob("page-*.geojson")) if path.is_dir() else [path]
        if not files:
            raise ValueError("EEA page bundle is empty")
        accepted, quarantined = [], []
        seen: set[str] = set()
        fields: set[str] = set()
        anomalies: Counter[str] = Counter()
        countries: Counter[str] = Counter()
        row_number = 0
        for file in files:
            doc = json.loads(file.read_bytes().decode("utf-8-sig"))
            if not isinstance(doc, dict) or doc.get("type") != "FeatureCollection" or not isinstance(doc.get("features"), list):
                raise ValueError("EEA response must be a GeoJSON FeatureCollection")
            # GeoJSON defaults to CRS84. Reject projected legacy GeoJSON.
            if "crs" in doc and doc["crs"] not in (None, {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}):
                raise ValueError("EEA GeoJSON has an unexpected coordinate reference system")
            for feature in doc["features"]:
                row_number += 1
                props = feature.get("properties") if isinstance(feature, dict) else None
                if not isinstance(props, dict) or REQUIRED_FIELDS - props.keys():
                    raise ValueError("EEA site schema changed")
                fields.update(props)
                country = str(props.get("countryCode") or "").strip().upper()
                site = str(props.get("InspireSiteId") or "").strip()
                name = str(props.get("siteName") or "").strip()
                identity = f"{country}:{site}"
                reasons = []
                if not site or country not in COUNTRY_BOUNDS:
                    reasons.append("missing_or_unreviewed_source_identity")
                if not name:
                    reasons.append("missing_source_site_name")
                if props["Site_reporting_year"] != YEAR or props["eea_activities"] != "Livestock":
                    reasons.append("outside_reviewed_livestock_year_scope")
                if identity in seen:
                    reasons.append("duplicate_country_site_identity")
                seen.add(identity)
                row = {"source_id": SOURCE_ID, "source_row": row_number,
                       "source_record_key": f"site:{identity}:{YEAR}",
                       "source_values": dict(props), "normalized": {}}
                # Preserve the service-transformed geometry and source x/y
                # fields independently; neither replaces the original pages.
                row["source_values"]["source_geometry_wgs84"] = feature.get("geometry")
                if reasons:
                    quarantined.append({"source_row": row_number, "reasons": reasons, "record": row})
                    anomalies.update(reasons)
                    continue
                pair = coordinate_pair(feature.get("geometry"), country)
                coordinates = ({"longitude": pair[0], "latitude": pair[1],
                                "precision": "source-precision-unknown"} if pair else {})
                if not pair:
                    anomalies["unusable_or_out_of_country_source_point"] += 1
                row["normalized"] = {
                    "establishment_id": identity, "facility_grouping": "country-and-inspire-site-id",
                    "country_code": country, "facility_name": name,
                    "source_reporting_year": YEAR, "source_activity": "Livestock",
                    "activity_codes": [props["eprtr_AnnexIActivity"]] if props["eprtr_AnnexIActivity"] else [],
                    "source_activity_details": props["activity_details"],
                    "source_facility_count": props["nFacilities"],
                    "source_installation_count": props["nInstallations"],
                    "coordinates": coordinates, "coordinate_precision": "source-precision-unknown" if pair else "unknown",
                    "coordinate_state": "source-point-pending-review" if pair else "source-point-unusable",
                    "coordinate_method": "source_coordinates", "coordinate_provider": "European Environment Agency",
                    "privacy_gate": "pending-review", "rights_gate": "CC BY 4.0; attribute European Environment Agency",
                    "publication_gate": "blocked",
                }
                accepted.append(row)
                countries[country] += 1
        return {"accepted": accepted, "quarantined": quarantined, "input_rows": row_number,
                "scope_counts": dict(sorted(anomalies.items())), "country_counts": dict(sorted(countries.items())),
                "schema_fingerprint": hashlib.sha256(json.dumps(sorted(fields)).encode()).hexdigest()}

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        path, root = Path(raw_path), Path(run_dir)
        raw = None if path.is_dir() else path.read_bytes()
        digest, size = bundle_digest(path) if raw is None else (hashlib.sha256(raw).hexdigest(), len(raw))
        if (digest, size) != (artifact.sha256, artifact.byte_size):
            raise ValueError("EEA acquisition provenance mismatch")
        parsed = self.parse(path)
        accepted, quarantine = parsed["accepted"], parsed["quarantined"]
        _, parsed_hash, _ = atomic_jsonl(root / "parsed/records.jsonl", accepted + [x["record"] for x in quarantine])
        _, normalized_hash, _ = atomic_jsonl(root / "normalized/records.jsonl", accepted)
        atomic_jsonl(root / "quarantined/records.jsonl", quarantine)
        manifest = private_manifest(source_id=SOURCE_ID, adapter_version=ADAPTER_VERSION,
                                    schema_version=SCHEMA_VERSION, artifact=artifact,
                                    input_rows=parsed["input_rows"], normalized_rows=len(accepted), quarantined_rows=len(quarantine),
                                    normalized_sha256=normalized_hash, parsed_sha256=parsed_hash,
                                    anomaly_counts=parsed["scope_counts"])
        manifest.update({"schema_fingerprint": parsed["schema_fingerprint"], "country_counts": parsed["country_counts"],
                         "reporting_year": YEAR, "source_attribution": "European Environment Agency",
                         "geocoding": "disabled", "graph_relationships_emitted": 0})
        atomic_json(root / "manifest.json", manifest)
        return manifest

    def write_candidate_handoff(self, run_dir: Path, artifact: SourceArtifact, rows: list[dict[str, Any]]) -> dict[str, Any]:
        return write_handoff(run_dir, rows, artifact, source_id=SOURCE_ID, emit_graph_candidates=False)
