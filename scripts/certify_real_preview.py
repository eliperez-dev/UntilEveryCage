#!/usr/bin/env python3
"""Certify one exact source run through the guarded local real-preview path.

The command verifies existing lifecycle evidence; it never acquires source data.
Its JSON output is row-free and is not publication or recurring-health approval.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class CertificationError(RuntimeError):
    pass


def _integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CertificationError(f"invalid or missing {name}")
    return value


def _hash(value: Any, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", value):
        raise CertificationError(f"invalid or missing {name}")
    return value.lower()


def validate_ledger(ledger: dict[str, Any], source_id: str) -> dict[str, Any]:
    """Validate exact run identity and safe row-free lifecycle aggregates."""
    if ledger.get("status") != "imported" or ledger.get("source_id") != source_id:
        raise CertificationError("runtime ledger is not an imported run for the requested source")
    run_id = ledger.get("run_id")
    if not isinstance(run_id, str) or not run_id or len(run_id) > 200:
        raise CertificationError("runtime ledger has no valid acquisition run id")
    source_run = ledger.get("source_run")
    if not isinstance(source_run, dict) or not isinstance(source_run.get("run_id"), str):
        raise CertificationError("runner manifest identity is missing")
    source_results = source_run.get("results")
    source_result = next((item for item in source_results or []
                          if isinstance(item, dict) and item.get("source_id") == source_id), None)
    source_summary = source_result.get("summary") if isinstance(source_result, dict) else None
    if not isinstance(source_summary, dict):
        raise CertificationError("source lifecycle summary is missing")
    if not isinstance(ledger.get("acquisition"), dict) or not ledger["acquisition"]:
        raise CertificationError("acquisition provenance is missing")
    imported = ledger.get("preview_import")
    if not isinstance(imported, dict) or imported.get("status") != "imported":
        raise CertificationError("preview import evidence is missing")
    if imported.get("idempotent") is not True:
        raise CertificationError("preview import did not verify idempotent replay")
    if _integer(ledger.get("public_rows"), "ledger public row count") != 0:
        raise CertificationError("runtime ledger reports public rows")
    if _integer(imported.get("public_release_count"), "public release count") != 0:
        raise CertificationError("runtime import reports public release rows")
    if _integer(imported.get("public_projection_count"), "public projection count") != 0:
        raise CertificationError("runtime import reports public projection rows")

    counts = {
        "observations": _integer(imported.get("observation_count"), "observation count"),
        "candidates": _integer(imported.get("facility_candidate_count"), "candidate count"),
        "numeric_coordinates": _integer(imported.get("numeric_coordinate_count"), "numeric coordinate count"),
        "city_postal": _integer(imported.get("city_postal_count"), "city/postal count"),
        "coarse_placeable": _integer(imported.get("coarse_placeable_facility_count", 0), "coarse placeable count"),
        "unmapped": _integer(imported.get("unmapped_map_candidate_count"), "unmapped candidate count"),
        "map_visible": _integer(ledger.get("map_visible_count"), "map-visible count"),
    }
    if counts["numeric_coordinates"] + counts["coarse_placeable"] != counts["map_visible"]:
        raise CertificationError("map-visible count does not reconcile with coordinate/coarse counts")
    if counts["numeric_coordinates"] + counts["city_postal"] + counts["unmapped"] != counts["candidates"]:
        raise CertificationError("candidate location classes do not reconcile")
    precision = ledger.get("coordinate_precision_breakdown")
    if not isinstance(precision, dict) or _integer(precision.get("exact"), "exact coordinate count") != 0:
        raise CertificationError("coordinate precision evidence is missing or claims exact points")

    quarantine = ledger.get("quarantine")
    if not isinstance(quarantine, dict):
        raise CertificationError("quarantine reconciliation is missing")
    input_count = _integer(quarantine.get("input_rows"), "input row count")
    quarantined = _integer(quarantine.get("quarantined_rows"), "quarantined row count")
    accepted = quarantine.get("accepted_rows", quarantine.get("candidate_observation_rows"))
    accepted_count = _integer(accepted, "accepted row count")
    out_of_scope = _integer(quarantine.get("out_of_scope_rows", 0), "out-of-scope row count")
    # Source adapters may count out-of-scope rows within either the accepted or
    # quarantined bucket; preserve that indicator without double-counting it.
    if input_count != accepted_count + quarantined:
        raise CertificationError("input rows do not reconcile to accepted plus quarantined")
    if accepted_count < counts["observations"]:
        raise CertificationError("imported observations exceed accepted source rows")

    acquisition_hashes: set[str] = set()
    def collect_hashes(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if ("sha256" in key.lower() or key.lower() in {"raw_hash", "raw_sha256"}) and isinstance(nested, str) and re.fullmatch(r"[a-fA-F0-9]{64}", nested):
                    acquisition_hashes.add(nested.lower())
                collect_hashes(nested)
        elif isinstance(value, list):
            for nested in value:
                collect_hashes(nested)
    collect_hashes(ledger["acquisition"])
    if not acquisition_hashes:
        raise CertificationError("acquisition provenance contains no source artifact hash")
    acquisition_run_ids: set[str] = set()
    def collect_run_ids(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key == "run_id" and isinstance(nested, str):
                    acquisition_run_ids.add(nested)
                collect_run_ids(nested)
        elif isinstance(value, list):
            for nested in value:
                collect_run_ids(nested)
    collect_run_ids(ledger["acquisition"])
    if run_id not in acquisition_run_ids:
        raise CertificationError("acquisition provenance is not bound to the selected run id")
    hashes = {
        "normalized_sha256": _hash(ledger.get("normalized_sha256") or imported.get("normalized_sha256"), "normalized hash"),
        "candidate_handoff_sha256": _hash(ledger.get("candidate_handoff_sha256"), "candidate handoff hash"),
        "schema_fingerprint": _hash(ledger.get("schema_fingerprint"), "schema fingerprint"),
    }
    if _hash(imported.get("normalized_sha256"), "imported normalized hash") != hashes["normalized_sha256"]:
        raise CertificationError("normalized artifact hash differs between lifecycle and import")
    if (_hash(source_summary.get("candidate_handoff_sha256"), "lifecycle candidate handoff hash")
            != hashes["candidate_handoff_sha256"]):
        raise CertificationError("candidate handoff hash differs between lifecycle and runtime ledger")
    if (_hash(source_summary.get("schema_fingerprint"), "lifecycle schema fingerprint")
            != hashes["schema_fingerprint"]):
        raise CertificationError("schema fingerprint differs between lifecycle and runtime ledger")
    return {"run_id": run_id, "runner_run_id": source_run["run_id"], "counts": counts,
            "hashes": hashes, "input_rows": input_count, "accepted_rows": accepted_count,
            "quarantined_rows": quarantined, "out_of_scope_rows": out_of_scope,
            "acquisition_hashes": sorted(acquisition_hashes)}


def _loopback_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.username or parsed.password:
        raise CertificationError("API endpoint must be an unauthenticated loopback HTTP URL")
    return value.rstrip("/")


def _api_json(url: str, token: str, *, timeout: float = 10.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={
        "X-Uec-Dev-Preview-Token": token,
        "Host": urlsplit(url).netloc,
        "Origin": f"http://{urlsplit(url).netloc}",
        "Cache-Control": "no-store",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200 or response.headers.get("Cache-Control", "").lower() != "no-store":
                raise CertificationError("private preview API did not return a no-store success")
            value = json.loads(response.read())
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        raise CertificationError("private preview API check failed") from None
    if not isinstance(value, dict):
        raise CertificationError("private preview API returned an invalid response")
    return value


def _check_api(base_url: str, token: str, source_id: str, evidence: dict[str, Any]) -> dict[str, bool]:
    counts = _api_json(f"{base_url}/dev/real-preview/counts", token)
    data = counts.get("data")
    meta = counts.get("meta")
    if not isinstance(data, dict) or not isinstance(meta, dict) or meta.get("private_preview") is not True:
        raise CertificationError("preview counts endpoint did not identify a private preview")
    ledger = meta.get("runtime_ledger")
    if not isinstance(ledger, list) or not any(
        isinstance(item, dict) and item.get("source_id") == source_id and item.get("run_id") == evidence["run_id"]
        for item in ledger
    ):
        raise CertificationError("served preview does not include the exact certified source run")
    if _integer(data.get("map_visible_count"), "API map-visible count") != evidence["counts"]["map_visible"]:
        raise CertificationError("API map-visible count differs from certified run evidence")
    list_url = f"{base_url}/dev/real-preview/locations?{urllib.parse.urlencode({'source_id': source_id, 'limit': 1})}"
    listing = _api_json(list_url, token)
    rows = listing.get("data")
    listing_meta = listing.get("meta")
    if not isinstance(listing_meta, dict) or listing_meta.get("private_preview") is not True:
        raise CertificationError("served source list is not marked private preview")
    if not isinstance(rows, list) or not rows:
        raise CertificationError("served source candidate list is empty or malformed")
    item = rows[0]
    if not isinstance(item, dict) or item.get("source_id") != source_id:
        raise CertificationError("served candidate is missing source/private labels")
    if item.get("project_approval") is not False or item.get("publication_status") != "not_published":
        raise CertificationError("served candidate does not explicitly disclaim approval/publication")
    candidate_id = item.get("candidate_id")
    if not isinstance(candidate_id, str):
        raise CertificationError("served candidate id is missing")
    detail = _api_json(f"{base_url}/dev/real-preview/locations/{urllib.parse.quote(candidate_id, safe='')}", token)
    detail_data = detail.get("data")
    if (not isinstance(detail_data, dict) or detail_data.get("source_id") != source_id
            or detail_data.get("project_approval") is not False
            or detail_data.get("publication_status") != "not_published"):
        raise CertificationError("candidate detail did not resolve from the selected source")
    map_ready = evidence["counts"]["map_visible"] > 0
    viewport_ready = False
    if evidence["counts"]["numeric_coordinates"] > 0:
        viewport_url = f"{base_url}/dev/real-preview/viewport?{urllib.parse.urlencode({'source_id': source_id, 'west': -180, 'south': -90, 'east': 180, 'north': 90, 'limit': 500})}"
        viewport = _api_json(viewport_url, token)
        viewport_meta = viewport.get("meta")
        viewport_data = viewport.get("data")
        if not isinstance(viewport_meta, dict) or viewport_meta.get("private_preview") is not True:
            raise CertificationError("served viewport is not marked private preview")
        viewport_ready = isinstance(viewport_data, list) and any(
            isinstance(candidate, dict) and candidate.get("source_id") == source_id for candidate in viewport_data)
        if not viewport_ready:
            raise CertificationError("map-visible source candidates were absent from the served viewport")
    return {"counts": True, "source_list": True, "candidate_detail": True,
            "map_visible_count_positive": map_ready, "viewport_has_source_candidate": viewport_ready}


def _db_check(database_url: str, source_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
    parsed = urlsplit(database_url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise CertificationError("certification database must be loopback")
    try:
        import psycopg
    except ImportError:
        raise CertificationError("psycopg is required for database certification") from None
    with psycopg.connect(database_url) as connection:
        found = connection.execute("""SELECT source_id, snapshot_sha256, source_artifact_sha256,
            normalized_sha256, input_count, accepted_count, quarantined_count, out_of_scope_count,
            imported_observation_count, facility_count, numeric_coordinate_count,
            coarse_placeable_count, unmapped_count, api_listable_count, map_visible_count,
            public_rows FROM real_preview.source_preview_runs WHERE run_id=%s""",
            (evidence["run_id"],)).fetchone()
        if not found:
            raise CertificationError("database has no row for the exact acquisition run")
        (db_source, snapshot, raw_hash, normalized, input_count, accepted, quarantined, out_of_scope,
         observations, candidates, numeric, coarse, unmapped, listable, visible, public_rows) = found
        expected = evidence["counts"]
        if db_source != source_id or normalized.strip() != evidence["hashes"]["normalized_sha256"]:
            raise CertificationError("database run identity or normalized hash does not match the ledger")
        if raw_hash.strip().lower() not in evidence["acquisition_hashes"]:
            raise CertificationError("database source artifact hash is absent from acquisition provenance")
        if (observations, candidates, numeric, coarse, unmapped, listable, visible) != (
            expected["observations"], expected["candidates"], expected["numeric_coordinates"],
            expected["coarse_placeable"], expected["unmapped"], expected["candidates"], expected["map_visible"]):
            raise CertificationError("database run counts differ from the runtime ledger")
        if (input_count != evidence["input_rows"] or accepted != evidence["accepted_rows"]
                or quarantined != evidence["quarantined_rows"] or out_of_scope != evidence["out_of_scope_rows"]):
            raise CertificationError("database quarantine counts differ from the runtime ledger")
        if public_rows != 0:
            raise CertificationError("database run is marked with public rows")
        bad_coordinates = connection.execute("""SELECT count(*) FROM real_preview.candidates
            WHERE snapshot_sha256=%s AND source_id=%s AND location_class='numeric_source_coordinate'
            AND NOT (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180
                     AND (latitude<>0 OR longitude<>0))""", (snapshot, source_id)).fetchone()[0]
        if bad_coordinates:
            raise CertificationError("database numeric candidate set contains invalid coordinates")
        for relation in ("uec.release_members", "uec.map_facilities_public_discovery",
                         "uec.map_facilities_public_discovery_read_model", "uec.graph_public_relationships",
                         "uec.graph_public_claims"):
            exists = connection.execute("SELECT to_regclass(%s)", (relation,)).fetchone()[0]
            if exists and connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]:
                raise CertificationError("database public projection is non-empty")
    return {"exact_run": True, "public_rows": 0, "valid_numeric_coordinates": True,
            "snapshot_sha256": snapshot, "source_artifact_sha256": raw_hash}


def certify(source_id: str, ledger_path: Path, database_url: str, api_url: str, token: str) -> dict[str, Any]:
    from pipeline.source_runtime_classification import RuntimeClassificationError, require_production_preview_source
    try:
        require_production_preview_source(source_id)
    except RuntimeClassificationError as error:
        raise CertificationError(str(error)) from None
    try:
        policy = json.loads((ROOT / "pipeline" / "preview-enabled-sources.json").read_text(encoding="utf-8"))
        source_policy = policy["sources"][source_id]
        terms_path = (ROOT / source_policy["terms_review"]).resolve()
        terms_path.relative_to(ROOT.resolve())
        terms = json.loads(terms_path.read_text(encoding="utf-8"))
    except (OSError, KeyError, TypeError, ValueError):
        raise CertificationError("source preview policy or terms review is unavailable") from None
    if (source_policy.get("enabled") is not True or source_policy.get("public_release") is not False
            or source_policy.get("terms_decision") != "approved" or terms.get("decision") != "approved"):
        raise CertificationError("source private-preview or terms boundary is not currently approved")
    if len(token) < 32:
        raise CertificationError("preview token must contain at least 32 characters")
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise CertificationError("runtime ledger could not be read") from None
    if not isinstance(ledger, dict):
        raise CertificationError("runtime ledger must be a JSON object")
    evidence = validate_ledger(ledger, source_id)
    try:
        database = _db_check(database_url, source_id, evidence)
    except CertificationError:
        raise
    except Exception:
        raise CertificationError("database verification failed") from None
    api = _check_api(_loopback_url(api_url), token, source_id, evidence)
    return {
        "schema_version": "strict-private-preview-certificate-v1",
        "status": "certified",
        "source_id": source_id,
        "run_id": evidence["run_id"],
        "runner_run_id": evidence["runner_run_id"],
        "certified_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "provenance_hashes": evidence["hashes"],
        "counts": {**evidence["counts"], "input_rows": evidence["input_rows"],
                   "accepted_rows": evidence["accepted_rows"], "quarantined_rows": evidence["quarantined_rows"],
                   "out_of_scope_rows": evidence["out_of_scope_rows"]},
        "checks": {"lifecycle_and_provenance": True, "database": database, "served_private_preview_api": api},
        "claims": {"private_preview_only": True, "publication_approval": False,
                   "recurring_health": False, "source_completeness": False,
                   "factual_accuracy": False, "privacy_clearance": False},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="one explicitly enabled production-e2e source id")
    parser.add_argument("--ledger", required=True, type=Path, help="exact source-preview-ledger.json from the completed run")
    parser.add_argument("--api-url", default="http://127.0.0.1:38001")
    parser.add_argument("--database-url-env", default="UEC_DATABASE_URL")
    parser.add_argument("--preview-token-env", default="UEC_DEV_PREVIEW_TOKEN")
    args = parser.parse_args(argv)
    try:
        database_url = os.environ.get(args.database_url_env)
        token = os.environ.get(args.preview_token_env)
        if not database_url or not token:
            raise CertificationError("database URL or in-memory preview token environment value is missing")
        result = certify(args.source, args.ledger, database_url, args.api_url, token)
        print(json.dumps(result, sort_keys=True))
        return 0
    except CertificationError as error:
        print(json.dumps({"status": "not_certified", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    except Exception:
        print(json.dumps({"status": "not_certified", "error": "certification failed without a safe result"}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
