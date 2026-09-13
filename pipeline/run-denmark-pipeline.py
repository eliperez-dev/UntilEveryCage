#!/usr/bin/env python3
"""Run the auditable Denmark staging pipeline from one command."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


LOGGER = logging.getLogger("uec.denmark.pipeline")
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "pipeline" / "scripts" / "stages"


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
    parser.add_argument("input", type=Path, help="Downloaded official Smileydata.xml")
    parser.add_argument("--rules", type=Path, default=ROOT / "pipeline/config/denmark-classification-v1.json")
    parser.add_argument("--output-dir", type=Path, help="Run directory; defaults to data/staging/<UTC run>")
    parser.add_argument("--expected-rows", type=int)
    parser.add_argument("--geocode-limit", type=int, help="Optionally call DAWA for only this many queued records")
    parser.add_argument("--geocode-delay", type=float, default=1.0)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    input_path = args.input.resolve()
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
        run_stage("parse", SCRIPTS / "parse-denmark-smiley.py", [str(input_path), "--output-dir", str(parse_dir)])
        run_stage("normalize", SCRIPTS / "normalize-denmark-smiley.py", [str(parse_dir / "parsed-rows.jsonl"), "--output-dir", str(normalize_dir)])
        run_stage("classify", SCRIPTS / "classify-denmark.py", [str(normalize_dir / "normalized-records.jsonl"), "--rules", str(args.rules.resolve()), "--output-dir", str(classify_dir)])
        validation_args = [str(classify_dir / "classified-records.jsonl"), "--output-dir", str(validate_dir)]
        if args.expected_rows is not None:
            validation_args.extend(["--expected-rows", str(args.expected_rows)])
        run_stage("validate", SCRIPTS / "validate-denmark.py", validation_args)
        run_stage("geocode_queue", SCRIPTS / "create-geocode-queue.py", [str(classify_dir / "classified-records.jsonl"), "--output-dir", str(geocode_dir)])
        if args.geocode_limit is not None:
            run_stage("geocode_dawa", SCRIPTS / "geocode-denmark-dawa.py", [str(geocode_dir / "geocode-queue.jsonl"), "--output", str(run_dir / "06-geocode-results.jsonl"), "--limit", str(args.geocode_limit), "--delay", str(args.geocode_delay)])
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
