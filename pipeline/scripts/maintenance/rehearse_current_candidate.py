"""Rehearse the current private corpus through one disposable candidate release.

This runner deliberately imports only candidate-handoff records.  It never
promotes a release, writes a public release, or commits acquired payloads.  A
row-free JSON report records the validation and API invariants so CI and a
maintainer can distinguish a complete rehearsal from a partial one.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import psycopg


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RELEASE_ID = "candidate-current-reacquisition-20260916"
FORBIDDEN_REPORT_KEYS = {"source_values", "raw_fields", "raw_payload", "payload", "records"}
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class RehearsalError(RuntimeError):
    """A fail-closed validation or environment error."""


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RehearsalError(f"unable to load maintenance module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _find_artifact(root: Path, source_id: str, checksum: str, byte_size: int) -> Path:
    """Find exactly one ignored raw artifact by the recorded identity."""
    candidates = []
    for base in (root / "data" / "raw" / source_id, root / "data" / "staging" / "reacquisition" / source_id):
        if not base.exists():
            continue
        candidates.extend(p for p in base.rglob("*") if p.is_file() and p.suffix.lower() not in {".json", ".jsonl"})
    matches = []
    for candidate in candidates:
        digest, size = _sha256(candidate)
        if digest == checksum and size == int(byte_size):
            matches.append(candidate)
    if len(matches) != 1:
        detail = ", ".join(str(p.relative_to(root)) for p in matches) or "none"
        raise RehearsalError(
            f"raw artifact resolution failed closed for {source_id}: expected one "
            f"artifact with sha256={checksum} bytes={byte_size}; matches={detail}"
        )
    return matches[0]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RehearsalError(f"unable to read JSON manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RehearsalError(f"manifest is not an object: {path}")
    return value


def _request(base: str, path: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], Any]:
    request = urllib.request.Request(base + path, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            content_type = response.headers.get("content-type", "")
            if "text/csv" in content_type:
                body: Any = raw.decode("utf-8")
            else:
                body = json.loads(raw)
            return response.status, dict(response.headers.items()), body
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = raw.decode("utf-8", errors="replace")
        return exc.code, dict(exc.headers.items()), body
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RehearsalError(f"API request failed for {path}: {exc}") from exc


def _assert_report_safe(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_REPORT_KEYS.intersection(value)
        if forbidden:
            raise RehearsalError(f"report would contain restricted payload keys: {sorted(forbidden)}")
        for child in value.values():
            _assert_report_safe(child)
    elif isinstance(value, list):
        for child in value:
            _assert_report_safe(child)


def _counts(database_url: str, release_id: str) -> dict[str, int]:
    with psycopg.connect(database_url) as db:
        tables = (
            "raw_artifacts", "acquisition_runs", "acquisition_run_artifacts",
            "source_records", "facilities", "observations", "release_members",
            "publication_review_events",
        )
        values = {table: db.execute(f"SELECT count(*) FROM uec.{table}").fetchone()[0] for table in tables}
        values["release_members_for_candidate"] = db.execute(
            "SELECT count(*) FROM uec.release_members WHERE release_id=%s", (release_id,)
        ).fetchone()[0]
        values["source_records_for_candidate"] = db.execute(
            "SELECT count(*) FROM uec.source_records sr "
            "JOIN uec.observations o ON o.source_record_id=sr.source_record_id "
            "JOIN uec.release_members m ON m.observation_id=o.observation_id "
            "WHERE m.release_id=%s", (release_id,)
        ).fetchone()[0]
        return values


def _write_failure(path: Path, message: str) -> None:
    report = {
        "report_version": 1,
        "status": "blocked",
        "fail_closed": True,
        "blocker": message,
        "private_payloads_included": False,
    }
    _assert_report_safe(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(manifest_path: Path, root: Path, output: Path, release_id: str) -> dict[str, Any]:
    from pipeline.tests.e2e.fixture import E2EEnvironment

    manifest = _read_json(manifest_path)
    release_id = release_id or str(manifest.get("publication", {}).get("candidate_release") or DEFAULT_RELEASE_ID)
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise RehearsalError("aggregate manifest has no sources")

    validator = _load_module(ROOT / "pipeline/scripts/maintenance/rehearse_current_reacquisition.py", "current_reacquisition_validator")
    validation_output = root / "data" / "reports" / "current-reacquisition-rehearsal.json"
    validation = validator.build_report(manifest_path, root, validation_output)

    import_candidate = _load_module(ROOT / "pipeline/scripts/maintenance/import-candidate.py", "candidate_import")
    env = E2EEnvironment()
    env.test_release_id = release_id
    try:
        env.start()
        imported: list[dict[str, Any]] = []
        for entry in sources:
            if not isinstance(entry, dict):
                raise RehearsalError("aggregate manifest contains a non-object source entry")
            source_id = entry.get("source_id")
            handoff_value = entry.get("candidate_handoff_manifest")
            if not isinstance(source_id, str) or not isinstance(handoff_value, str):
                raise RehearsalError("source entry lacks source_id or candidate_handoff_manifest")
            handoff_path = root / handoff_value
            handoff = _read_json(handoff_path)
            if int(handoff.get("normalized_rows", -1)) == 0:
                imported.append({"source_id": source_id, "input_rows": int(entry.get("input_rows", -1)), "normalized_rows": 0, "quarantined_rows": int(entry.get("quarantined_rows", -1)), "imported_rows": 0, "rerun_rows": 0, "status": "quarantined-not-imported"})
                continue
            normalized = handoff_path.parent / "normalized" / "records.jsonl"
            if not normalized.exists():
                raise RehearsalError(f"normalized handoff is missing for {source_id}: {normalized}")
            raw = _find_artifact(root, source_id, str(handoff["checksum_sha256"]), int(handoff["byte_size"]))
            source_manifest, rows = import_candidate.load_inputs(handoff_path, normalized, raw)
            first = import_candidate.import_candidate(env.database_url, source_manifest, rows, release_id, False)
            second = import_candidate.import_candidate(env.database_url, source_manifest, rows, release_id, False)
            imported.append({"source_id": source_id, "input_rows": int(entry["input_rows"]), "normalized_rows": len(rows), "quarantined_rows": int(entry["quarantined_rows"]), "imported_rows": first, "rerun_rows": second, "status": "imported"})

        base = f"http://127.0.0.1:{env.api_port}"
        headers = {"X-UEC-Dev-Preview-Token": env.dev_preview_token}
        status, _, public_body = _request(base, "/api/v2/locations?profile=official&limit=1")
        if status != 200 or public_body.get("data") != []:
            raise RehearsalError("public API exposed candidate rows during private rehearsal")
        status, _, first_page = _request(base, "/api/dev/preview/test-release/locations?profile=official&limit=2", headers)
        if status != 200 or not isinstance(first_page.get("data"), list) or not first_page["data"]:
            raise RehearsalError("test-release list did not return candidate rows")
        if first_page.get("meta", {}).get("test_only") is not True:
            raise RehearsalError("test-release list lacked test-only metadata")
        forbidden = json.dumps(first_page)
        if "source_values" in forbidden or "raw_fields" in forbidden:
            raise RehearsalError("test-release list exposed raw source fields")
        first_id = first_page["data"][0]["facility_id"]
        status, _, detail = _request(base, f"/api/dev/preview/test-release/locations/{first_id}?profile=official", headers)
        if status != 200 or detail.get("data", {}).get("facility_id") != first_id:
            raise RehearsalError("test-release detail did not match list identity")
        status, _, facets = _request(base, "/api/dev/preview/test-release/discovery/facets?profile=official", headers)
        if status != 200 or not isinstance(facets.get("dimensions"), dict):
            raise RehearsalError("test-release facets unavailable")
        next_cursor = first_page.get("meta", {}).get("next_cursor")
        second_page = None
        if next_cursor:
            status, _, second_page = _request(base, f"/api/dev/preview/test-release/locations?profile=official&limit=2&cursor={next_cursor}", headers)
            if status != 200:
                raise RehearsalError("test-release cursor request failed")
            first_ids = {row["facility_id"] for row in first_page["data"]}
            second_ids = {row["facility_id"] for row in second_page.get("data", [])}
            if first_ids.intersection(second_ids):
                raise RehearsalError("test-release cursor returned overlapping facilities")
        status, _, csv_body = _request(base, "/api/dev/preview/test-release/locations.csv?profile=official", headers)
        if status != 400 or not isinstance(csv_body, dict) or csv_body.get("error", {}).get("code") != "export_too_large":
            raise RehearsalError("unbounded test export did not enforce the bounded limit")
        # The endpoint is intentionally bounded at 1,000 rows.  The current
        # corpus must therefore fail closed rather than emit an oversized
        # private export; smaller candidate releases are covered by the
        # focused candidate-import E2E test.
        bounded_export = status == 400 and csv_body.get("error", {}).get("code") == "export_too_large"

        with psycopg.connect(env.database_url) as db:
            restricted_record, restricted_facility = db.execute(
                "SELECT sr.source_record_id, m.facility_id FROM uec.source_records sr "
                "JOIN uec.observations o ON o.source_record_id=sr.source_record_id "
                "JOIN uec.release_members m ON m.observation_id=o.observation_id "
                "WHERE m.release_id=%s ORDER BY sr.source_record_id LIMIT 1", (release_id,)
            ).fetchone()
            db.execute("INSERT INTO uec.record_access_events(source_record_id,action,reason_category,policy_version,maintainer) VALUES (%s,'public_access_revoked','privacy','ethics-v1','authorized-sprint-runner')", (restricted_record,))
        status, _, after_suppression = _request(base, f"/api/dev/preview/test-release/locations/{restricted_facility}?profile=official", headers)
        suppression_detail_status = status
        status, _, after_list = _request(base, "/api/dev/preview/test-release/locations?profile=official&limit=2", headers)
        if status != 200:
            raise RehearsalError("test-release list failed after suppression")
        post_ids = {row["facility_id"] for row in after_list.get("data", [])}
        if suppression_detail_status == 200:
            raise RehearsalError("suppressed facility remained available in detail")
        if str(restricted_facility) in post_ids:
            raise RehearsalError("suppressed facility remained available in list")

        counts = _counts(env.database_url, release_id)
        report = {
            "report_version": 1,
            "status": "passed",
            "fail_closed": True,
            "release_id": release_id,
            "private_payloads_included": False,
            "source_validation": {"status": "passed", "sources": validation.get("sources"), "totals": validation.get("totals")},
            "sources": imported,
            "candidate_release": {"status": "candidate", "test_only": True, "public_rows": len(public_body.get("data", [])), "database_counts": counts},
            "api_contract": {
                "list": True,
                "detail": True,
                "facets": True,
                "cursor_pagination": next_cursor is None or second_page is not None,
                "bounded_export": bounded_export,
                "raw_fields_absent": True,
            },
            "suppression": {"record_restricted": True, "detail_status_after": suppression_detail_status, "list_checked": True, "restricted_facility_not_reintroduced": True},
            "limitations": ["CFIA parsed as legacy XLS but all 874 rows remain quarantined pending reviewed function-code mapping; no CFIA rows entered the candidate release."],
        }
        _assert_report_safe(report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report
    finally:
        env.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/manifests/current-reacquisition-2026-09-16.json")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "data/reports/current-candidate-rehearsal.json")
    parser.add_argument("--release-id", default=None)
    args = parser.parse_args()
    try:
        report = run(args.manifest, args.root, args.output, args.release_id)
        print(json.dumps({"output": str(args.output), "status": report["status"], "release_id": report["release_id"]}, sort_keys=True))
        return 0
    except Exception as exc:
        message = str(exc)
        _write_failure(args.output, message)
        print(json.dumps({"output": str(args.output), "status": "blocked", "blocker": message}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
