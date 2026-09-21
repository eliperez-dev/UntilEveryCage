"""D3 mixed source rehearsal built on the shared private refresh runner.

The rehearsal selects the seven D2 facility lanes plus the expected D3 US
facility/evidence lanes.  The latter remain intentionally unregistered until
their source-owned registration is integrated.  Fixture mode runs only
preserved synthetic artifacts; live mode is a fail-closed capability check and
does not make network requests.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.common.d2_e2e_readiness import D2_SOURCE_IDS
from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
from pipeline.contracts.refresh import RefreshRequest


D3_EXPECTED_SOURCE_IDS = ("us.fsis", "us.aphis", "us.inspections")
D3_REHEARSAL_SOURCE_IDS = D2_SOURCE_IDS + D3_EXPECTED_SOURCE_IDS
D3_REPORT_VERSION = "d3-live-operations-v1"

# These are synthetic/preserved fixture locations already owned by source
# packages.  Only availability booleans leave this module; paths never enter
# the row-free report.
_FIXTURE_PATHS = {
    "us.fsis": (Path("pipeline/sources/us/fsis/fixtures/valid.csv"),),
    "us.aphis": (
        Path("pipeline/sources/us/aphis/fixtures/registrations.csv"),
        Path("pipeline/sources/us/aphis/fixtures/annual_reports.csv"),
        Path("pipeline/sources/us/aphis/fixtures/inspections.csv"),
    ),
    "us.inspections": (Path("pipeline/sources/us/aphis/fixtures/inspections.csv"),),
}


def _fixture_availability(root: Path) -> dict[str, dict[str, Any]]:
    return {
        source_id: {
            "fixture_available": all((root / path).is_file() for path in paths),
            "fixture_files": len(paths),
            "registration_state": "awaiting-source-owned-registration",
        }
        for source_id, paths in _FIXTURE_PATHS.items()
    }


def build_mixed_rehearsal(*, run_root: str | Path, mode: str = "fixture",
                          as_of_utc: str = "2026-01-01T00:00:00Z", resume: bool = False) -> dict[str, Any]:
    """Run the deterministic D3 mixed plan and return a row-free report."""
    if mode not in {"fixture", "local-artifact", "live-acquisition"}:
        raise ValueError("mode must be fixture, local-artifact, or live-acquisition")
    root = Path(run_root)
    repository_root = Path(__file__).resolve().parents[2]
    options = {
        "as_of_utc": as_of_utc,
        "rehearsal": "d3-mixed-facility-and-evidence",
        "eligible_source_ids": list(D3_REHEARSAL_SOURCE_IDS),
    }
    request = RefreshRequest(
        all_eligible=True,
        mode=mode,
        output_root=root,
        retries=2,
        resume=resume,
        options=options,
    )
    result = RefreshRunner(RefreshCatalog()).run(request)
    result["d3"] = {
        "schema_version": D3_REPORT_VERSION,
        "mixed_scope": {
            "d2_facility_sources": list(D2_SOURCE_IDS),
            "expected_d3_sources": list(D3_EXPECTED_SOURCE_IDS),
            "selected_sources": list(D3_REHEARSAL_SOURCE_IDS),
            "execution": "sequential",
        },
        "fixture_availability": _fixture_availability(repository_root),
        "live_access": {
            "performed": False,
            "network_requests": 0,
            "reason": "live modes remain fail-closed until source-owned registration and terms authorization",
        },
        "readiness": {
            "state": "private-rehearsal-only" if result["exit_status"] == "ok" else "attention-required",
            "terms_review": "required",
            "human_review": "required",
            "public_release_allowed": False,
            "release_created": False,
            "promoted": False,
        },
        "operator_exit": {
            "success": "all selected sources completed without failed or unsupported lanes",
            "failure": "any failed or unsupported lane returns exit code 1; configuration errors return 2",
        },
    }
    output = root / "d3-live-operations-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result
