"""Shared provider-neutral address queue for post-acquisition enrichment."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl


def _has_valid_source_coordinates(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        latitude = float(value.get("latitude"))
        longitude = float(value.get("longitude"))
    except (TypeError, ValueError):
        return False
    return (
        -90 <= latitude <= 90
        and -180 <= longitude <= 180
        and not (latitude == 0 and longitude == 0)
    )


def build_source_location_queue(
    records: Iterable[dict[str, Any]],
    artifact: SourceArtifact,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Stage address lookups from normalized facility-location fields only.

    Valid source coordinates take precedence. Queries omit names and contact
    fields, and this function never calls an external provider.
    """
    root = Path(output_dir)
    queue: list[dict[str, Any]] = []
    seen = source_coordinates = no_address = 0
    for record in records:
        seen += 1
        normalized = record.get("normalized") or {}
        coordinates = normalized.get("coordinates")
        if _has_valid_source_coordinates(coordinates):
            source_coordinates += 1
            continue
        address = normalized.get("facility_address") or normalized.get("address")
        if not isinstance(address, str) or not address.strip():
            no_address += 1
            continue
        parts = [address, normalized.get("city"), normalized.get("province") or normalized.get("region"),
                 normalized.get("postal_code"), normalized.get("nation") or normalized.get("country_code")]
        query = ", ".join(" ".join(str(part).split()) for part in parts if isinstance(part, str) and part.strip())
        if not query:
            no_address += 1
            continue
        source_key = record.get("source_record_key")
        if not isinstance(source_key, (str, int)) or not str(source_key).strip():
            raise ValueError("location queue record is missing its source-scoped key")
        queue.append({
            "queue_key": f"{record['source_id']}:{source_key}:{artifact.sha256}",
            "source_id": record["source_id"],
            "source_record_key": str(source_key),
            "source_artifact_sha256": artifact.sha256,
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
        "geocoder_status_policy": "pending provider configuration; no external geocoder has been called",
        "provider_review_state": "not_configured",
    }
    atomic_json(root / "geocode-queue-metadata.json", summary)
    return summary
