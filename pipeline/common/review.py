"""Row-free operator review packets for private source runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from pipeline.contracts.source_lifecycle import atomic_json
from .review_packet import _assert_row_free, platform_context


def write_operator_review_packet(
    run_dir: str | Path,
    manifest: dict[str, Any],
    *,
    source_scope: str,
    checks: Iterable[str],
    blockers: Iterable[str],
) -> dict[str, Any]:
    """Write deterministic, row-free review instructions beside a run."""
    packet = {
        "packet_version": "operator-review-v1",
        "source_id": manifest["source_id"],
        "source_scope": source_scope,
        "source_url": manifest.get("source_url"),
        "retrieved_at_utc": manifest.get("retrieved_at_utc"),
        "effective_date": manifest.get("effective_date"),
        "checksum_sha256": manifest.get("checksum_sha256"),
        "schema_version": manifest.get("schema_version"),
        "schema_fingerprint": manifest.get("schema_fingerprint"),
        "adapter_version": manifest.get("adapter_version"),
        "counts": {
            "input_rows": manifest.get("input_rows", 0),
            "normalized_rows": manifest.get("normalized_rows", 0),
            "quarantined_rows": manifest.get("quarantined_rows", 0),
        },
        "anomaly_counts": manifest.get("anomaly_counts", {}),
        "review_state": "review_required",
        "publication_state": "private-candidate",
        "release_state": "not-created",
        "geocoding": "disabled",
        "checks": sorted(set(checks)),
        "blockers": sorted(set(blockers)),
        "platform": platform_context(manifest.get("source_id")),
        "publication_boundary": "awaiting-owner-review; this packet is row-free evidence and cannot approve or promote a release",
        "row_payloads_included": False,
    }
    _assert_row_free(packet)
    atomic_json(Path(run_dir) / "operator-review-packet.json", packet)
    return packet
