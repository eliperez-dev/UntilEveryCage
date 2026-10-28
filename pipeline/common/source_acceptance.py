"""Private spatial-source acceptance on the assigned V0-backed local database.

Uses the existing API binary and database, never creates a container, migrates,
publishes, or leaves a server running. Outputs aggregate evidence only.
"""
from __future__ import annotations

import hashlib
import importlib.util
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

SOURCE_ID = "eu.eea.intensive-livestock"
SOURCES = {SOURCE_ID: ("Livestock", "eea-acceptance.json"),
           "pl.giw.approved-food": (None, "poland-acceptance.json"),
           "no.fiskeridir.aquaculture": ("animal", "norway-acceptance.json")}
ROOT = Path(__file__).resolve().parents[2]
DATABASE = "uec_launch_sources_test_20261025"


def validate_target(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.path != "/" + DATABASE or set(urllib.parse.parse_qs(parsed.query)) & {"host", "hostaddr", "service", "servicefile"}):
        raise ValueError("Spatial acceptance requires the assigned mutable local V0 copy")


def release_input_check(ledger_path: Path, source_id: str) -> dict[str, Any]:
    """Exercise the actual release bridge without creating a release."""
    if source_id not in SOURCES:
        raise ValueError("Source has no assigned spatial acceptance contract")
    root = ledger_path.parent / "sources" / source_id
    path = root / "candidate-handoff/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    snapshot = {"source_artifact_sha256": manifest["checksum_sha256"],
                "normalized_sha256": manifest["normalized_sha256"],
                "retrieved_at": manifest["retrieved_at_utc"],
                "handoff_code_version": manifest["code_version"],
                "handoff_config_version": manifest["config_version"],
                "source_host": urllib.parse.urlsplit(manifest["source_url"]).hostname}
    spec = importlib.util.spec_from_file_location("spatial_release_bridge", ROOT / "pipeline/scripts/maintenance/bridge-v0-candidates.py")
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    handoff = bridge.verify_handoff({"source_id": source_id, "handoff_manifest_path": str(path.resolve())},
                                   {"snapshot": snapshot, "counts": {"imported_observation_count": manifest["normalized_rows"]}})
    kept = {"pl.giw.approved-food": ("source_section", "source_species_scope", "source_approval_details", "source_scope_eligibility"),
            "eu.eea.intensive-livestock": ("source_reporting_year", "source_activity", "source_activity_details",
                                          "source_facility_count", "source_installation_count"),
            "no.fiskeridir.aquaculture": ("source_species_scope", "source_locality_status", "source_capacity",
                                          "source_production_form", "source_production_purpose", "source_water_environment")}[source_id]
    for _, row in handoff["rows"]:
        normalized = row["normalized"]
        safe = bridge._safe_normalized(normalized, source_id, row.get("source_values"))
        if not safe.get("facility_display_name") or any(safe.get(k) != normalized.get(k) for k in kept):
            raise ValueError("Release projection lost source name or activity facts")
    result = {"source_id": source_id, "status": "verified_without_release_creation",
              "observation_rows": len(handoff["rows"]), "candidate_groups": len(handoff["groups"]),
              "named_records": len(handoff["rows"]), "source_fields_preserved": list(kept),
              "graph_handoff_state": handoff["graph_handoff_state"]}
    atomic_json(ledger_path.parent / "release-input-check.json", result)
    return result


