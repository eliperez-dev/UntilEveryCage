"""Acquire or stage the NVWA list bundle through the shared private lifecycle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.common.review import write_operator_review_packet
from pipeline.common.acquisition import default_run_id, utc_now
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json

from .acquire import acquire_bundle
from .adapter import ADAPTER_VERSION, CONFIG, NvwaApprovedFoodAdapter, SCHEMA_VERSION, SOURCE_ID


REVIEW_BLOCKERS = {
    "terms": ["NVWA states that website content is CC0 unless an item records an exception; verify the source page's current exception notice on each refresh, avoid logo/house-style use, and do not imply NVWA endorsement."],
    "privacy": ["Retain source address/postcode/place only in restricted evidence and the private geocoding queue. Apply personal/private-location screening independently; public-government facility addresses are not blanket per-row manual-review blockers. Publication remains blocked."],
    "completeness": ["The adapter is limited to the eight currently advertised overig_303–310 approval lists; it is not a national facility census and list observations do not equal facilities."],
    "classification": ["Preserve source activity, category, product, species, approval, regulation, lifecycle and remarks as one-to-many source observations; do not infer closure from missing opheffingsdatum."],
    "coverage": ["Page through the live SOAP result and preserve per-list response counts. A disappearing observation is not-observed, not closure or deauthorization."],
}


def _artifact(bundle_path: Path, *, retrieved_at_utc: str | None = None) -> SourceArtifact:
    raw = bundle_path.read_bytes()
    try:
        bundle = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("bundle manifest is invalid JSON") from error
    if bundle.get("source_id") != SOURCE_ID or bundle.get("bundle_version") != "nvwa-approved-food-bundle-v1":
        raise ValueError("bundle manifest is not a supported NVWA approval bundle")
    retrieved = retrieved_at_utc or bundle.get("retrieved_at_utc") or bundle.get("completed_at_utc")
    if not retrieved:
        raise ValueError("retrieved_at_utc is required for private health evidence")
    return SourceArtifact(
        source_url=CONFIG["source_url"], retrieved_at_utc=str(retrieved),
        sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw),
        code_version=ADAPTER_VERSION, config_version=CONFIG["config_version"],
        rights_caveat="NVWA website states CC0 by default unless a specific item notes an exception; no implied endorsement; terms review is recorded separately.",
        privacy_caveat="Restricted private staging; source address evidence is passed to a separate privacy-filtered geocoding queue; publication blocked.",
        coverage=CONFIG["coverage"],
    )


def refresh(
    *, run_dir: str | Path, bundle_path: str | Path | None = None, fetch: bool = False,
    output_root: str | Path = "data/raw", run_id: str | None = None,
    terms_review_path: str | Path = "data/terms-reviews/nl.nvwa.approved-food.json",
    retrieved_at_utc: str | None = None,
    previous_normalized: str | Path | None = None,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    if fetch == (bundle_path is not None):
        raise ValueError("specify exactly one of fetch or bundle_path")
    acquisition = None
    if fetch:
        acquisition = acquire_bundle(
            output_root=output_root, run_id=run_id or default_run_id(),
            terms_review_path=terms_review_path, timeout_seconds=timeout_seconds,
        )
        input_path = Path(acquisition["bundle_path"]).resolve()
    else:
        input_path = Path(bundle_path).resolve()  # type: ignore[arg-type]
        if not input_path.is_file():
            raise ValueError("--bundle must reference an existing retained bundle-manifest.json")
        sidecar = input_path.parent / "bundle-manifest.json"
        if sidecar != input_path:
            raise ValueError("--bundle must reference bundle-manifest.json in its raw artifact directory")

    artifact = _artifact(input_path, retrieved_at_utc=retrieved_at_utc)
    adapter = NvwaApprovedFoodAdapter()
    lifecycle = run_private_lifecycle(
        input_path, Path(run_dir) / "lifecycle", artifact, adapter,
        health_as_of_utc=artifact.retrieved_at_utc,
        previous_normalized_path=previous_normalized,
        review_blockers=REVIEW_BLOCKERS,
    )
    manifest = lifecycle.get("manifest", {})
    schema_status = manifest.get("schema_status", "unknown")
    handoff_written = False
    handoff_sha256 = None
    schema_fingerprint = None
    if lifecycle.get("status") == "candidate-ready" and schema_status != "schema-drift":
        lifecycle_root = Path(lifecycle["run_dir"])
        rows = [
            json.loads(line) for line in
            (lifecycle_root / "normalized" / "records.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        handoff = adapter.write_candidate_handoff(Path(run_dir) / "candidate-handoff", artifact, rows)
        handoff_manifest_path = Path(run_dir) / "candidate-handoff" / "manifest.json"
        handoff_manifest = json.loads(handoff_manifest_path.read_text(encoding="utf-8"))
        handoff_manifest["schema_version"] = SCHEMA_VERSION
        handoff_manifest["config_version"] = CONFIG["config_version"]
        atomic_json(handoff_manifest_path, handoff_manifest)
        handoff_sha256 = handoff.get("normalized_sha256")
        schema_fields = sorted({key for row in rows for key in row.get("normalized", {})})
        schema_fingerprint = hashlib.sha256(json.dumps(
            schema_fields, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        write_operator_review_packet(
            lifecycle_root,
            lifecycle["manifest"],
            source_scope=CONFIG["coverage"],
            checks=(
                "review row-free QA and schema/pagination evidence",
                "confirm each source recognition observation remains source-qualified and list-specific",
                "review the private candidate-handoff in restricted staging",
                "keep addresses in the separate private geocoding queue and no public map/API/export",
            ),
            blockers=(
                "candidate is private and human-gated",
                "publication approval and source lifecycle semantics remain open",
                "address privacy screening and geocoded-result review remain separate gates",
            ),
        )
        lifecycle["candidate_handoff"] = {
            "written": True,
            "normalized_rows": handoff["normalized_rows"],
            "release_state": handoff["release_state"],
            "publication_state": handoff["publication_state"],
        }
        handoff_written = True

    report = {
        "source_id": SOURCE_ID,
        "source_url": artifact.source_url,
        "retrieved_at_utc": artifact.retrieved_at_utc,
        "checksum_sha256": artifact.sha256,
        "byte_size": artifact.byte_size,
        "schema_version": SCHEMA_VERSION,
        "status": "schema-drift" if schema_status == "schema-drift" else lifecycle.get("status"),
        "schema_status": schema_status,
        "input_observations": lifecycle.get("manifest", {}).get("input_rows"),
        "normalized_observations": lifecycle.get("manifest", {}).get("normalized_rows"),
        "quarantined_observations": lifecycle.get("manifest", {}).get("quarantined_rows"),
        "observation_rows_by_list": lifecycle.get("manifest", {}).get("observation_rows_by_list", {}),
        "unique_recognition_numbers_by_list": lifecycle.get("manifest", {}).get("unique_recognition_numbers_by_list", {}),
        "count_semantics": "Counts are observations and recognition numbers within each list only; no summed facility count is computed.",
        "lifecycle_run_dir": lifecycle.get("run_dir"),
        "candidate_handoff": lifecycle.get("candidate_handoff") or {"written": handoff_written},
        "candidate_handoff_sha256": handoff_sha256,
        "schema_fingerprint": schema_fingerprint,
        "publication_state": lifecycle.get("publication_state", "private-candidate"),
        "release_state": "not-created",
        "geocoding": "no provider call during acquisition; address evidence is eligible for the separate private profile and privacy filter",
        "acquisition": acquisition,
    }
    atomic_json(Path(run_dir) / "refresh.json", report)
    return {"report": report, "lifecycle": lifecycle}


class NvwaRefreshAdapter:
    """Strict shared-runner bridge for live and preserved NVWA bundles."""

    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    source_kind = "facility_master"

    def acquire(self, *, run_dir: Path, options: Any) -> dict[str, Any]:
        reviews = options.get("terms_review_paths")
        review_path = reviews.get(SOURCE_ID) if isinstance(reviews, dict) else None
        review_path = review_path or options.get("terms_review_path")
        if not review_path:
            raise ValueError("NVWA live acquisition requires a source terms-review path")
        run_id = str(options.get("acquisition_run_id") or default_run_id())
        output_root = run_dir / "acquisition"
        acquisition = acquire_bundle(
            output_root=output_root,
            run_id=run_id,
            terms_review_path=Path(str(review_path)),
            timeout_seconds=float(options.get("timeout_seconds", 60.0)),
        )
        path = Path(acquisition["bundle_path"])
        raw = path.read_bytes()
        bundle = json.loads(raw.decode("utf-8"))
        evidence = {
            "source_id": SOURCE_ID, "run_id": run_id,
            "requested_url": CONFIG["source_url"], "final_url": CONFIG["source_url"],
            "requested_at_utc": bundle.get("requested_at_utc"),
            "retrieved_at_utc": acquisition["retrieved_at_utc"],
            "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
            "terms_review": bundle.get("terms_review"),
            "rights_caveat": "NVWA site content is stated to be CC0 unless an item says otherwise; no implied endorsement.",
            "privacy_caveat": "Restricted private staging; location evidence enters a separate privacy-filtered profile; no publication approval.",
            "coverage": CONFIG["coverage"], "adapter_version": ADAPTER_VERSION,
            "config_version": CONFIG["config_version"],
        }
        from pipeline.contracts.source_lifecycle import atomic_json
        atomic_json(path.parent / "acquisition-metadata.json", evidence)
        return {
            "artifact_path": str(path),
            "source_url": CONFIG["source_url"],
            "retrieved_at_utc": acquisition["retrieved_at_utc"],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "byte_size": len(raw),
            "code_version": ADAPTER_VERSION,
            "config_version": CONFIG["config_version"],
            "coverage": CONFIG["coverage"],
            "publication_state": "private-only",
            "acquisition_metadata": str(path.parent / "acquisition-metadata.json"),
        }

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: Any) -> dict[str, Any]:
        if mode == "fixture":
            return {
                "lifecycle_status": "no-source-fixture",
                "candidate_handoff": False,
                "review_required": True,
                "public_surfaces": {"api": False, "map": False, "export": False},
            }
        if mode != "local-artifact" or artifact is None:
            raise ValueError("NVWA adapter requires a preserved bundle artifact")
        acquisition = options.get("acquisition") if isinstance(options.get("acquisition"), dict) else {}
        result = refresh(
            run_dir=run_dir,
            bundle_path=artifact,
            retrieved_at_utc=acquisition.get("retrieved_at_utc"),
            previous_normalized=options.get("previous_normalized_path"),
        )
        report = result["report"]
        manifest = result["lifecycle"].get("manifest", {})
        return {
            "lifecycle_status": report.get("status"),
            "publication_state": report.get("publication_state"),
            "input_rows": report.get("input_observations", 0),
            "normalized_rows": report.get("normalized_observations", 0),
            "candidate_observation_rows": report.get("normalized_observations", 0),
            "quarantined_rows": report.get("quarantined_observations", 0),
            "quarantine_reasons": manifest.get("anomaly_counts", {}),
            "observation_rows_by_list": report.get("observation_rows_by_list", {}),
            "unique_recognition_numbers_by_list": report.get("unique_recognition_numbers_by_list", {}),
            "count_semantics": report.get("count_semantics"),
            "candidate_handoff": bool(report.get("candidate_handoff", {}).get("written")),
            "candidate_handoff_sha256": report.get("candidate_handoff_sha256"),
            "schema_fingerprint": report.get("schema_fingerprint"),
            "schema_status": manifest.get("schema_status"),
            "review_required": True,
            "source_artifact_sha256": report.get("checksum_sha256"),
            "source_artifact_byte_size": report.get("byte_size"),
            "retrieved_at_utc": report.get("retrieved_at_utc"),
            "public_surfaces": {"api": False, "map": False, "export": False},
            "release_promoted": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--bundle", type=Path, help="Retained NVWA bundle-manifest.json")
    source.add_argument("--fetch", action="store_true", help="Acquire the current control XML and eight approved-food lists")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--run-id")
    parser.add_argument("--terms-review", type=Path, default=Path("data/terms-reviews/nl.nvwa.approved-food.json"))
    parser.add_argument("--retrieved-at-utc")
    parser.add_argument("--previous-normalized", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()
    try:
        result = refresh(
            run_dir=args.run_dir, bundle_path=args.bundle, fetch=args.fetch,
            output_root=args.output_root, run_id=args.run_id, terms_review_path=args.terms_review,
            retrieved_at_utc=args.retrieved_at_utc,
            previous_normalized=args.previous_normalized, timeout_seconds=args.timeout_seconds,
        )
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result["report"], ensure_ascii=False, sort_keys=True))
    return 0 if result["report"]["status"] in {"candidate-ready", "staged-restricted"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
