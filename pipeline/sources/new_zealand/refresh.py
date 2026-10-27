"""Refresh the New Zealand MPI RMP register from a user-preserved CSV export.

The published register is a browser search application. This module accepts
the ordinary UI's downloaded CSV and deliberately does not call undocumented
Salesforce endpoints or automate past browser challenges.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.refresh import AdapterCapabilities, RefreshRequest
from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
from pipeline.contracts.source_lifecycle import read_jsonl

from .adapter import ADAPTER_VERSION, SCHEMA_VERSION, SOURCE_ID, SOURCE_URL, NewZealandRmpAdapter

RIGHTS_CAVEAT = (
    "MPI general website terms state CC BY 4.0 with Crown attribution; selected register-export terms and project reuse require review."
)
PRIVACY_CAVEAT = (
    "Operator/address details are retained only in restricted private staging; per-record privacy review and release approval remain pending."
)


class NewZealandRmpRefreshAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    source_kind = "facility_master"

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: Mapping[str, Any]) -> Mapping[str, Any]:
        if mode not in {"local-artifact", "fixture"} or artifact is None or not artifact.is_file():
            raise ValueError("provide the CSV exported from MPI's public RMP register")
        retrieved = options.get("retrieved_at_utc")
        if not isinstance(retrieved, str) or not retrieved.strip():
            raise ValueError("retrieved_at_utc is required for preserved MPI export evidence")
        raw = artifact.read_bytes()
        acquisition = options.get("acquisition")
        if isinstance(acquisition, Mapping):
            expected_sha = acquisition.get("sha256") or acquisition.get("artifact_sha256")
            expected_size = acquisition.get("byte_size") or acquisition.get("artifact_byte_size")
            if expected_sha and expected_sha != hashlib.sha256(raw).hexdigest():
                raise ValueError("acquisition checksum does not match CSV artifact")
            if expected_size is not None and int(expected_size) != len(raw):
                raise ValueError("acquisition byte size does not match CSV artifact")
        source_artifact = SourceArtifact(
            source_url=SOURCE_URL,
            retrieved_at_utc=retrieved,
            sha256=hashlib.sha256(raw).hexdigest(),
            byte_size=len(raw),
            code_version=ADAPTER_VERSION,
            config_version=SCHEMA_VERSION,
            rights_caveat=RIGHTS_CAVEAT,
            privacy_caveat=PRIVACY_CAVEAT,
            coverage="MPI RMP public-register export; programme observations, potentially multi-location; explicit animal-product categories only",
        )
        adapter = NewZealandRmpAdapter()
        lifecycle = run_private_lifecycle(
            artifact, run_dir / "lifecycle", source_artifact, adapter,
            health_as_of_utc=retrieved,
        )
        manifest = lifecycle.get("manifest") or {}
        handoff_manifest: dict[str, Any] = {}
        if lifecycle.get("status") == "candidate-ready":
            lifecycle_root = Path(lifecycle["run_dir"])
            rows = read_jsonl(lifecycle_root / "normalized" / "records.jsonl")
            handoff_manifest = write_handoff(
                run_dir / "candidate-handoff", rows, source_artifact,
                source_id=SOURCE_ID, emit_graph_candidates=False,
            )
        return {
            "lifecycle_status": lifecycle.get("status"),
            "publication_state": lifecycle.get("publication_state", "unchanged"),
            "input_rows": manifest.get("input_rows", 0),
            "normalized_rows": manifest.get("normalized_rows", 0),
            "quarantined_rows": manifest.get("quarantined_rows", 0),
            "candidate_handoff": bool(handoff_manifest),
            "candidate_observation_rows": handoff_manifest.get("normalized_rows", 0),
            "candidate_handoff_sha256": handoff_manifest.get("normalized_sha256"),
            "multi_location_rows": manifest.get("multi_location_rows", 0),
            "activity_counts": manifest.get("activity_counts", {}),
            "schema_fingerprint": manifest.get("schema_fingerprint"),
            "quarantine_reasons": manifest.get("anomaly_counts", {}),
            "source_url": SOURCE_URL,
            "retrieved_at_utc": retrieved,
            "geocoding": "disabled; no coordinates supplied by export",
            "publication": "not-created",
        }


def _run_local(raw: Path, run_dir: Path, retrieved_at_utc: str) -> Mapping[str, Any]:
    return NewZealandRmpRefreshAdapter().refresh(
        mode="local-artifact", run_dir=run_dir, artifact=raw,
        options={"retrieved_at_utc": retrieved_at_utc},
    )


def run_registered_local(*, raw: Path, output_root: Path, retrieved_at_utc: str) -> Mapping[str, Any]:
    """Use the shared runner with this source's local-only capability."""
    catalog = RefreshCatalog()
    catalog.register(
        NewZealandRmpRefreshAdapter(),
        AdapterCapabilities(
            source_id=SOURCE_ID, adapter_version=ADAPTER_VERSION, schema_version=SCHEMA_VERSION,
            acquisition="assisted_only", geocoding="disabled", publication="human_gate_required",
            adapter_path="pipeline.sources.new_zealand.refresh.NewZealandRmpRefreshAdapter",
            country_code="NZ", source_kind="facility_master", operational_classification="assisted",
            live_callable=False,
        ),
    )
    request = RefreshRequest(
        source_ids=(SOURCE_ID,), mode="local-artifact", artifact_paths={SOURCE_ID: str(raw)},
        output_root=output_root,
        options={"retrieved_at_utc": retrieved_at_utc},
    )
    return RefreshRunner(catalog).run(request)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True, help="CSV downloaded from MPI's public RMP register")
    parser.add_argument("--run-dir", type=Path, required=True, help="restricted local run directory")
    parser.add_argument("--retrieved-at-utc", required=True, help="recorded UTC download time, e.g. 2026-10-27T06:21:51Z")
    parser.add_argument("--shared-runner", action="store_true", help="run through the shared aggregate-only refresh runner")
    args = parser.parse_args()
    try:
        if not args.raw.is_file():
            raise FileNotFoundError("CSV artifact does not exist")
        if args.shared_runner:
            result = run_registered_local(raw=args.raw, output_root=args.run_dir,
                                          retrieved_at_utc=args.retrieved_at_utc)
        else:
            result = _run_local(args.raw, args.run_dir, args.retrieved_at_utc)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    # Shared refresh output is already aggregate-only. Source-local output
    # contains no row payloads, identifiers, names, or addresses.
    print(json.dumps(result, sort_keys=True))
    status = result.get("exit_status") or result.get("lifecycle_status")
    return 0 if status in {"ok", "candidate-ready"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
