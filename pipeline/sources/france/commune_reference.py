"""Acquire the current official French commune centres for coarse display."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any

from pipeline.common.acquisition import utc_now
from pipeline.contracts.source_lifecycle import atomic_json


SOURCE_URL = "https://geo.api.gouv.fr/communes?fields=nom,code,codeDepartement,centre&format=json"
REFERENCE_URL = "https://www.data.gouv.fr/datasets/admin-express-admin-express-cog-admin-express-cog-carto-admin-express-cog-carto-plus-pe"
VERSION = "geo-api-communes-centre-v1"
LICENSE = "Licence Ouverte / Open Licence 2.0 (Etalab)"
MAX_BYTES = 64 * 1024 * 1024


def _key(value: str) -> str:
    value = re.sub(r"['’ʼ`´]", "", value)
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=path.parent, prefix=".communes-", suffix=".part") as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    os.replace(temporary, path)


def acquire_centres(*, output_root: Path, run_id: str, timeout_seconds: float = 60.0) -> dict[str, Any]:
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "UntilEveryCage/controlled-acquisition", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        if response.status != 200 or response.geturl() != SOURCE_URL:
            raise ValueError("French commune reference endpoint changed or redirected")
        headers = {name: response.headers[name] for name in ("Content-Type", "Last-Modified", "ETag", "Date") if response.headers.get(name)}
        raw = response.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("French commune reference exceeded its empty/size bound")
    try:
        items = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("French commune reference response is not supported JSON") from error
    if not isinstance(items, list) or not items:
        raise ValueError("French commune reference has no commune collection")
    retrieved_at = utc_now()
    source_hash = hashlib.sha256(raw).hexdigest()
    root = output_root / run_id
    root.mkdir(parents=True, exist_ok=True)
    raw_path = root / "communes.json"
    _atomic_bytes(raw_path, raw)
    by_name_department: dict[str, dict[str, Any]] = {}
    ambiguous_keys: set[str] = set()
    for row in items:
        if not isinstance(row, dict):
            raise ValueError("French commune reference schema changed")
        name, code, department = row.get("nom"), row.get("code"), row.get("codeDepartement")
        centre = row.get("centre")
        coordinates = centre.get("coordinates") if isinstance(centre, dict) else None
        if not isinstance(name, str) or not name.strip() or not isinstance(code, str) or not isinstance(department, str) or not isinstance(coordinates, list) or len(coordinates) != 2:
            raise ValueError("French commune reference is missing a required field")
        try:
            longitude, latitude = float(coordinates[0]), float(coordinates[1])
        except (TypeError, ValueError) as error:
            raise ValueError("French commune reference has invalid coordinates") from error
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180) or (latitude == 0 and longitude == 0):
            raise ValueError("French commune reference has out-of-range coordinates")
        key = f"{_key(name)}|{_key(department)}"
        entry = {"municipality": name, "insee_code": code, "department_code": department,
                 "latitude": latitude, "longitude": longitude}
        if key in ambiguous_keys:
            continue
        if key in by_name_department:
            by_name_department.pop(key)
            ambiguous_keys.add(key)
            continue
        by_name_department[key] = entry
    if not by_name_department:
        raise ValueError("French commune reference contains no usable centres")
    metadata = {
        "source": "Etalab / geo.api.gouv.fr API Découpage administratif",
        "source_url": SOURCE_URL,
        "source_reference_url": REFERENCE_URL,
        "license": LICENSE,
        "attribution": "Etalab / IGN; French administrative commune reference",
        "version": VERSION,
        "reference_date": "current endpoint response; upstream release date not supplied",
        "retrieved_at_utc": retrieved_at,
        "source_last_modified": headers.get("Last-Modified"),
        "response_headers": headers,
        "source_sha256": source_hash,
        "source_byte_size": len(raw),
        "schema_fingerprint": hashlib.sha256(b"communes[nom,code,codeDepartement,centre.coordinates(lon,lat)]").hexdigest(),
        "method": "exact normalized commune name plus official department code; reference centre only; never a facility point",
        "municipality_count": len(by_name_department),
        "ambiguous_name_department_pairs_excluded": len(ambiguous_keys),
    }
    payload = {**metadata, "municipalities": by_name_department}
    index_path = root / "municipality-centres.json"
    atomic_json(index_path, payload)
    index_hash = hashlib.sha256(index_path.read_bytes()).hexdigest()
    return {**metadata, "path": str(index_path), "derived_index_sha256": index_hash,
            "derived_index_byte_size": index_path.stat().st_size, "run_id": run_id}
