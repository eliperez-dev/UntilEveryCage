"""Canonical private staging runner for the Denmark Find Smiley source."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pipeline.contracts.private_run import write_private_run_report
from pipeline.contracts.source_health import build_health_snapshot, write_health_snapshot
from pipeline.contracts.source_lifecycle import atomic_json, validate_private_manifest
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.common.review import write_operator_review_packet
from pipeline.common.review_packet import write_review_packet
from .adapter import DenmarkSmileyAdapter


LOGGER = logging.getLogger("uec.denmark.pipeline")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SHARED_STAGES = PROJECT_ROOT / "pipeline" / "scripts" / "stages"
DENMARK_STAGES = PROJECT_ROOT / "pipeline" / "sources" / "denmark" / "stages"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_stage(name: str, script: Path, args: list[str]) -> None:
    """Run one source stage; import and promotion are intentionally absent."""
    command = [sys.executable, str(script), *args]
    LOGGER.info("stage=%s status=started command=%s", name, " ".join(command))
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    LOGGER.info("stage=%s status=completed", name)


def artifact_manifest(run_dir: Path, input_path: Path, started_at: str,
                      completed_at: str, status: str = "success",
                      error: str | None = None) -> Path:
    """Retain the historical inventory manifest for existing operators."""
    artifacts = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name not in {"pipeline-manifest.json", "manifest.json"}:
            artifacts.append({"path": path.relative_to(PROJECT_ROOT).as_posix()
                              if path.is_relative_to(PROJECT_ROOT) else path.as_posix(),
                              "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    manifest = {"status": status, "pipeline": "denmark-smiley-staging",
                "started_at_utc": started_at, "completed_at_utc": completed_at,
                "input_path": input_path.relative_to(PROJECT_ROOT).as_posix()
                if input_path.is_relative_to(PROJECT_ROOT) else input_path.as_posix(),
                "artifacts": artifacts,
                "database_import": "not run; import is an explicit separate command"}
    if error:
        manifest["error"] = error
    return atomic_json(run_dir / "pipeline-manifest.json", manifest)


def _canonical_evidence(run_dir: Path, input_path: Path, metadata: dict,
                        started_at: str, completed_at: str) -> None:
    """Bridge stage reports into the shared private-run contract.

    Validation findings are retained and counted as anomalies; they are not
    silently removed from the normalized stage output.  The shared manifest
    therefore keeps ``normalized_rows`` equal to every parsed row and records
    findings separately in ``anomaly_counts``.
    """
    parse_meta = json.loads((run_dir / "01-parse" / "run-metadata.json").read_text(encoding="utf-8"))
    validation = json.loads((run_dir / "04-validate" / "validation-report.json").read_text(encoding="utf-8"))
    raw_hash = metadata.get("sha256")
    raw_size = metadata.get("byte_size")
    if not isinstance(raw_hash, str) or not isinstance(raw_size, int):
        # A local file without acquisition metadata is still stageable, but
        # cannot receive a credibility health claim.
        raw_hash, raw_size = sha256_file(input_path), input_path.stat().st_size
    retrieved = metadata.get("retrieved_at_utc")
    source_url = metadata.get("final_url") or metadata.get("requested_url")
    manifest = {
        "contract_version": "source-lifecycle-v1",
        "source_id": "dk.smiley",
        "adapter_version": "denmark-smiley-contract-v1",
        "schema_version": "denmark-smiley-contract-v1",
        "source_url": source_url,
        "retrieved_at_utc": retrieved,
        "publication_date": (metadata.get("publication_metadata") or {}).get("Last-Modified"),
        "effective_date": None,
        "sha256": raw_hash,
        "checksum_sha256": raw_hash,
        "byte_size": raw_size,
        "code_version": "denmark-smiley-contract-v1",
        "config_version": "denmark-smiley-contract-v1",
        "input_rows": int(parse_meta["rows_parsed"]),
        "normalized_rows": int(parse_meta["rows_parsed"]),
        "quarantined_rows": 0,
        "release_state": "not-created",
        "publication_state": "private-candidate",
        "review_state": "review_required",
        "privacy_gate": "pending",
        "coordinate_gate": "review_required",
        "parsed_sha256": sha256_file(run_dir / "01-parse" / "parsed-rows.jsonl"),
        "normalized_sha256": sha256_file(run_dir / "03-classify" / "classified-records.jsonl"),
        "anomaly_counts": {str(k): int(v) for k, v in validation.get("counts", {}).items()},
        "acquisition": metadata or {"source_url": source_url, "retrieved_at_utc": retrieved},
        "pipeline_started_at_utc": started_at,
        "pipeline_completed_at_utc": completed_at,
        "coverage": "Danish Find Smiley food-business inspection listings; source rows only; no completeness claim",
    }
    validate_private_manifest(manifest)
    atomic_json(run_dir / "manifest.json", manifest)
    report = write_private_run_report(run_dir, manifest)
    # Using the recorded observation time as the default makes local reruns
    # byte-identical. Callers needing wall-clock freshness may override it.
    if retrieved:
        snapshot = build_health_snapshot(run_dir, as_of_utc=retrieved)
        write_health_snapshot(run_dir / "source-health.json", snapshot)
    classified = run_dir / "03-classify" / "classified-records.jsonl"
    if classified.is_file() and retrieved and source_url:
        artifact = SourceArtifact(
            source_url=str(source_url), retrieved_at_utc=str(retrieved), sha256=str(raw_hash), byte_size=int(raw_size),
            publication_date=manifest.get("publication_date"), effective_date=manifest.get("effective_date"),
            code_version=str(manifest["code_version"]), config_version=str(manifest["config_version"]),
            rights_caveat="Find Smiley source attribution/currentness review remains open; private handoff only",
            privacy_caveat="restricted staging; address and source-coordinate review pending",
            coverage=manifest["coverage"],
        )
        classified_rows = [json.loads(line) for line in classified.read_text(encoding="utf-8").splitlines() if line]
        DenmarkSmileyAdapter().write_candidate_handoff(run_dir / "candidate-handoff", artifact, classified_rows)
        write_operator_review_packet(
            run_dir,
            manifest,
            source_scope=manifest["coverage"],
            checks=("review candidate-handoff/normalized/records.jsonl in restricted staging", "review validation findings before any candidate import", "confirm no public release or API promotion"),
            blockers=("candidate is private and human-gated", "address and coordinate publication blocked", "full pipeline validation findings require operator review"),
        )
    write_review_packet(run_dir, blockers={
        "terms": ["Find Smiley attribution/currentness conditions are recorded; named project release approval remains open."],
        "privacy": ["Address and source-coordinate residential/private-location screening remains required; geocoding is separately review-gated."],
        "completeness": ["Find Smiley coverage is not a census and has no supplied dataset effective date."],
        "classification": ["Source category and stable-key mappings remain explicit; unknown or ambiguous values quarantine."],
        "coverage": ["Source disappearance is not-observed, never closure; candidate import and API checks remain disposable/test-only."],
    })
    LOGGER.info("private evidence source=dk.smiley rows=%d findings=%d qa=%s",
                report["normalized_rows"], validation.get("finding_records", 0), run_dir / "qa.json")


def main(*, run_stage_fn: Callable[[str, Path, list[str]], None] | None = None,
         artifact_manifest_fn: Callable[..., Path] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="Previously archived or local Smileydata.xml")
    parser.add_argument("--fetch", action="store_true", help="Acquire dk.smiley first; requires --terms-review and does not import or promote.")
    parser.add_argument("--terms-review", type=Path, help="Approved terms-review JSON required with --fetch.")
    parser.add_argument("--source-url", help="Optional requested URL override for --fetch.")
    parser.add_argument("--raw-output-root", type=Path, default=PROJECT_ROOT / "data/raw")
    parser.add_argument("--run-id", help="Acquisition run ID for --fetch.")
    parser.add_argument("--rules", type=Path, default=PROJECT_ROOT / "pipeline/config/denmark-classification-v1.json")
    parser.add_argument("--output-dir", type=Path, help="Run directory; defaults to data/staging/<UTC run>")
    parser.add_argument("--expected-rows", type=int)
    parser.add_argument("--geocode-limit", type=int)
    parser.add_argument("--geocode-delay", type=float, default=1.0)
    parser.add_argument("--geocode-provider-config", type=Path, default=PROJECT_ROOT / "pipeline/config/geocoding-dev.json")
    parser.add_argument("--geocode-terms-review", type=Path)
    parser.add_argument("--geocode-suppression-keys", type=Path)
    args = parser.parse_args()
    stage = run_stage_fn or run_stage
    inventory = artifact_manifest_fn or artifact_manifest
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    if args.fetch and args.input is not None:
        parser.error("input cannot be provided with --fetch")
    if not args.fetch and args.input is None:
        parser.error("input is required unless --fetch is used")
    if args.fetch and args.terms_review is None:
        parser.error("--terms-review is required with --fetch")
    if args.geocode_limit is not None and args.geocode_terms_review is None:
        parser.error("--geocode-terms-review is required with --geocode-limit")
    metadata: dict = {}
    if args.fetch:
        acquisition_run_id = args.run_id or (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
        acquisition_args = ["--fetch", "--output-root", str(args.raw_output_root.resolve()), "--terms-review", str(args.terms_review.resolve()), "--run-id", acquisition_run_id]
        if args.source_url:
            acquisition_args.extend(["--url", args.source_url])
        stage("acquire", DENMARK_STAGES / "acquire-denmark-smiley.py", acquisition_args)
        input_path = (args.raw_output_root.resolve() / "dk.smiley" / acquisition_run_id / "Smileydata.xml")
        metadata = json.loads((input_path.parent / "acquisition-metadata.json").read_text(encoding="utf-8"))
    else:
        input_path = args.input.resolve()
        sidecar = input_path.parent / "acquisition-metadata.json"
        if sidecar.is_file():
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    if not input_path.is_file():
        LOGGER.error("pipeline status=failed reason=input_not_found input=%s", input_path)
        return 2
    run_dir = (args.output_dir or PROJECT_ROOT / "data/staging/denmark-smiley" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    try:
        parse_dir, normalize_dir = run_dir / "01-parse", run_dir / "02-normalize"
        classify_dir, validate_dir = run_dir / "03-classify", run_dir / "04-validate"
        geocode_dir = run_dir / "05-geocode-queue"
        stage("parse", DENMARK_STAGES / "parse-denmark-smiley.py", [str(input_path), "--output-dir", str(parse_dir)])
        stage("normalize", DENMARK_STAGES / "normalize-denmark-smiley.py", [str(parse_dir / "parsed-rows.jsonl"), "--output-dir", str(normalize_dir)])
        stage("classify", DENMARK_STAGES / "classify-denmark.py", [str(normalize_dir / "normalized-records.jsonl"), "--rules", str(args.rules.resolve()), "--output-dir", str(classify_dir)])
        validation_args = [str(classify_dir / "classified-records.jsonl"), "--output-dir", str(validate_dir)]
        if args.expected_rows is not None:
            validation_args.extend(["--expected-rows", str(args.expected_rows)])
        stage("validate", DENMARK_STAGES / "validate-denmark.py", validation_args)
        stage("geocode_queue", SHARED_STAGES / "create-geocode-queue.py", [str(classify_dir / "classified-records.jsonl"), "--output-dir", str(geocode_dir)])
        if args.geocode_limit is not None:
            geo = [str(geocode_dir / "geocode-queue.jsonl"), "--output", str(run_dir / "06-geocode-results.jsonl"), "--limit", str(args.geocode_limit), "--delay", str(args.geocode_delay), "--provider-config", str(args.geocode_provider_config.resolve()), "--terms-review", str(args.geocode_terms_review.resolve()), "--network"]
            if args.geocode_suppression_keys:
                geo.extend(["--suppression-keys", str(args.geocode_suppression_keys.resolve())])
            stage("geocode_dawa", DENMARK_STAGES / "geocode-denmark-dawa.py", geo)
        completed_at = utc_now()
        inventory(run_dir, input_path, started_at, completed_at)
        status = {"status": "private-candidate", "publication_state": "private-candidate", "candidate_created": False, "release_promoted": False, "public_surfaces": {"api": False, "map": False, "export": False, "cache": False, "history": False}, "run_dir": str(run_dir)}
        atomic_json(run_dir / "run-status.json", status)
        if (run_dir / "01-parse" / "run-metadata.json").is_file() and (run_dir / "04-validate" / "validation-report.json").is_file():
            _canonical_evidence(run_dir, input_path, metadata, started_at, completed_at)
        # Refresh the inventory after shared evidence is written so operators
        # can verify the complete private run from the historical manifest.
        inventory(run_dir, input_path, started_at, completed_at)
        LOGGER.info("pipeline=denmark-smiley status=success run_dir=%s", run_dir)
    except subprocess.CalledProcessError as error:
        inventory(run_dir, input_path, started_at, utc_now(), "failed", f"stage exited with code {error.returncode}")
        atomic_json(run_dir / "run-status.json", {"status": "failed", "publication_state": "unchanged", "release_promoted": False, "error": str(error), "run_dir": str(run_dir)})
        return error.returncode or 1
    except Exception as error:
        inventory(run_dir, input_path, started_at, utc_now(), "failed", str(error))
        atomic_json(run_dir / "run-status.json", {"status": "failed", "publication_state": "unchanged", "release_promoted": False, "error": str(error), "run_dir": str(run_dir)})
        LOGGER.exception("pipeline=denmark-smiley status=failed")
        return 1
    return 0
