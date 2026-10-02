"""Build a private, provider-neutral queue for unmapped Canadian facilities."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.common.geocode_queue import build_geocode_queue as _build_shared_queue


def build_geocode_queue(
    records: Iterable[dict[str, Any]],
    artifact: SourceArtifact,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Build the shared provider-neutral queue for Canadian rows."""
    return _build_shared_queue(records, artifact, output_dir, country_name="Canada")
