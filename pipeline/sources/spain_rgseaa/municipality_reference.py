"""Exact joining of verified AESAN localities to normalized IGN municipality rows."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .location_enrichment import _fold, official_province_key, same_official_province


SOURCE_URL = "https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec=9000004"
REFERENCE_SOURCE_ID = "ign-ngmep-2026"
REFERENCE_SOURCE = "Nomenclátor Geográfico de Municipios y Entidades de Población (IGN/CNIG), 2026"
REFERENCE_FILE = "BD_MUNICIPIOS-ENTIDADES.ZIP"
REFERENCE_YEAR = 2026
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_EXPANDED_CSV_BYTES = 3 * 1024 * 1024
MUNICIPALITY_HEADERS = (
    "COD_INE", "ID_REL", "COD_GEO", "COD_PROV", "PROVINCIA", "NOMBRE_ACTUAL",
    "POBLACION_MUNI", "SUPERFICIE", "PERIMETRO", "COD_INE_CAPITAL", "CAPITAL",
    "POBLACION_CAPITAL", "HOJA_MTN25", "LONGITUD_ETRS89_REGCAN95",
    "LATITUD_ETRS89_REGCAN95", "ORIGENCOOR", "ALTITUD", "ORIGENALTITUD",
)
PROVINCE_HEADERS = ("COD_PROV", "PROVINCIA", "COD_CA", "COMUNIDAD_AUTONOMA", "CAPITAL")
ALLOWED_COORDINATE_ORIGINS = {
    # Keep observed publisher spellings from the 2026 archive. These are
    # formatting variants of the already documented GPS.PNRGM and
    # Coordinación IGR.Poblaciones coordinate-origin methods.
    "gps.pnrgm", "gps. pnrgm", "investigacion",
    "coordinacion igr.poblaciones", "coordinado igr.poblaciones",
    "coordinado_igr poblaciones",
    "deteccion automatica", "mapa",
}
SPAIN_REFERENCE_BOUNDS = {"min_longitude": -18.5, "max_longitude": 4.5,
                          "min_latitude": 27.5, "max_latitude": 44.2}


def _finite_coordinate(value: Any) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # These CSVs use semicolon separators and Spanish decimal commas.
    if "." in text and "," in text:
        return None
    if text.count(",") > 1:
        return None
    try:
        result = float(text.replace(",", "."))
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_ign_reference_index(archive_path: str | Path, *,
                              retrieved_at_utc: str | None = None) -> dict[str, Any]:
    """Parse the official 2026 IGN archive into a minimized municipality index.

    Only the documented MUNICIPIOS and PROVINCIAS CSV members are consumed.
    Names, INE code, municipal population, coordinate origin, and geographic
    point are retained; no address/business records are involved.
    """
    path = Path(archive_path)
    if (not path.is_file() or path.is_symlink()
            or path.stat().st_size > MAX_ARCHIVE_BYTES):
        raise ValueError("ign_archive_invalid_or_over_size")
    retrieved_at_utc = retrieved_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        retrieved = datetime.fromisoformat(retrieved_at_utc.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError("ign_retrieval_timestamp_invalid") from None
    if retrieved.utcoffset() is None:
        raise ValueError("ign_retrieval_timestamp_invalid")

    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 32 or sum(entry.file_size for entry in entries) > 64 * 1024 * 1024:
                raise ValueError("ign_archive_expanded_size_invalid")
            if any(Path(entry.filename).is_absolute() or ".." in Path(entry.filename).parts
                   for entry in entries):
                raise ValueError("ign_archive_member_path_invalid")
            members: dict[str, zipfile.ZipInfo] = {}
            for entry in entries:
                if entry.filename in {"MUNICIPIOS.csv", "PROVINCIAS.csv"}:
                    if entry.filename in members:
                        raise ValueError("ign_archive_expected_member_duplicated")
                    if entry.file_size > MAX_EXPANDED_CSV_BYTES:
                        raise ValueError("ign_csv_member_over_size")
                    members[entry.filename] = entry
            if set(members) != {"MUNICIPIOS.csv", "PROVINCIAS.csv"}:
                raise ValueError("ign_archive_expected_members_missing")
            member_timestamps = {
                filename: {
                    "zip_mtime_local": datetime(*members[filename].date_time).isoformat(timespec="seconds"),
                    "timezone_semantics": "ZIP DOS member timestamp; timezone is not encoded",
                }
                for filename in sorted(members)
            }
            province_text = archive.read(members["PROVINCIAS.csv"]).decode("cp1252", "strict")
            municipality_text = archive.read(members["MUNICIPIOS.csv"]).decode("cp1252", "strict")
    except (zipfile.BadZipFile, UnicodeDecodeError, OSError):
        raise ValueError("ign_archive_or_encoding_invalid") from None

    province_reader = csv.DictReader(province_text.splitlines(), delimiter=";", strict=True)
    if tuple(province_reader.fieldnames or ()) != PROVINCE_HEADERS:
        raise ValueError("ign_province_csv_schema_changed")
    province_by_code: dict[str, str] = {}
    for row in province_reader:
        code, name = row.get("COD_PROV"), row.get("PROVINCIA")
        if (not isinstance(code, str) or not re.fullmatch(r"\d{2}", code)
                or not isinstance(name, str) or not name.strip() or code in province_by_code):
            raise ValueError("ign_province_reference_invalid")
        province_by_code[code] = name.strip()

    municipality_reader = csv.DictReader(municipality_text.splitlines(), delimiter=";", strict=True)
    if tuple(municipality_reader.fieldnames or ()) != MUNICIPALITY_HEADERS:
        raise ValueError("ign_municipality_csv_schema_changed")
    references: list[dict[str, Any]] = []
    excluded: dict[str, int] = {}
    all_municipality_codes: set[str] = set()
    for row in municipality_reader:
        if row.get("COD_PROV") not in province_by_code:
            raise ValueError("ign_municipality_province_code_invalid")
        if _fold(row.get("PROVINCIA", "")) != _fold(province_by_code[row["COD_PROV"]]):
            raise ValueError("ign_municipality_province_name_mismatch")
        # COD_INE is the documented 11-digit INE identifier for the
        # municipality row. COD_GEO is not a unique key in this release.
        code, name = row.get("COD_INE"), row.get("NOMBRE_ACTUAL")
        if (not isinstance(code, str) or not re.fullmatch(r"\d{11}", code)
                or not isinstance(name, str) or not name.strip()):
            raise ValueError("ign_municipality_identity_invalid")
        if code in all_municipality_codes:
            raise ValueError("ign_municipality_code_duplicated")
        all_municipality_codes.add(code)
        origin = row.get("ORIGENCOOR", "").strip()
        if _fold(origin) not in ALLOWED_COORDINATE_ORIGINS:
            excluded["coordinate_origin_untrusted"] = excluded.get("coordinate_origin_untrusted", 0) + 1
            continue
        longitude = _finite_coordinate(row.get("LONGITUD_ETRS89_REGCAN95"))
        latitude = _finite_coordinate(row.get("LATITUD_ETRS89_REGCAN95"))
        if (longitude is None or latitude is None
                or not SPAIN_REFERENCE_BOUNDS["min_longitude"] <= longitude <= SPAIN_REFERENCE_BOUNDS["max_longitude"]
                or not SPAIN_REFERENCE_BOUNDS["min_latitude"] <= latitude <= SPAIN_REFERENCE_BOUNDS["max_latitude"]
                or (longitude == 0 and latitude == 0)):
            excluded["coordinates_missing_invalid_or_outside_spain"] = excluded.get(
                "coordinates_missing_invalid_or_outside_spain", 0) + 1
            continue
        population = row.get("POBLACION_MUNI", "").strip()
        if population and not re.fullmatch(r"\d+", population):
            raise ValueError("ign_municipality_population_invalid")
        references.append({
            "municipality_code": code,
            "municipality_name": name.strip(),
            "province_code": row["COD_PROV"],
            "province_name": province_by_code[row["COD_PROV"]],
            "latitude": latitude,
            "longitude": longitude,
            "coordinate_origin": origin,
            "population": int(population) if population else None,
        })
    if len(references) < 7000:
        raise ValueError("ign_reference_municipality_count_implausible")

    archive_sha = _sha256(path)
    normalized_bytes = json.dumps(references, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")).encode("utf-8")
    return {
        "source": REFERENCE_SOURCE,
        "source_id": REFERENCE_SOURCE_ID,
        "source_url": SOURCE_URL,
        "source_file": REFERENCE_FILE,
        "source_dataset_year": REFERENCE_YEAR,
        "source_archive_member_timestamps": member_timestamps,
        "source_sha256": archive_sha,
        "source_byte_size": path.stat().st_size,
        "retrieved_at_utc": retrieved_at_utc,
        "license": "CC-BY 4.0 compatible; attribution required",
        "attribution": "Obra derivada de NGMEP CC-BY 4.0 ign.es",
        "coordinate_reference_system": "ETRS89 (mainland/Balearics/Ceuta/Melilla) or REGCAN95 (Canary Islands), compatible with WGS84",
        "coordinate_axis_order": "longitude,latitude",
        "coordinate_bounds": SPAIN_REFERENCE_BOUNDS,
        "method": "official municipality row; exact municipality+province join; no approximate name aliases",
        "version": REFERENCE_SOURCE_ID,
        "normalized_reference_sha256": hashlib.sha256(normalized_bytes).hexdigest(),
        "municipality_count": len(references),
        "excluded_row_counts": dict(sorted(excluded.items())),
        "municipalities": references,
    }


def write_ign_reference_index(archive_path: str | Path, output_path: str | Path, *,
                              output_root: str | Path,
                              retrieved_at_utc: str | None = None) -> dict[str, Any]:
    """Write a compact derivative index only beneath its approved external root."""
    root = Path(output_root).resolve()
    target = Path(output_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("ign_reference_output_outside_approved_root")
    payload = build_ign_reference_index(archive_path, retrieved_at_utc=retrieved_at_utc)
    data = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, target)
    return {key: payload[key] for key in ("source_id", "source_sha256", "source_byte_size",
            "source_dataset_year", "source_archive_member_timestamps",
            "normalized_reference_sha256", "municipality_count", "excluded_row_counts")}


def resolve_municipality_reference(municipality: str, province: str,
                                   references: Iterable[dict[str, Any]] | dict[tuple[str, str], list[dict[str, Any]]], *,
                                   source_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve one official municipality point by exact name+province only.

    ``references`` is an adapter-owned normalized view of the official IGN
    MUNICIPIOS table. It must expose municipality_name, province_name,
    municipality_code, latitude, longitude, coordinate_origin, and optionally
    population. No nearest-name, locality, city, or facility-address fallback
    is permitted. Duplicate exact administrative names are unresolved.
    """
    if not isinstance(municipality, str) or not municipality.strip() \
            or not isinstance(province, str) or not province.strip():
        return {"outcome": "incomplete_verified_locality"}
    municipality_key = _fold(municipality)
    if isinstance(references, dict):
        matches = references.get((municipality_key, official_province_key(province)), [])
    else:
        matches = [row for row in references
                   if isinstance(row, dict)
                   and isinstance(row.get("municipality_name"), str)
                   and _fold(row["municipality_name"]) == municipality_key
                   and isinstance(row.get("province_name"), str)
                   and same_official_province(province, row["province_name"])]
    if not matches:
        return {"outcome": "not_found"}
    if len(matches) != 1:
        return {"outcome": "ambiguous_exact_municipality_and_province"}
    row = matches[0]
    code = row.get("municipality_code")
    if not isinstance(code, str) or not re.fullmatch(r"(?:\d{5}|\d{11})", code):
        return {"outcome": "invalid_ign_municipality_code"}
    origin = row.get("coordinate_origin")
    if not isinstance(origin, str) or _fold(origin) not in ALLOWED_COORDINATE_ORIGINS:
        return {"outcome": "coordinate_origin_untrusted"}
    latitude, longitude = row.get("latitude"), row.get("longitude")
    if (isinstance(latitude, bool) or isinstance(longitude, bool)
            or not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float))
            or not math.isfinite(latitude) or not math.isfinite(longitude)
            or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
            or (latitude == 0 and longitude == 0)):
        return {"outcome": "invalid_ign_coordinates"}
    metadata = source_metadata or {}
    source_sha256 = row.get("source_artifact_sha256") or metadata.get("source_sha256")
    if not isinstance(source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        return {"outcome": "reference_provenance_missing"}
    source_url = row.get("source_url") or metadata.get("source_url")
    if source_url != SOURCE_URL:
        return {"outcome": "reference_provenance_mismatch"}
    return {
        "outcome": "matched",
        "municipality_code": code,
        "municipality_name": row["municipality_name"],
        "province_name": row["province_name"],
        "latitude": float(latitude),
        "longitude": float(longitude),
        "precision": "locality_reference_coarse",
        "match_method": "exact_ign_municipality_and_official_province",
        "coordinate_origin": origin,
        "population": row.get("population"),
        "reference_source_id": f"{REFERENCE_SOURCE_ID}:{code}",
        "reference_source_url": SOURCE_URL,
        "source_artifact_sha256": source_sha256,
    }


def normalized_reference_key(municipality: str, province: str) -> str:
    """Stable index key for a unique name+province pair (not a fuzzy alias)."""
    if not isinstance(municipality, str) or not municipality.strip() \
            or not isinstance(province, str) or not province.strip():
        raise ValueError("municipality_reference_key_incomplete")
    return f"{_fold(municipality)}|{official_province_key(province)}"


def exact_municipality_reference_index(
    references: Iterable[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Index by exact folded municipality and supported official province key."""
    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in references:
        if (not isinstance(row, dict) or not isinstance(row.get("municipality_name"), str)
                or not isinstance(row.get("province_name"), str)):
            continue
        key = (_fold(row["municipality_name"]), official_province_key(row["province_name"]))
        index.setdefault(key, []).append(row)
    return index


def load_ign_reference_index(path: str | Path, *, expected_source_sha256: str | None = None) -> dict[str, Any]:
    """Load and verify the generated reference index without exposing its rows."""
    index_path = Path(path)
    if not index_path.is_file() or index_path.is_symlink() or index_path.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("ign_reference_index_invalid_or_over_size")
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("ign_reference_index_invalid") from None
    if (not isinstance(index, dict) or index.get("source_id") != REFERENCE_SOURCE_ID
            or index.get("source_url") != SOURCE_URL or index.get("version") != REFERENCE_SOURCE_ID
            or index.get("source_sha256") != expected_source_sha256 and expected_source_sha256 is not None
            or not isinstance(index.get("municipalities"), list)
            or not re.fullmatch(r"[0-9a-f]{64}", str(index.get("source_sha256", "")))):
        raise ValueError("ign_reference_index_provenance_invalid")
    rows = index["municipalities"]
    if len(rows) < 7000 or index.get("municipality_count") != len(rows):
        raise ValueError("ign_reference_index_count_invalid")
    seen_codes: set[str] = set()
    for row in rows:
        if (not isinstance(row, dict)
                or not isinstance(row.get("municipality_code"), str)
                or not re.fullmatch(r"\d{11}", row["municipality_code"])
                or row["municipality_code"] in seen_codes
                or not isinstance(row.get("municipality_name"), str)
                or not isinstance(row.get("province_name"), str)
                or not isinstance(row.get("coordinate_origin"), str)
                or _fold(row["coordinate_origin"]) not in ALLOWED_COORDINATE_ORIGINS):
            raise ValueError("ign_reference_index_row_invalid")
        seen_codes.add(row["municipality_code"])
        latitude, longitude = row.get("latitude"), row.get("longitude")
        if (isinstance(latitude, bool) or isinstance(longitude, bool)
                or not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float))
                or not math.isfinite(latitude) or not math.isfinite(longitude)
                or not SPAIN_REFERENCE_BOUNDS["min_latitude"] <= latitude <= SPAIN_REFERENCE_BOUNDS["max_latitude"]
                or not SPAIN_REFERENCE_BOUNDS["min_longitude"] <= longitude <= SPAIN_REFERENCE_BOUNDS["max_longitude"]
                or (latitude == 0 and longitude == 0)):
            raise ValueError("ign_reference_index_coordinate_invalid")
    normalized = json.dumps(rows, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(normalized).hexdigest() != index.get("normalized_reference_sha256"):
        raise ValueError("ign_reference_index_checksum_mismatch")
    return index
