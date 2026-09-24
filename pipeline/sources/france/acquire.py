"""Bounded private acquisition for the two current DGAL 853/2004 TXT routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.common.acquisition import fetch_source

from .adapter import FranceDgalSectionIAdapter, FranceDgalSectionIIAdapter

ADAPTERS = {"I": FranceDgalSectionIAdapter, "II": FranceDgalSectionIIAdapter}


def fetch_section(*, section: str, output_root: str | Path, terms_review_path: str | Path, run_id: str | None = None, timeout_seconds: float = 60.0, max_bytes: int = 32 * 1024 * 1024) -> dict[str, Any]:
    adapter = ADAPTERS[section]()
    return fetch_source(source_id=adapter.source_id, url=adapter.source_url, output_root=output_root, artifact_name="source.txt", terms_review_path=terms_review_path, run_id=run_id, timeout_seconds=timeout_seconds, max_bytes=max_bytes, allowed_content_types=("text/plain", "text/csv", "application/octet-stream"), code_version=adapter.adapter_version, config_version=adapter.schema_version, coverage=f"France DGAL Regulation (EC) 853/2004 Section {section}; source rows only", rights_caveat="Ministry legal notice: non-commercial reuse of data not covered by copyright subject to integrity and attribution; this run is private preview only; public release requires separate review.", privacy_caveat="Private staging; names, addresses, SIRET, and any location enrichment require review.")
