"""Private parser for narrowly scoped INEGI DENUE meat-industry results."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

SOURCE_ID = "mx.locations"
API_BASE = "https://www.inegi.org.mx/app/api/denue/v1/consulta/"
API_DOCS = "https://www.inegi.org.mx/servicios/api-denue/"
ACTIVITY_CODES = ("311611", "311612", "311613", "311614")
ACTIVITY_CATEGORIES = {
    "311611": ("slaughter",),
    "311612": ("processing",),
    "311613": ("processing",),
    "311614": ("processing",),
}
# Broad WGS84 validation envelope for mainland Mexico and its populated
# offshore jurisdictions. This rejects clearly foreign points; it is not a
# point-in-polygon claim or a precision statement.
MEXICO_WGS84_BOUNDS = (-118.5, -86.5, 14.5, 32.8)  # west, east, south, north
ADAPTER_VERSION = "mx-denue-v1"
SCHEMA_VERSION = "denue-api-v1"

# The API also returns phone, email, and website fields. These are deliberately
# excluded from retained rows; this source only needs facility identity,
# classification, address, and source-supplied location evidence.
SOURCE_FIELDS = (
    "CLEE", "Id", "Nombre", "Razon_social", "Clase_actividad", "Estrato",
    "Tipo_vialidad", "Calle", "Num_Exterior", "Num_Interior", "Colonia", "CP",
    "Ubicacion", "Tipo", "Latitud", "Longitud", "AGEB", "Manzana",
    "CLASE_ACTIVIDAD_ID", "SECTOR_ACTIVIDAD_ID", "SUBSECTOR_ACTIVIDAD_ID",
    "RAMA_ACTIVIDAD_ID", "SUBRAMA_ACTIVIDAD_ID", "EDIFICIO_PISO", "EDIFICACION",
    "Tipo_Asentamiento", "Fecha_Alta", "AreaGeo",
)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _coordinate_pair(latitude: Any, longitude: Any) -> tuple[dict[str, float] | None, str]:
    lat_text, lon_text = _text(latitude), _text(longitude)
    if not lat_text and not lon_text:
        return None, "not-supplied"
    if not lat_text or not lon_text:
        return None, "incomplete-source-coordinate"
    try:
        lat, lon = float(lat_text), float(lon_text)
    except ValueError:
        return None, "invalid-source-coordinate"
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, "invalid-source-coordinate"
    return {"latitude": lat, "longitude": lon}, "source-provided-precision-unknown"


def _address(row: dict[str, Any]) -> str | None:
    parts = [
        _text(row.get("Tipo_vialidad")), _text(row.get("Calle")),
        _text(row.get("Num_Exterior")), _text(row.get("Num_Interior")),
        _text(row.get("Colonia")), _text(row.get("CP")),
    ]
    value = ", ".join(part for part in parts if part)
    return value or None


class DenueAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    schema_version = SCHEMA_VERSION

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("DENUE artifact is not valid UTF-8 JSON") from error
        if (not isinstance(payload, dict) or payload.get("source_id") != SOURCE_ID
                or payload.get("schema_version") != SCHEMA_VERSION
                or payload.get("activity_codes") != list(ACTIVITY_CODES)
                or not isinstance(payload.get("records"), list)):
            raise ValueError("DENUE artifact envelope or activity scope changed")

        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        seen: set[str] = set()
        anomaly_counts: dict[str, int] = {}
        for index, raw in enumerate(payload["records"], start=1):
            if not isinstance(raw, dict):
                quarantined.append({"source_row": index, "reasons": ["record_not_object"], "source_values": {}})
                anomaly_counts["record_not_object"] = anomaly_counts.get("record_not_object", 0) + 1
                continue
            source_values = {key: raw[key] for key in SOURCE_FIELDS if key in raw}
            establishment_id = _text(raw.get("Id"))
            clee = _text(raw.get("CLEE"))
            activity_id = _text(raw.get("CLASE_ACTIVIDAD_ID"))
            reasons = []
            if not establishment_id:
                reasons.append("missing_establishment_id")
            if not clee:
                reasons.append("missing_clee")
            if activity_id not in ACTIVITY_CODES:
                reasons.append("activity_class_out_of_scope")
            if establishment_id and establishment_id in seen:
                reasons.append("duplicate_establishment_id")
            if establishment_id:
                seen.add(establishment_id)
            coordinates, coordinate_state = _coordinate_pair(raw.get("Latitud"), raw.get("Longitud"))
            if coordinates:
                west, east, south, north = MEXICO_WGS84_BOUNDS
                if not (west <= coordinates["longitude"] <= east
                        and south <= coordinates["latitude"] <= north):
                    coordinates = None
                    coordinate_state = "outside-mexico-coordinate-envelope"
                    reasons.append("invalid_or_outside_mexico_bounds")
            name = _text(raw.get("Nombre"))
            address = _address(raw)
            record = {
                "source_id": SOURCE_ID,
                "source_row": index,
                "source_record_key": establishment_id,
                "source_values": source_values,
                "normalized": {
                    "establishment_id": establishment_id,
                    "clee": clee,
                    "name": name,
                    "operator_name": _text(raw.get("Razon_social")),
                    "country_code": "MX",
                    "source_administrative_location": _text(raw.get("Ubicacion")),
                    "facility_address": address,
                    "private_location_evidence": {
                        "address": address,
                        "country_code": "MX",
                        "source_administrative_location": _text(raw.get("Ubicacion")),
                    },
                    "address_state": "source-present-pending-privacy-review" if address else "unknown",
                    "activity_class_id": activity_id,
                    "activity_name": _text(raw.get("Clase_actividad")),
                    "source_activity_categories": (activity_id,) if activity_id else (),
                    "activity_categories": ACTIVITY_CATEGORIES.get(activity_id, ()),
                    "classification_state": "mapped" if activity_id in ACTIVITY_CATEGORIES else "unresolved",
                    "activity_size_stratum": _text(raw.get("Estrato")),
                    "source_start_date": _text(raw.get("Fecha_Alta")),
                    "coordinates": coordinates,
                    "coordinate_state": coordinate_state,
                    "coordinate_provider": "INEGI DENUE" if coordinates else None,
                    "coordinate_precision": "unknown" if coordinates else None,
                    "privacy_gate": "pending-review",
                    "coordinate_gate": "review_required",
                    "publication_gate": "blocked",
                },
            }
            if reasons:
                quarantined.append({"source_row": index, "reasons": reasons, "record": record})
                for reason in reasons:
                    anomaly_counts[reason] = anomaly_counts.get(reason, 0) + 1
            else:
                accepted.append(record)
        return {"accepted": accepted, "quarantined": quarantined,
                "input_rows": len(payload["records"]),
                "anomaly_counts": dict(sorted(anomaly_counts.items())),
                "source_sha256": hashlib.sha256(content).hexdigest(),
                "retrieved_at_utc": payload.get("retrieved_at_utc"),
                "activity_counts": payload.get("preflight_counts", [])}

    def run(self, raw_path: str | Path, run_dir: str | Path,
            artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        if artifact.sha256 != hashlib.sha256(raw).hexdigest() or artifact.byte_size != len(raw):
            raise ValueError("DENUE artifact provenance mismatch")
        parsed = self.parse_bytes(raw)
        root = Path(run_dir)
        rows = parsed["accepted"] + [item["record"] for item in parsed["quarantined"] if "record" in item]
        _, parsed_sha, _ = atomic_jsonl(root / "parsed" / "records.jsonl", rows)
        _, normalized_sha, _ = atomic_jsonl(root / "normalized" / "records.jsonl", parsed["accepted"])
        atomic_jsonl(root / "quarantined" / "records.jsonl", parsed["quarantined"])
        manifest = private_manifest(
            source_id=self.source_id, adapter_version=self.adapter_version,
            schema_version=self.schema_version, artifact=artifact,
            input_rows=parsed["input_rows"], normalized_rows=len(parsed["accepted"]),
            quarantined_rows=len(parsed["quarantined"]), normalized_sha256=normalized_sha,
            parsed_sha256=parsed_sha, anomaly_counts=parsed["anomaly_counts"],
        )
        manifest.update({
            "country_code": "MX",
            "coverage": "DENUE establishments in SCIAN 2023 classes 311611–311614; bounded state-by-state API acquisition",
            "source_documentation_url": API_DOCS,
            "activity_counts": parsed["activity_counts"],
            "source_record_key": "DENUE Id; CLEE preserved as a second source identifier",
            "terms_attribution": "Source: INEGI, DENUE, retrieval date; disclose project transformations and do not imply INEGI endorsement.",
            "geocoding": "disabled",
            "release_gate": "restricted_pending_privacy_and_source_review",
        })
        atomic_json(root / "manifest.json", manifest)
        return manifest

    def write_candidate_handoff(self, run_dir: str | Path, artifact: SourceArtifact,
                                parsed: dict[str, Any]) -> dict[str, Any]:
        """Write accepted rows through the shared private candidate contract."""
        root = Path(run_dir)
        atomic_jsonl(root / "quarantined" / "records.jsonl", parsed["quarantined"])
        return write_handoff(
            root, parsed["accepted"], artifact, source_id=self.source_id,
            profile="mx-denue-scian-31161",
        )
