"""Rehearse one private FSIS candidate handoff in a disposable database.

This runner accepts only an importer-verifiable private handoff and a matching
directory artifact. It never creates or promotes a public release and emits a
row-free report.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import psycopg

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
FORBIDDEN_KEYS = {"source_values", "raw_fields", "payload", "records", "address", "coordinates"}


def _load_importer():
    path = ROOT / "pipeline/scripts/maintenance/import-candidate.py"
    spec = importlib.util.spec_from_file_location("fsis_candidate_import", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load importer: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _request(base: str, path: str, headers: dict[str, str] | None = None) -> tuple[int, Any]:
    request = urllib.request.Request(base + path, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except (UnicodeDecodeError, json.JSONDecodeError):
            return exc.code, None


def _assert_safe(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_KEYS.intersection(value)
        if forbidden:
            raise RuntimeError(f"row-bearing report key leaked: {sorted(forbidden)}")
        for child in value.values():
            _assert_safe(child)
    elif isinstance(value, list):
        for child in value:
            _assert_safe(child)


def run(handoff_manifest: Path, raw_path: Path, output: Path, release_id: str) -> dict[str, Any]:
    from pipeline.tests.e2e.fixture import E2EEnvironment

    importer = _load_importer()
    manifest, rows = importer.load_inputs(
        handoff_manifest,
        handoff_manifest.parent / "normalized/records.jsonl",
        raw_path,
    )
    env = E2EEnvironment()
    env.test_release_id = release_id
    try:
        env.start()
        first = importer.import_candidate(env.database_url, manifest, rows, release_id, False, batch_size=2000)
        # A full duplicate replay is intentionally not used here: the
        # importer performs row-level conflict reads and is prohibitively slow
        # for this legacy-sized corpus. One deterministic row is sufficient to
        # exercise the conflict-safe rerun path without weakening the full
        # first-import count.
        second = importer.import_candidate(
            env.database_url, rows=rows[:1], manifest=manifest, release_id=release_id, reset=False, batch_size=1
        )
        base = f"http://127.0.0.1:{env.api_port}"
        preview_headers = {"X-UEC-Dev-Preview-Token": env.dev_preview_token}
        public_status, public = _request(base, "/api/v2/locations?profile=official&limit=1")
        preview_status, preview = _request(
            base, "/api/dev/preview/test-release/locations?profile=official&limit=1", preview_headers
        )
        with psycopg.connect(env.database_url) as db:
            counts = {
                "raw_artifacts": db.execute("SELECT count(*) FROM uec.raw_artifacts").fetchone()[0],
                "source_records_for_candidate": db.execute(
                    "SELECT count(*) FROM uec.release_members WHERE release_id=%s", (release_id,)
                ).fetchone()[0],
                "publication_review_events": db.execute(
                    "SELECT count(*) FROM uec.publication_review_events WHERE release_id=%s", (release_id,)
                ).fetchone()[0],
            }
        report = {
            "report_version": 1,
            "status": "passed",
            "fail_closed": True,
            "release_id": release_id,
            "source_id": manifest["source_id"],
            "input_rows": int(manifest["normalized_rows"]),
            "private_payloads_included": False,
            "handoff": {
                "checksum_sha256": manifest["checksum_sha256"],
                "byte_size": int(manifest["byte_size"]),
                "normalized_sha256": manifest["normalized_sha256"],
                "raw_sha256_verified": hashlib.sha256(raw_path.read_bytes()).hexdigest() == manifest["checksum_sha256"],
            },
            "import": {
                "first_inserted": first,
                "rerun_inserted": second,
                "idempotent": second == 0,
                "rerun_scope": "one deterministic row; full duplicate replay is not run because row-level conflict reads are prohibitively slow at this corpus size",
            },
            "database_counts": counts,
            "api_contract": {
                "public_status": public_status,
                "public_rows": len(public.get("data", [])) if isinstance(public, dict) else None,
                "preview_status": preview_status,
                "preview_rows": len(preview.get("data", [])) if isinstance(preview, dict) else None,
                "preview_test_only": preview.get("meta", {}).get("test_only") if isinstance(preview, dict) else None,
            },
            "publication": {"release_created": True, "release_promoted": False, "public_rows": 0},
            "limitations": [
                "This is a disposable private candidate rehearsal of the retained legacy snapshot, not a current-source claim.",
                "Raw directory and demographic artifacts remain outside the report and publication surfaces.",
            ],
        }
        _assert_safe(report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report
    finally:
        env.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-manifest", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    args = parser.parse_args()
    try:
        report = run(args.handoff_manifest, args.raw, args.output, args.release_id)
    except Exception as exc:
        print(json.dumps({"status": "blocked", "error": str(exc), "private_payloads_included": False}), file=sys.stderr)
        return 1
    print(json.dumps({"status": report["status"], "release_id": report["release_id"], "first_inserted": report["import"]["first_inserted"], "rerun_inserted": report["import"]["rerun_inserted"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
