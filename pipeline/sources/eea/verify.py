"""Private EEA acceptance on the assigned V0-backed local database.

Uses the existing API binary and database, never creates a container, migrates,
publishes, or leaves a server running. Outputs aggregate evidence only.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import psycopg

from pipeline.contracts.source_lifecycle import atomic_json
from pipeline.scripts.release_baseline import load_contract, verify
from .adapter import SOURCE_ID

ROOT = Path(__file__).resolve().parents[3]
DATABASE = "uec_launch_sources_test_20261025"


def validate_target(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.path != "/" + DATABASE or set(urllib.parse.parse_qs(parsed.query)) & {"host", "hostaddr", "service", "servicefile"}):
        raise ValueError("EEA acceptance requires the assigned mutable local V0 copy")


def check(ledger_path: Path, database_url: str, *, executable: Path | None = None) -> dict[str, Any]:
    validate_target(database_url)
    contract = load_contract(ROOT / "pipeline/contracts/development-baseline.json")
    before = verify(database_url, contract)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    imported = ledger["preview_import"]
    if ledger.get("source_id") != SOURCE_ID or imported.get("status") != "imported" or imported.get("idempotent_replay") is not True:
        raise ValueError("EEA acceptance requires a completed idempotent source import")
    expected_count = imported["facility_candidate_count"]
    with psycopg.connect(database_url, options="-c default_transaction_read_only=on -c statement_timeout=60000") as db:
        snapshot = db.execute("SELECT snapshot_sha256 FROM real_preview.source_preview_runs WHERE run_id=%s AND source_id=%s",
                              (ledger["run_id"], SOURCE_ID)).fetchone()
        if not snapshot:
            raise ValueError("EEA imported run is absent from the assigned database")
        rows = db.execute("""SELECT candidate_id::text,source_group_key,country_code,latitude,longitude,display_name,category
            FROM real_preview.candidates WHERE source_id=%s AND snapshot_sha256=%s""", (SOURCE_ID, snapshot[0])).fetchall()
        if len(rows) != expected_count or len({r[1] for r in rows}) != expected_count:
            raise ValueError("EEA candidate counts or identities do not reconcile")
        expected = {r[0]: r for r in rows if r[3] is not None and r[4] is not None}
        if len(expected) != imported["map_visible_count"] or any(not r[5] or r[6] != "animal_keeping_and_production" for r in rows):
            raise ValueError("EEA names, categories or map counts do not reconcile")
        samples = {}
        for row in rows:
            samples.setdefault(row[2], row[0])
        public = db.execute("SELECT count(*) FROM uec.release_members m JOIN uec.observations o USING(observation_id) JOIN uec.source_records s USING(source_record_id) WHERE s.source_id=%s", (SOURCE_ID,)).fetchone()[0]
        if public:
            raise ValueError("EEA candidates unexpectedly entered a public release")
    executable = executable or ROOT / "target/debug" / ("uec-api.exe" if os.name == "nt" else "uec-api")
    if not executable.is_file():
        raise ValueError("Build the existing API binary before EEA acceptance")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    token = secrets.token_urlsafe(32)
    env = {key: value for key, value in os.environ.items() if not key.startswith("UEC_") and key != "PORT"}
    env.update({"UEC_DATABASE_URL": database_url, "UEC_RUNTIME_MODE": "development", "UEC_BIND_HOST": "127.0.0.1",
                "UEC_DEV_PREVIEW": "true", "UEC_DEV_PREVIEW_TOKEN": token, "PORT": str(port),
                "UEC_CORS_ORIGIN": f"http://127.0.0.1:{port}"})
    server = subprocess.Popen([str(executable)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    base = f"http://127.0.0.1:{port}"
    def request(path, authenticated=True):
        headers = {"X-Uec-Dev-Preview-Token": token} if authenticated else {}
        with urllib.request.urlopen(urllib.request.Request(base + path, headers=headers), timeout=60) as response:
            return json.load(response)
    try:
        deadline = time.monotonic() + 30
        while True:
            if server.poll() is not None:
                raise ValueError("Owned EEA acceptance API exited during startup")
            try:
                request("/health/ready")
                break
            except (urllib.error.URLError, OSError):
                if time.monotonic() > deadline:
                    raise ValueError("Owned EEA acceptance API startup timed out") from None
                time.sleep(.2)
        try:
            request("/dev/real-preview/locations", authenticated=False)
            raise ValueError("Private EEA API unexpectedly allowed unauthenticated access")
        except urllib.error.HTTPError as error:
            if error.code != 401:
                raise ValueError("Private EEA API authentication failed") from None
        source_query = urllib.parse.urlencode({"source_id": SOURCE_ID})
        listing = request("/dev/real-preview/locations?" + source_query + "&limit=100")
        if not listing.get("data") or any(r["source_id"] != SOURCE_ID for r in listing["data"]):
            raise ValueError("EEA private source listing failed")
        search = request("/dev/real-preview/locations?" + source_query + "&q=Livestock&limit=1")
        if not search.get("data"):
            raise ValueError("EEA private source search failed")
        feed = request("/dev/real-preview/map/feed?" + source_query)
        features = feed.get("data", [])
        if len(features) != len(expected) or {f["key"] for f in features} != set(expected):
            raise ValueError("EEA complete map-feed membership differs from the database")
        for f in features:
            row = expected[f["key"]]
            if (f["source_id"] != SOURCE_ID or f["weight"] != 1 or f["category_key"] != row[6]
                    or abs(f["latitude"] - row[3]) > 1e-7 or abs(f["longitude"] - row[4]) > 1e-7):
                raise ValueError("EEA served map geometry, category or weight changed")
        for country, candidate in samples.items():
            detail = request("/dev/real-preview/locations/" + candidate)["data"]
            if detail.get("source_id") != SOURCE_ID or detail.get("project_approval") is not False:
                raise ValueError("EEA private facility detail failed")
        after = verify(database_url, contract)
        if before != after:
            raise ValueError("V0 baseline changed during EEA acceptance")
        receipt = {"source_id": SOURCE_ID, "run_id": ledger["run_id"], "status": "verified_private_e2e",
                   "candidate_observations": len(rows), "mapped_candidates": len(features), "country_count": len(samples),
                   "detail_country_samples": len(samples), "full_map_membership_checked": True,
                   "list_and_search_passed": True, "private_auth_passed": True, "idempotent_replay": True,
                   "baseline": after, "public_source_rows": public, "owned_api_stopped": True,
                   "api_binary_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(), "deployment": "not_attempted"}
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
    atomic_json(ledger_path.parent / "eea-acceptance.json", receipt)
    return receipt


def run(*, existing_runner_run_id: str | None = None, refresh_callback=None) -> dict[str, Any]:
    """Shared strict command: refresh, identical replay, and real API acceptance."""
    if refresh_callback is None:
        from scripts.real_preview import refresh_source
        refresh_callback = refresh_source
    database_url = os.environ.get("UEC_DATABASE_URL", "")
    validate_target(database_url)
    verify(database_url, load_contract(ROOT / "pipeline/contracts/development-baseline.json"))
    if existing_runner_run_id:
        runs = Path(os.environ.get("UEC_REAL_PREVIEW_RUNS_ROOT", str(ROOT / "target/real-preview/runs")))
        ledger_path = runs / existing_runner_run_id / "source-preview-ledger.json"
    else:
        first = refresh_callback(SOURCE_ID)
        ledger_path = Path(first["ledger"])
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    refresh_callback(SOURCE_ID, ledger["source_run"]["run_id"])
    # Replay writes the same run ledger; it must not create another acquisition.
    return check(ledger_path, database_url)
