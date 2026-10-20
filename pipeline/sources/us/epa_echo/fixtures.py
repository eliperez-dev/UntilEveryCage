"""Deterministic, synthetic-only EPA-shaped response artifact for fixtures."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from pipeline.contracts.source_lifecycle import atomic_bytes

from .acquire import FIELDS


def synthetic_archive() -> bytes:
    attributes = {field: None for field in FIELDS}
    attributes.update({
        "OBJECTID": 1, "REGISTRY_ID": "SYNTHETIC-REGISTRY-ONLY",
        "FAC_NAME": "Synthetic Example Facility", "FAC_STREET": "100 Example Road",
        "FAC_CITY": "Example City", "FAC_STATE": "ZZ", "FAC_ZIP": "00000",
        "FAC_LAT": 38.25, "FAC_LONG": -77.5, "FAC_COLLECTION_METHOD": "Synthetic",
        "FAC_REFERENCE_POINT": "Synthetic point", "FAC_ACCURACY_METERS": 999,
        "FAC_ACTIVE_FLAG": "Y", "NPDES_FLAG": "Y", "NPDES_IDS": "SYNTHETIC-PERMIT",
        "CWA_PERMIT_TYPES": "NPDES", "CWA_NAICS": "112112", "CWA_SICS": "0211",
        "FAC_NAICS_CODES": "112112", "FAC_SIC_CODES": "0211",
    })
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("result-count.json", json.dumps({"count": 1}))
        archive.writestr("object-ids.json", json.dumps({"objectIds": [1]}))
        archive.writestr("response-0001.json", json.dumps({"features": [{"attributes": attributes}]}))
    return buffer.getvalue()


def write_synthetic_archive(path: str | Path) -> Path:
    return atomic_bytes(path, synthetic_archive())
