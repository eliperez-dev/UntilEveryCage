"""Bounded acquisition of AESAN's published RGSEAA full-list workbook."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.common.acquisition import fetch_source

from .adapter import CONFIG, RgseaaAdapter


def _validate_workbook(path: Path, _headers: dict[str, str]) -> None:
    try:
        RgseaaAdapter().parse_bytes(path.read_bytes())
    except ValueError as error:
        raise ValueError("AESAN RGSEAA workbook schema is unsupported") from error


def fetch(*, output_root: Path, run_id: str, terms_review_path: Path,
          timeout_seconds: float = 60.0, max_bytes: int = 64 * 1024 * 1024) -> dict[str, Any]:
    return fetch_source(
        source_id=CONFIG["source_id"], url=CONFIG["source_url"], output_root=output_root,
        artifact_name="rgseaa.xlsx", terms_review_path=terms_review_path, run_id=run_id,
        timeout_seconds=timeout_seconds, max_bytes=max_bytes,
        allowed_content_types=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",),
        code_version=CONFIG["adapter_version"], config_version=CONFIG["config_version"],
        coverage=CONFIG["coverage"],
        rights_caveat=("AESAN legal notice permits reuse subject to non-distortion, source attribution, "
                       "and last-update citation unless a contrary or third-party notice applies; "
                       "private processing only, no release approval"),
        privacy_caveat=("Restricted private evidence; source business labels and industrial addresses "
                        "remain in the private candidate handoff for display and queued location "
                        "enrichment; acquisition makes no provider calls or public release"),
        artifact_validator=_validate_workbook,
    )