def check(ledger_path: Path, database_url: str, *, executable: Path | None = None,
          source_id: str = SOURCE_ID) -> dict[str, Any]:
    if source_id not in SOURCES:
        raise ValueError("Source has no assigned spatial acceptance contract")
    search_text, receipt_name = SOURCES[source_id]
    validate_target(database_url)
    contract = load_contract(ROOT / "pipeline/contracts/development-baseline.json")
    before = verify(database_url, contract)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    imported = ledger["preview_import"]
    if ledger.get("source_id") != source_id or imported.get("status") != "imported" or imported.get("idempotent_replay") is not True:
        raise ValueError("Spatial-source acceptance requires a completed idempotent source import")
    expected_count = imported["facility_candidate_count"]
    with psycopg.connect(database_url, options="-c default_transaction_read_only=on -c statement_timeout=60000") as db:
        snapshot = db.execute("SELECT snapshot_sha256 FROM real_preview.source_preview_runs WHERE run_id=%s AND source_id=%s",
                              (ledger["run_id"], source_id)).fetchone()
        if not snapshot:
            raise ValueError("Spatial-source imported run is absent from the assigned database")
        rows = db.execute("""SELECT candidate_id::text,source_group_key,country_code,latitude,longitude,display_name,category
            FROM real_preview.candidates WHERE source_id=%s AND snapshot_sha256=%s""", (source_id, snapshot[0])).fetchall()
        if len(rows) != expected_count or len({r[1] for r in rows}) != expected_count:
            raise ValueError("Spatial-source candidate counts or identities do not reconcile")
        expected = {r[0]: r for r in rows if r[3] is not None and r[4] is not None}
        categories = {"slaughter", "processing_and_preparation", "other_regulated_premises"} if source_id == "pl.giw.approved-food" else {"animal_keeping_and_production"}
        if len(expected) != imported["map_visible_count"] or any(not r[5] or r[6] not in categories for r in rows):
            raise ValueError("Spatial-source names, categories or map counts do not reconcile")
        samples = {}
        for row in rows:
            samples.setdefault(row[2], row[0])
        country_count = len(samples)
        detail_ids = list(samples.values())
        detail_ids.extend(r[0] for r in sorted(rows)[:10] if r[0] not in detail_ids)
        public = db.execute("SELECT count(*) FROM uec.release_members m JOIN uec.observations o USING(observation_id) JOIN uec.source_records s USING(source_record_id) WHERE s.source_id=%s", (source_id,)).fetchone()[0]
        if public:
            raise ValueError("Spatial-source candidates unexpectedly entered a public release")
        queued_geocode_targets = None
        if source_id == "pl.giw.approved-food":
            handoff = ledger_path.parent / "sources" / source_id / "candidate-handoff/normalized/records.jsonl"
            eligible = set()
            for line in handoff.read_text(encoding="utf-8").splitlines():
                normalized = json.loads(line)["normalized"]
                location = normalized.get("private_location_evidence", {})
                if normalized.get("source_scope_eligibility") == "eligible" and (location.get("address") or location.get("address_lines")):
                    eligible.add(normalized["establishment_id"])
            queued = db.execute("SELECT DISTINCT source_record_key FROM real_preview.geocode_targets WHERE source_id=%s AND snapshot_sha256=%s", (source_id, snapshot[0])).fetchall()
            if {row[0] for row in queued} != eligible:
                raise ValueError("Poland address queue does not match eligible source approvals")
            queued_geocode_targets = len(queued)
    executable = executable or ROOT / "target/debug" / ("uec-api.exe" if os.name == "nt" else "uec-api")
    if not executable.is_file():
        raise ValueError("Build the existing API binary before Spatial-source acceptance")
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
                raise ValueError("Owned Spatial-source acceptance API exited during startup")
            try:
                request("/health/ready")
                break
            except (urllib.error.URLError, OSError):
                if time.monotonic() > deadline:
                    raise ValueError("Owned Spatial-source acceptance API startup timed out") from None
                time.sleep(.2)
        try:
            request("/dev/real-preview/locations", authenticated=False)
            raise ValueError("Private Spatial-source API unexpectedly allowed unauthenticated access")
        except urllib.error.HTTPError as error:
            if error.code != 401:
                raise ValueError("Private Spatial-source API authentication failed") from None
        source_query = urllib.parse.urlencode({"source_id": source_id})
        listing = request("/dev/real-preview/locations?" + source_query + "&limit=100")
        if not listing.get("data") or any(r["source_id"] != source_id for r in listing["data"]):
            raise ValueError("Spatial-source private source listing failed")
        search = request("/dev/real-preview/locations?" + source_query + "&" + urllib.parse.urlencode({"q": search_text or rows[0][5], "limit": 1}))
        if not search.get("data"):
            raise ValueError("Spatial-source private source search failed")
        feed = request("/dev/real-preview/map/feed?" + source_query)
        features = feed.get("data", [])
        if len(features) != len(expected) or {f["key"] for f in features} != set(expected):
            raise ValueError("Spatial-source complete map-feed membership differs from the database")
        for f in features:
            row = expected[f["key"]]
            if (f["source_id"] != source_id or f["weight"] != 1 or f["category_key"] != row[6]
                    or abs(f["latitude"] - row[3]) > 1e-7 or abs(f["longitude"] - row[4]) > 1e-7):
                raise ValueError("Spatial-source served map geometry, category or weight changed")
        for candidate in detail_ids:
            detail = request("/dev/real-preview/locations/" + candidate)["data"]
            if detail.get("source_id") != source_id or detail.get("project_approval") is not False:
                raise ValueError("Spatial-source private facility detail failed")
        after = verify(database_url, contract)
        if before != after:
            raise ValueError("V0 baseline changed during Spatial-source acceptance")
        receipt = {"source_id": source_id, "run_id": ledger["run_id"], "status": "verified_private_import_geocoding_pending" if source_id == "pl.giw.approved-food" and not features else "verified_private_e2e",
                   "candidate_observations": len(rows), "mapped_candidates": len(features), "country_count": country_count,
                   "detail_country_samples": country_count, "detail_samples": len(detail_ids), "full_map_membership_checked": True,
                   "list_and_search_passed": True, "private_auth_passed": True, "idempotent_replay": True,
                   **({"queued_geocode_targets": queued_geocode_targets} if queued_geocode_targets is not None else {}),
                   "baseline": after, "public_source_rows": public, "owned_api_stopped": True,
                   "api_binary_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(), "deployment": "not_attempted"}
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
    atomic_json(ledger_path.parent / receipt_name, receipt)
    return receipt


def run(*, existing_runner_run_id: str | None = None, refresh_callback=None,
        source_id: str = SOURCE_ID) -> dict[str, Any]:
    """Shared strict command: refresh, identical replay, and real API acceptance."""
    if refresh_callback is None:
        from scripts.real_preview import refresh_source
        refresh_callback = refresh_source
    if source_id not in SOURCES:
        raise ValueError("Source has no assigned spatial acceptance contract")
    database_url = os.environ.get("UEC_DATABASE_URL", "")
    validate_target(database_url)
    verify(database_url, load_contract(ROOT / "pipeline/contracts/development-baseline.json"))
    if existing_runner_run_id:
        runs = Path(os.environ.get("UEC_REAL_PREVIEW_RUNS_ROOT", str(ROOT / "target/real-preview/runs")))
        ledger_path = runs / existing_runner_run_id / "source-preview-ledger.json"
    else:
        first = refresh_callback(source_id)
        ledger_path = Path(first["ledger"])
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    refresh_callback(source_id, ledger["source_run"]["run_id"])
    # Replay writes the same run ledger; it must not create another acquisition.
    result = check(ledger_path, database_url, source_id=source_id)
    result["release_input"] = release_input_check(ledger_path, source_id)
    atomic_json(ledger_path.parent / SOURCES[source_id][1], result)
    return result
