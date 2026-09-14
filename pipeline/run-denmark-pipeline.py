#!/usr/bin/env python3
"""Run the auditable Denmark staging pipeline from one command."""

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


LOGGER = logging.getLogger("uec.denmark.pipeline")
ROOT = Path(__file__).resolve().parent.parent
SHARED_STAGES = ROOT / "pipeline" / "scripts" / "stages"
DENMARK_STAGES = ROOT / "pipeline" / "sources" / "denmark" / "stages"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_stage(name: str, script: Path, args: list[str]) -> None:
    command = [sys.executable, str(script), *args]
    LOGGER.info("stage=%s status=started command=%s", name, " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)
    LOGGER.info("stage=%s status=completed", name)


def artifact_manifest(run_dir: Path, input_path: Path, started_at: str, completed_at: str, status: str = "success", error: str | None = None) -> Path:
    artifacts = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "pipeline-manifest.json":
            artifacts.append({
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    manifest = {
        "status": status,
        "pipeline": "denmark-smiley-staging",
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "input_path": input_path.relative_to(ROOT).as_posix() if input_path.is_relative_to(ROOT) else input_path.as_posix(),
        "artifacts": artifacts,
        "database_import": "not run; import is an explicit separate command",
    }
    if error:
        manifest["error"] = error
    path = run_dir / "pipeline-manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="Previously archived or local Smileydata.xml")
    parser.add_argument("--fetch", action="store_true", help="Acquire dk.smiley first; requires --terms-review and does not import or promote.")
    parser.add_argument("--terms-review", type=Path, help="Approved terms-review JSON required with --fetch.")
    parser.add_argument("--source-url", help="Optional requested URL override for --fetch.")
    parser.add_argument("--raw-output-root", type=Path, default=ROOT / "data/raw", help="Archive root for --fetch.")
    parser.add_argument("--run-id", help="Acquisition run ID for --fetch.")
    parser.add_argument("--rules", type=Path, default=ROOT / "pipeline/config/denmark-classification-v1.json")
    parser.add_argument("--output-dir", type=Path, help="Run directory; defaults to data/staging/<UTC run>")
    parser.add_argument("--expected-rows", type=int)
    parser.add_argument("--geocode-limit", type=int, help="Optionally call DAWA for only this many queued records")
    parser.add_argument("--geocode-delay", type=float, default=1.0)
    parser.add_argument("--geocode-provider-config", type=Path, default=ROOT / "pipeline/config/geocoding-dev.json")
    parser.add_argument("--geocode-terms-review", type=Path, help="Approved per-run terms review required to make bounded geocoding requests.")
    parser.add_argument("--geocode-suppression-keys", type=Path, help="Payload-free source identity references excluded from geocoding.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    if args.fetch and args.input is not None:
        parser.error("input cannot be provided with --fetch")
    if not args.fetch and args.input is None:
        parser.error("input is required unless --fetch is used")
    if args.fetch and args.terms_review is None:
        parser.error("--terms-review is required with --fetch")
    if args.geocode_limit is not None and args.geocode_terms_review is None:
        parser.error("--geocode-terms-review is required with --geocode-limit")
    if args.fetch:
        terms_review_path = args.terms_review.resolve()
        raw_output_root = args.raw_output_root.resolve()
        acquisition_run_id = args.run_id or (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
        acquisition_args = ["--fetch", "--output-root", str(raw_output_root), "--terms-review", str(terms_review_path), "--run-id", acquisition_run_id]
        if args.source_url:
            acquisition_args.extend(["--url", args.source_url])
        run_stage("acquire", DENMARK_STAGES / "acquire-denmark-smiley.py", acquisition_args)
        acquisition_root = raw_output_root / "dk.smiley"
        input_path = (acquisition_root / acquisition_run_id / "Smileydata.xml").resolve()
        acquisition_metadata = json.loads((input_path.parent / "acquisition-metadata.json").read_text(encoding="utf-8"))
        acquired_source_url = acquisition_metadata.get("final_url") or acquisition_metadata.get("requested_url")
    else:
        input_path = args.input.resolve()
        acquired_source_url = None
    if not input_path.is_file():
        LOGGER.error("pipeline status=failed reason=input_not_found input=%s", input_path)
        return 2
    run_name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (args.output_dir or ROOT / "data/staging/denmark-smiley" / run_name).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    LOGGER.info("pipeline=denmark-smiley status=started run_dir=%s", run_dir)

    try:
        parse_dir = run_dir / "01-parse"
        normalize_dir = run_dir / "02-normalize"
        classify_dir = run_dir / "03-classify"
        validate_dir = run_dir / "04-validate"
        geocode_dir = run_dir / "05-geocode-queue"
        parse_args = [str(input_path), "--output-dir", str(parse_dir)]
        if acquired_source_url and acquired_source_url != "unknown":
            parse_args.extend(["--source-url", acquired_source_url])
        run_stage("parse", DENMARK_STAGES / "parse-denmark-smiley.py", parse_args)
        run_stage("normalize", DENMARK_STAGES / "normalize-denmark-smiley.py", [str(parse_dir / "parsed-rows.jsonl"), "--output-dir", str(normalize_dir)])
        run_stage("classify", DENMARK_STAGES / "classify-denmark.py", [str(normalize_dir / "normalized-records.jsonl"), "--rules", str(args.rules.resolve()), "--output-dir", str(classify_dir)])
        validation_args = [str(classify_dir / "classified-records.jsonl"), "--output-dir", str(validate_dir)]
        if args.expected_rows is not None:
            validation_args.extend(["--expected-rows", str(args.expected_rows)])
        run_stage("validate", DENMARK_STAGES / "validate-denmark.py", validation_args)
        run_stage("geocode_queue", SHARED_STAGES / "create-geocode-queue.py", [str(classify_dir / "classified-records.jsonl"), "--output-dir", str(geocode_dir)])
        if args.geocode_limit is not None:
            geocode_args = [str(geocode_dir / "geocode-queue.jsonl"), "--output", str(run_dir / "06-geocode-results.jsonl"), "--limit", str(args.geocode_limit), "--delay", str(args.geocode_delay), "--provider-config", str(args.geocode_provider_config.resolve()), "--terms-review", str(args.geocode_terms_review.resolve()), "--network"]
            if args.geocode_suppression_keys:
                geocode_args.extend(["--suppression-keys", str(args.geocode_suppression_keys.resolve())])
            run_stage("geocode_dawa", DENMARK_STAGES / "geocode-denmark-dawa.py", geocode_args)
        manifest = artifact_manifest(run_dir, input_path, started_at, utc_now())
        LOGGER.info("pipeline=denmark-smiley status=success manifest=%s", manifest)
    except subprocess.CalledProcessError as error:
        manifest = artifact_manifest(run_dir, input_path, started_at, utc_now(), "failed", f"stage exited with code {error.returncode}")
        LOGGER.error("pipeline=denmark-smiley status=failed stage_exit_code=%d manifest=%s", error.returncode, manifest)
        return error.returncode or 1
    except Exception as error:
        manifest = artifact_manifest(run_dir, input_path, started_at, utc_now(), "failed", str(error))
        LOGGER.exception("pipeline=denmark-smiley status=failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
