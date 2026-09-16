"""Bounded private acquisition for Ontario and the CFIA federal registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.common.acquisition import fetch_source

from .adapter import CfiaFederalMeatAdapter, OntarioMeatPlantsAdapter

ADAPTERS = {"ontario": OntarioMeatPlantsAdapter, "cfia": CfiaFederalMeatAdapter}


def fetch_source_artifact(*, source: str, output_root: str | Path, terms_review_path: str | Path, run_id: str | None = None, timeout_seconds: float = 60.0, max_bytes: int = 64 * 1024 * 1024) -> dict[str, Any]:
    adapter = ADAPTERS[source]()
    return fetch_source(source_id=adapter.source_id, url=adapter.source_url, output_root=output_root, artifact_name="source.csv", terms_review_path=terms_review_path, run_id=run_id, timeout_seconds=timeout_seconds, max_bytes=max_bytes, allowed_content_types=("text/csv", "application/csv", "application/octet-stream", "text/plain"), code_version=adapter.adapter_version, config_version=adapter.schema_version, coverage=adapter.coverage, rights_caveat="Government source; current licence, attribution, and redistribution review remain explicit gates.", privacy_caveat="Private staging; names, addresses, phones, and coordinates require review.")
