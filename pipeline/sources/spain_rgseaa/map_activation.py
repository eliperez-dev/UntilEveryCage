"""Consume verified AESAN locality events into the ordinary private map queue."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .location_enrichment import LOOKUP_METHOD_VERSION, LOOKUP_SOURCE_ID, registration_key_sha256

SOURCE_ID = "es.locations"
PROFILE_ID = "geoapify-es-aesan-rgseaa"
OFFICIAL_HOST = "rgsa-web-aesan.mscbs.es"
MAX_ACTIVATION_EVENTS = 24


def verified_address_query(address: str, municipality: str, province: str) -> str:
    """Keep the original address intact and add only independently verified locality context."""
    if not all(isinstance(value, str) and value.strip() for value in (address, municipality, province)):
        raise ValueError("verified_locality_query_incomplete")
    parts = [" ".join(value.split()) for value in (address, municipality, province)]
    parts.append("Spain")
    return ", ".join(parts)


def _official_url(value: Any, *, request: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("lookup_url_invalid")
    parsed = urlsplit(value)
    expected_paths = ({"/rgsa/procesaBusquedaServlet"} if request else
                      {"/rgsa/resultado_principal.jsp", "/rgsa/resultado_principal_excel.jsp"})
    if (parsed.scheme != "https" or parsed.hostname != OFFICIAL_HOST
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.path not in expected_paths):
        raise ValueError("lookup_url_out_of_scope")
    # Query strings and fragments are deliberately discarded: the provenance
    # keeps the official route, never an accidental search/session token.
    return urlunsplit(("https", OFFICIAL_HOST, parsed.path, "", ""))


def verified_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Validate one minimized successful source event; never accept raw addresses or names."""
    if event.get("event_type") != "official_locality_lookup" or event.get("outcome") != "matched":
        return None
    if (event.get("source_id") != SOURCE_ID
            or event.get("method_source_id") != LOOKUP_SOURCE_ID
            or event.get("method_version") != LOOKUP_METHOD_VERSION):
        raise ValueError("lookup_provenance_mismatch")
    key_hash = event.get("registration_key_sha256")
    if not isinstance(key_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", key_hash):
        raise ValueError("lookup_key_hash_invalid")
    source_record_key = event.get("source_record_key")
    if not isinstance(source_record_key, str) or not re.fullmatch(r"[0-9a-f]{64}", source_record_key):
        raise ValueError("source_record_identity_invalid")
    result = event.get("location_evidence_addition")
    if not isinstance(result, dict) or result.get("source_id") != LOOKUP_SOURCE_ID:
        raise ValueError("locality_evidence_invalid")
    if result.get("source_url") != event.get("source_url"):
        raise ValueError("locality_source_url_mismatch")
    if (result.get("match_method") != "exact_rgseaa_components_and_province"
            or result.get("precision") != "municipality"):
        raise ValueError("locality_match_method_invalid")
    municipality = result.get("municipality")
    province = result.get("province")
    if (not isinstance(municipality, str) or not municipality.strip() or len(municipality) > 160
            or not isinstance(province, str) or not province.strip() or len(province) > 120):
        raise ValueError("locality_values_invalid")
    retrieved_at = event.get("retrieved_at")
    try:
        timestamp = datetime.fromisoformat(str(retrieved_at).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("lookup_timestamp_invalid") from None
    if timestamp.utcoffset() is None:
        raise ValueError("lookup_timestamp_invalid")
    return {
        "source_record_key": source_record_key,
        "lookup_hash": key_hash,
        "lookup_source_id": LOOKUP_SOURCE_ID,
        "lookup_method_version": LOOKUP_METHOD_VERSION,
        "lookup_url": _official_url(event.get("source_url")),
        "lookup_request_url": _official_url(event.get("request_url"), request=True),
        "retrieved_at": timestamp,
        "municipality": municipality.strip(),
        "province": province.strip(),
    }


def load_verified_events(path: str | Path, *, limit: int = MAX_ACTIVATION_EVENTS) -> list[dict[str, Any]]:
    if not 1 <= limit <= MAX_ACTIVATION_EVENTS:
        raise ValueError(f"Spain locality activation limit must be 1..{MAX_ACTIVATION_EVENTS}")
    result = []
    seen: set[tuple[str, str]] = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError("lookup_event_json_invalid") from None
        if not isinstance(event, dict):
            raise ValueError("lookup_event_schema_invalid")
        clean = verified_event(event)
        if clean is None:
            continue
        identity = (clean["source_record_key"], clean["lookup_hash"])
        if identity in seen:
            continue
        seen.add(identity)
        clean["_event"] = event
        result.append(clean)
        if len(result) >= limit:
            break
    return result


def _event_digest(event: dict[str, Any], candidate_id: Any, snapshot: str) -> str:
    payload = {
        "candidate_id": str(candidate_id), "snapshot_sha256": snapshot.strip(),
        "lookup_hash": event["lookup_hash"], "lookup_url": event["lookup_url"],
        "lookup_request_url": event["lookup_request_url"],
        "source_record_key_hash": event["source_record_key"],
        "retrieved_at": event["retrieved_at"].isoformat(),
        "municipality": event["municipality"], "province": event["province"],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _read_candidates(connection: Any) -> dict[str, list[dict[str, Any]]]:
    rows = connection.execute("""
        WITH latest AS (
            SELECT snapshot_sha256 FROM real_preview.source_preview_runs
             WHERE source_id=%s ORDER BY created_at DESC,run_id DESC LIMIT 1
        )
        SELECT c.candidate_id,c.snapshot_sha256,c.source_group_key,observation.source_identifier,c.country_code,
               c.location_class,c.default_map_scope,c.facility_address,
               location.location_evidence->>'address',location.location_evidence->>'country_code',
               manifest.source_artifact_sha256,manifest.source_url,manifest.retrieved_at,
               artifact.artifact_id,
               NOT EXISTS (
                   SELECT 1 FROM real_preview.geocode_targets target
                   JOIN uec.geocode_jobs job USING(job_id)
                   JOIN uec.public_access_restricted restricted USING(source_record_id)
                   WHERE target.candidate_id=c.candidate_id
               ) AS restriction_clear
          FROM real_preview.candidates c
          JOIN latest USING(snapshot_sha256)
          JOIN real_preview.observations observation
            ON observation.preview_id=c.representative_observation_id
           AND observation.snapshot_sha256=c.snapshot_sha256
           AND observation.source_id=c.source_id
          JOIN real_preview.candidate_private_location_evidence location USING(candidate_id)
          JOIN real_preview.source_manifests manifest
            ON manifest.snapshot_sha256=c.snapshot_sha256 AND manifest.source_id=c.source_id
          JOIN uec.raw_artifacts artifact ON artifact.sha256=manifest.source_artifact_sha256
         WHERE c.source_id=%s AND c.country_code='ES'
    """, (SOURCE_ID, SOURCE_ID)).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key_hash = registration_key_sha256(str(row[2]))
        if key_hash is None:
            continue
        grouped.setdefault(key_hash, []).append({
            "candidate_id": row[0], "snapshot_sha256": str(row[1]).strip(),
            "source_group_key": str(row[2]), "source_record_key_hash": str(row[3]),
            "country_code": row[4], "location_class": row[5],
            "default_map_scope": row[6], "facility_address": row[7],
            "private_address": row[8], "evidence_country_code": row[9],
            "source_artifact_sha256": row[10], "source_url": row[11],
            "source_retrieved_at": row[12], "artifact_id": row[13],
            "restriction_clear": row[14],
        })
    return grouped


def activate(database_url: str, events_path: str | Path, *, limit: int = MAX_ACTIVATION_EVENTS,
             connect: Any = None) -> dict[str, int]:
    """Append locality proof and enqueue new standard-worker jobs, never call a provider."""
    if connect is None:
        import psycopg
        connect = psycopg.connect
    events = load_verified_events(events_path, limit=limit)
    counts = {"events_accepted": len(events), "candidates_matched": 0, "events_ambiguous": 0,
              "events_restricted": 0, "events_ineligible": 0, "evidence_appended": 0,
              "jobs_created": 0, "targets_created": 0, "provider_calls": 0}
    with connect(database_url) as connection, connection.transaction():
        database = connection.execute("SELECT current_database()").fetchone()[0]
        if database != "uec_launch_sources_test_20261025":
            raise RuntimeError("database_identity_invalid")
        profile = connection.execute("""
            SELECT 1 FROM real_preview.private_geocoding_source_profiles
             WHERE profile_id=%s AND source_id=%s AND country_code='ES' AND enabled
        """, (PROFILE_ID, SOURCE_ID)).fetchone()
        if profile is None:
            raise RuntimeError("spain_private_geocoding_profile_unavailable")
        candidates = _read_candidates(connection)
        for event in events:
            matches = candidates.get(event["lookup_hash"], [])
            matches = [row for row in matches
                       if row["source_record_key_hash"] == event["source_record_key"]]
            if len(matches) != 1:
                counts["events_ambiguous" if len(matches) > 1 else "events_ineligible"] += 1
                continue
            candidate = matches[0]
            if not candidate["restriction_clear"]:
                counts["events_restricted"] += 1
                continue
            if (candidate["country_code"] != "ES" or candidate["evidence_country_code"] != "ES"
                    or candidate["location_class"] != "unmapped_private_observation"
                    or candidate["default_map_scope"] is not True
                    or not candidate["source_artifact_sha256"] or not candidate["artifact_id"]):
                counts["events_ineligible"] += 1
                continue
            address = candidate["private_address"] or candidate["facility_address"]
            try:
                query = verified_address_query(address, event["municipality"], event["province"])
            except ValueError:
                counts["events_ineligible"] += 1
                continue
            event_sha = _event_digest(event, candidate["candidate_id"], candidate["snapshot_sha256"])
            inserted = connection.execute("""
                INSERT INTO real_preview.spain_verified_locality_evidence
                    (event_sha256,source_id,candidate_id,snapshot_sha256,lookup_hash,source_record_key_hash,
                     lookup_source_id,lookup_method_version,lookup_url,lookup_request_url,
                     retrieved_at,municipality,province)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (event_sha256) DO NOTHING
                RETURNING evidence_event_id
            """, (event_sha, SOURCE_ID, candidate["candidate_id"], candidate["snapshot_sha256"],
                  event["lookup_hash"], event["source_record_key"],
                  event["lookup_source_id"], event["lookup_method_version"],
                  event["lookup_url"], event["lookup_request_url"], event["retrieved_at"],
                  event["municipality"], event["province"])).fetchone()
            if inserted is None:
                # The original insert and its job/target are one transaction;
                # a duplicate event is therefore already fully activated.
                continue
            counts["evidence_appended"] += 1
            linkage_key = f"real-preview:spain-verified-locality:{candidate['snapshot_sha256']}:{event_sha}"
            source_row = connection.execute("""
                INSERT INTO uec.source_records
                    (source_id,source_record_key,artifact_id,raw_fields,parsed_at)
                VALUES (%s,%s,%s,%s::jsonb,%s)
                ON CONFLICT (source_id,source_record_key,artifact_id) DO NOTHING
                RETURNING source_record_id
            """, (SOURCE_ID, linkage_key, candidate["artifact_id"], json.dumps({
                    "projection": "real_preview_spain_verified_locality_geocode_target",
                    "snapshot_sha256": candidate["snapshot_sha256"],
                    "lookup_evidence_event_sha256": event_sha,
                }, sort_keys=True), event["retrieved_at"])).fetchone()
            if source_row is None:
                source_row = connection.execute("""
                    SELECT source_record_id FROM uec.source_records
                     WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s
                """, (SOURCE_ID, linkage_key, candidate["artifact_id"])).fetchone()
            if source_row is None:
                raise RuntimeError("spain_geocode_source_record_missing")
            source_record_id = source_row[0]
            restricted = connection.execute("""
                SELECT 1 FROM uec.public_access_restricted WHERE source_record_id=%s
            """, (source_record_id,)).fetchone()
            if restricted is not None:
                raise RuntimeError("spain_geocode_target_restricted_after_validation")
            job = connection.execute("""
                INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                VALUES (%s,'geoapify',%s)
                ON CONFLICT (source_record_id,provider_id,query) DO NOTHING
                RETURNING job_id
            """, (source_record_id, query)).fetchone()
            job_created = job is not None
            if job is None:
                job = connection.execute("""
                    SELECT job_id FROM uec.geocode_jobs
                     WHERE source_record_id=%s AND provider_id='geoapify' AND query=%s
                """, (source_record_id, query)).fetchone()
            job_id = job[0]
            counts["jobs_created"] += int(job_created)
            target = connection.execute("""
                INSERT INTO real_preview.geocode_targets
                    (job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING RETURNING candidate_id
            """, (job_id, candidate["candidate_id"], candidate["snapshot_sha256"],
                  SOURCE_ID, candidate["source_group_key"])).fetchone()
            counts["targets_created"] += int(target is not None)
            connection.execute("""
                INSERT INTO uec.geocode_job_events(job_id,event_type,attempt_number,retryable,details)
                SELECT %s,'queued',1,false,%s::jsonb
                WHERE NOT EXISTS (SELECT 1 FROM uec.geocode_job_events WHERE job_id=%s)
            """, (job_id, json.dumps({
                    "processing_mode": "private_geoapify_source_profile",
                    "profile_id": PROFILE_ID,
                    "provider_configuration": PROFILE_ID,
                    "source_artifact_sha256": candidate["source_artifact_sha256"],
                    "lookup_evidence_event_sha256": event_sha,
                    "query_role": "source_industrial_address_with_verified_municipality",
                }, sort_keys=True), job_id))
            connection.execute("""
                INSERT INTO real_preview.enrichment_state_events
                    (candidate_id,snapshot_sha256,source_id,source_record_key,state_code,reason_code)
                VALUES (%s,%s,%s,%s,'queued','spain_verified_locality_address_profile')
            """, (candidate["candidate_id"], candidate["snapshot_sha256"], SOURCE_ID,
                  candidate["source_group_key"]))
            counts["candidates_matched"] += 1
    return counts
