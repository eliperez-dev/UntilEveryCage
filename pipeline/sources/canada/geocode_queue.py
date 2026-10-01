"""Build a private, provider-neutral queue for unmapped Canadian facilities."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl


_ADDRESS_FIELDS = {
    "locadd1", "locadd2", "locadd3", "address", "streetaddress",
    "locationaddress", "addressline1", "addressline2", "addressline3",
}


def _address_lines(source_values: dict[str, Any]) -> list[str]:
    fields: list[tuple[int, str]] = []
    for header, raw in source_values.items():
        key = re.sub(r"[^a-z0-9]", "", str(header).lower())
        if key not in _ADDRESS_FIELDS or raw is None:
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
) -> dict[str, Any]:
    """Write restricted queries for accepted records without source points.

    This stage only stages work. A provider must be separately reviewed and
    selected before any asynchronous worker sends a query outside the project.
    """
    root = Path(output_dir)
    queue: list[dict[str, Any]] = []
    seen = queued = source_coordinates = no_address = 0
    for record in records:
        seen += 1
        normalized = record.get("normalized") or {}
        source_values = record.get("source_values") or {}
        if normalized.get("coordinate_state") != "not-supplied-by-source":
            source_coordinates += 1
            continue
        address_lines = _address_lines(source_values)
        if not address_lines:
            no_address += 1
            continue
        parts = address_lines + [
            normalized.get("city"), normalized.get("province"),
            normalized.get("postal_code"), "Canada",
        ]
        query = ", ".join(" ".join(str(part).split()) for part in parts if part)
        queue.append({
            "queue_key": f"{record['source_id']}:{record['source_record_key']}:{artifact.sha256}",
            "source_id": record["source_id"],
            "source_record_key": record["source_record_key"],
            "source_artifact_sha256": artifact.sha256,
            "geocoder_query": query,
            "target_precision": "address",
            "status": "pending-provider-review",
        })
        queued += 1

    queue_path, queue_sha256, _ = atomic_jsonl(root / "geocode-queue.jsonl", queue)
    summary = {
        "status": "success",
        "records_seen": seen,
        "records_queued": queued,
        "records_with_source_coordinates": source_coordinates,
        "records_without_usable_address": no_address,
        "queue_sha256": queue_sha256,
        "queue_byte_size": queue_path.stat().st_size,
        "geocoder_status_policy": "pending; no external geocoder has been called",
        "provider_review_state": "required",
    }
    atomic_json(root / "geocode-queue-metadata.json", summary)
    return summary
