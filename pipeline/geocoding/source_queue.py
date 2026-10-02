"""Shared provider-neutral address queue for post-acquisition enrichment."""
from __future__ import annotations

import math
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl


_ADDRESS_KEYS = frozenset({
    "address", "streetaddress", "street", "streetaddressline", "addressline",
    "addressline1", "addressline2", "addressline3", "locadd1", "locadd2",
    "locadd3", "locationaddress", "streetaddress1", "streetaddress2",
})


def _has_valid_source_coordinates(normalized: dict[str, Any]) -> bool:
    if normalized.get("coordinate_state") in {
        "source-coordinate", "source_coordinates_preserved",
        "source-value-present-pending-review",
    }:
        return True
    value = normalized.get("coordinates")
    if not isinstance(value, dict):
        return False
    try:
        latitude = float(value.get("latitude"))
        longitude = float(value.get("longitude"))
    except (TypeError, ValueError):
        return False
    return (
        math.isfinite(latitude) and math.isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
        and not (latitude == 0 and longitude == 0)
    )


def _source_address(source_values: dict[str, Any]) -> list[str]:
    fields: list[tuple[int, str]] = []
    for header, raw in source_values.items():
        key = re.sub(r"[^a-z0-9]", "", str(header).lower())
        if key not in _ADDRESS_KEYS or raw is None:
            continue
        value = " ".join(str(raw).split())
        if value:
            suffix = re.search(r"([123])$", key)
            fields.append((int(suffix.group(1)) if suffix else 1, value))
    return [value for _, value in sorted(fields)]


def build_geocode_queue(
    records: Iterable[dict[str, Any]],
    artifact: SourceArtifact,
    output_dir: str | Path,
    *,
    country_name: str | None = None,
) -> dict[str, Any]:
    """Stage provider-neutral address queries for accepted records without points.

    Valid source coordinates take precedence. Queries use allowlisted address
    fields and omit names/contact fields; no external provider is called.
    """
    root = Path(output_dir)
    queue: list[dict[str, Any]] = []
    seen = source_coordinates = no_address = 0
    for record in records:
        seen += 1
        normalized = record.get("normalized") or {}
        if _has_valid_source_coordinates(normalized):
            source_coordinates += 1
            continue
        parts = []
        address = normalized.get("facility_address") or normalized.get("address")
        if isinstance(address, str) and address.strip():
            parts.append(" ".join(address.split()))
        else:
            parts.extend(_source_address(record.get("source_values") or {}))
        parts.extend(str(normalized.get(field)).strip() for field in
                     ("city", "municipality", "state", "province", "region", "postal_code", "postcode")
                     if normalized.get(field) and str(normalized.get(field)).strip())
        country = normalized.get("nation") or normalized.get("country_code") or country_name
        if country:
            parts.append(str(country).strip())
        query = ", ".join(dict.fromkeys(" ".join(part.split()) for part in parts if part))
        if not query:
            no_address += 1
            continue
        source_key = record.get("source_record_key")
        source_id = record.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip() or not isinstance(source_key, (str, int)) or not str(source_key).strip():
            raise ValueError("location queue record is missing its source-scoped key")
        queue.append({
            "queue_key": f"{source_id}:{source_key}:{artifact.sha256}",
            "source_id": source_id,
            "source_record_key": str(source_key),
            "source_artifact_sha256": artifact.sha256,
            "source_url": artifact.source_url,
            "geocoder_query": query,
            "target_precision": "address",
            "status": "pending-provider-configuration",
        })

    queue_path, queue_sha256, _ = atomic_jsonl(root / "geocode-queue.jsonl", queue)
    summary = {
        "status": "success",
        "records_seen": seen,
        "records_queued": len(queue),
        "records_with_source_coordinates": source_coordinates,
        "records_without_usable_address": no_address,
        "queue_sha256": queue_sha256,
        "queue_byte_size": queue_path.stat().st_size,
        "geocoder_status_policy": "pending; no external geocoder has been called",
        "provider_review_state": "not_configured",
    }
    atomic_json(root / "geocode-queue-metadata.json", summary)
    return summary
