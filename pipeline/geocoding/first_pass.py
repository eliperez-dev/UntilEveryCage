"""Country-scoped first-pass address work using the existing durable queue.

No provider retry, release writes, or credential discovery. One request may
cover multiple records at the same address; all source targets remain linked.
"""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import random
import math
import hashlib
import uuid

import psycopg

from .locationiq import LocationIqAdapter
from .private_profiles import profile_for_source

ROOT = Path(__file__).resolve().parents[2]
DATABASE = "uec_launch_sources_test_20261025"
SOURCES = (
    "fsa_approved_establishments", "fss_approved_establishments", "nz.locations",
    "es.cat.feed-sandach", "es.locations",
)

# Retrospectively imported research calls have real started events but never
# reserved a commercial account allowance. Queued-only jobs are not attempts.
ATTEMPTED_JOBS = """
 SELECT reservation.job_id FROM uec.geocode_request_reservations reservation
 WHERE NOT EXISTS(SELECT 1 FROM uec.geocode_job_events event
   WHERE event.job_id=reservation.job_id AND event.event_type='cancelled'
     AND event.details->>'processing_mode'='first_pass_pre_call_input_repair'
     AND event.details->>'no_provider_request_sent'='true')
 UNION
 SELECT event.job_id FROM uec.geocode_job_events event JOIN uec.geocode_jobs job USING(job_id)
 WHERE job.provider_id='cartociudad' AND event.event_type='started'
   AND event.details->>'processing_mode'='cartociudad_pilot_checkpoint_import'
   AND event.details->>'outbound_request_recorded'='true'
"""


def restore_spain_localities(connection, events_path):
    """Reattach retained official municipality evidence; no lookup or source rewrite."""
    from pipeline.sources.spain_rgseaa.reference_activation import (
        _candidate_index, _candidate_rejection, load_locality_events,
    )
    from pipeline.sources.spain_rgseaa.map_activation import _event_digest
    if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
        raise ValueError("wrong_source_test_database")
    events = load_locality_events(events_path)
    snapshot = connection.execute("""SELECT snapshot_sha256 FROM real_preview.source_preview_runs
        WHERE source_id='es.locations' ORDER BY created_at DESC,run_id DESC LIMIT 1""").fetchone()[0]
    candidates = _candidate_index(connection, str(snapshot).strip())
    parameters = []
    for event in events:
        matched = candidates.get((event["lookup_hash"],event["source_record_key"]),[])
        if len(matched) != 1 or _candidate_rejection(matched[0]):
            continue
        candidate = matched[0]
        parameters.append((_event_digest(event,candidate["candidate_id"],candidate["snapshot_sha256"]),
            candidate["candidate_id"],candidate["snapshot_sha256"],event["lookup_hash"],
            event["source_record_key"],event["lookup_source_id"],event["lookup_method_version"],
            event["lookup_url"],event["lookup_request_url"],event["retrieved_at"],event["municipality"],event["province"]))
    with connection.cursor() as cursor:
        cursor.executemany("""INSERT INTO real_preview.spain_verified_locality_evidence
            (event_sha256,source_id,candidate_id,snapshot_sha256,lookup_hash,source_record_key_hash,
             lookup_source_id,lookup_method_version,lookup_url,lookup_request_url,retrieved_at,municipality,province)
            VALUES(%s,'es.locations',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(event_sha256) DO NOTHING""", parameters)
        appended = cursor.rowcount
    return {"source":"es.locations","retained_events_validated":len(events),
            "source_bound_events":len(parameters),"locality_evidence_appended":appended,"provider_calls":0}


def normalize_query(query: str) -> str:
    return " ".join(query.lower().split())


def partition_groups(groups, partition, partitions):
    """Partition source identities before converting a query for its provider."""
    import hashlib
    if partitions not in (1, 2, 3, 4) or not 0 <= partition < partitions:
        raise ValueError("invalid_first_pass_partition")
    return [group for group in groups if int(hashlib.sha256(
        (group["source"]+group["query"]).encode()).hexdigest(),16)%partitions == partition]


def select_input_mode(groups, input_mode="standard", seed=None):
    """Defer complex inputs explicitly; do not relabel them as attempted."""
    if input_mode not in {"standard", "es_structured_numbered", "es_structured_complex", "es_other_numbered"}:
        raise ValueError("unknown_first_pass_input_mode")
    selected = list(groups)
    if input_mode.startswith("es_structured_"):
        from .spanish_addresses import input_kind, structured_components
        selected = [g for g in selected if g["source"] == "es.locations"
                    and json.loads(g["query"]).get("locality")
                    and ((input_mode == "es_structured_numbered"
                          and input_kind(json.loads(g["query"])["address"]) == "simple_numbered_road")
                         or (input_mode == "es_structured_complex"
                             and input_kind(json.loads(g["query"])["address"]) != "simple_numbered_road"
                             and structured_components(json.loads(g["query"])["address"]) is not None))]
    elif input_mode == "es_other_numbered":
        from .spanish_addresses import input_kind, structured_components, address_parts
        selected = [g for g in selected if g["source"] == "es.locations"
                    and json.loads(g["query"]).get("locality")
                    and input_kind(json.loads(g["query"])["address"]) == "other_numbered_address"
                    and structured_components(json.loads(g["query"])["address"]) is None
                    and any(int(re.match(r"[0-9]+", house)[0]) > 0
                            for _, house in address_parts(json.loads(g["query"])["address"]))]
    if seed is not None:
        random.Random(seed).shuffle(selected)
    return selected, len(groups)-len(selected)


def validate_provider_interval(provider, interval):
    minimum = .25 if provider == "geoapify" else .55
    if not math.isfinite(interval) or interval < minimum:
        raise ValueError("provider_interval_below_supported_rate")
    return interval


def defer_explicit_no_number(groups, *, include_no_number=False):
    from .spanish_addresses import input_kind
    if include_no_number:
        return list(groups), 0
    selected = [g for g in groups if g["source"] != "es.locations"
                or input_kind(json.loads(g["query"])["address"]) != "explicit_no_number"]
    return selected, len(groups)-len(selected)


def reopen_local_input_rejections(connection):
    """Correct attempt history only where the adapter demonstrably made no call."""
    if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
        raise ValueError("wrong_source_test_database")
    rows = connection.execute("""SELECT DISTINCT job.job_id,job.query,location.location_evidence,verified.municipality
        FROM uec.geocode_jobs job JOIN real_preview.geocode_targets target USING(job_id)
        JOIN real_preview.candidates candidate ON candidate.source_id=target.source_id
          AND candidate.source_group_key=target.source_record_key
        JOIN real_preview.candidate_private_location_evidence location ON location.candidate_id=candidate.candidate_id
          AND location.snapshot_sha256=candidate.snapshot_sha256 AND location.source_id=candidate.source_id
        JOIN LATERAL(SELECT municipality FROM real_preview.spain_verified_locality_evidence v
            WHERE v.candidate_id=candidate.candidate_id AND v.snapshot_sha256=candidate.snapshot_sha256
              AND v.source_id=candidate.source_id ORDER BY retrieved_at DESC,evidence_event_id DESC LIMIT 1)verified ON true
        WHERE job.provider_id='geoapify' AND target.source_id='es.locations'
          AND candidate.country_code='ES' AND candidate.default_map_scope
          AND candidate.snapshot_sha256=(SELECT snapshot_sha256 FROM real_preview.source_preview_runs
            WHERE source_id='es.locations' ORDER BY created_at DESC,run_id DESC LIMIT 1)
          AND (SELECT count(*) FROM uec.geocode_request_reservations r WHERE r.job_id=job.job_id)=1
          AND EXISTS(SELECT 1 FROM uec.geocode_results r WHERE r.source_record_id=job.source_record_id
            AND r.provider_id=job.provider_id AND r.query=job.query AND r.status='failed'
            AND r.match_method='geoapify_forward' AND r.response->>'error'='invalid_source_address')
          AND NOT EXISTS(SELECT 1 FROM uec.geocode_results r WHERE r.source_record_id=job.source_record_id
            AND r.provider_id=job.provider_id AND r.query=job.query AND
            (r.status<>'failed' OR r.match_method<>'geoapify_forward'
             OR r.response->>'error' IS DISTINCT FROM 'invalid_source_address'))
          AND NOT EXISTS(SELECT 1 FROM uec.public_access_restricted r WHERE r.source_record_id=job.source_record_id)
          AND NOT EXISTS(SELECT 1 FROM real_preview.enrichment_state_events state
            WHERE state.candidate_id=candidate.candidate_id AND state.state_code='restricted')""").fetchall()
    reopened = set()
    for job, old_query, location, municipality in rows:
        try:
            old = json.loads(old_query)
        except (TypeError, ValueError):
            continue
        if (not isinstance(old, dict) or old.get("schema_version") != "uec-address-query-v1"
                or old.get("country_code") != "ES" or old.get("locality")):
            continue
        query = structured_query("es.locations", location, municipality=municipality)
        if not query or query == old_query or not json.loads(query)["locality"]:
            continue
        digest = hashlib.sha256(query.encode()).hexdigest()
        event = uuid.uuid5(uuid.UUID("9d6a0228-1088-4d24-b9e9-8ad4c56f6649"), f"{job}:{digest}")
        inserted = connection.execute("""INSERT INTO uec.geocode_job_events(event_id,job_id,event_type,details)
            VALUES(%s,%s,'cancelled',%s::jsonb) ON CONFLICT DO NOTHING RETURNING event_id""",
            (event,job,json.dumps({"processing_mode":"first_pass_pre_call_input_repair",
                "no_provider_request_sent":True,"replacement_query_sha256":digest,
                "reason":"verified_town_recovered_after_local_input_rejection"}))).fetchone()
        if inserted:
            reopened.add(job)
    return {"reopened_pre_call_jobs":len(reopened),"provider_calls":0,"quota_reservations_modified":0}


def structured_query(source: str, location: dict, *, municipality: str = "") -> str | None:
    """Use source location fields, not establishment/contact names or guessed towns."""
    country = {SOURCES[0]: "GB", SOURCES[1]: "GB", SOURCES[2]: "NZ",
               SOURCES[3]: "ES", SOURCES[4]: "ES"}.get(source)
    if country is None or location.get("country_code") != country:
        return None
    address = location.get("address")
    if country == "GB":
        lines = location.get("address_lines")
        if not isinstance(lines, list) or any(not isinstance(line, str) for line in lines):
            return None
        address = ", ".join(line.strip() for line in lines if line.strip())
    if source == "nz.locations" and (
        type(location.get("location_count")) is not int or location["location_count"] != 1
        or str(location.get("number_of_locations", "")).strip() != "1"
    ):
        return None
    payload = {"schema_version": "uec-address-query-v1", "address": address,
               "locality": municipality if source == "es.locations" else location.get("city", ""),
               "postcode": location.get("postal_code", location.get("postcode")) or None,
               "region": location.get("region") or None, "country_code": country}
    query = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return query if LocationIqAdapter._parse_first_pass_query(query, country.lower()) else None


_CANDIDATES = f"""
WITH latest AS MATERIALIZED (
 SELECT DISTINCT ON(source_id) * FROM real_preview.source_preview_runs
 WHERE source_id=ANY(%s) ORDER BY source_id,created_at DESC,run_id DESC
), attempted AS MATERIALIZED (
 SELECT DISTINCT target.source_id,target.source_record_key
 FROM real_preview.geocode_targets target
 JOIN ({ATTEMPTED_JOBS}) reservation USING(job_id)
), restricted AS MATERIALIZED (
 SELECT DISTINCT candidate_id FROM real_preview.enrichment_state_events WHERE state_code='restricted'
 UNION SELECT DISTINCT target.candidate_id FROM real_preview.geocode_targets target
 JOIN uec.geocode_jobs job USING(job_id) JOIN uec.public_access_restricted restriction USING(source_record_id)
), original AS MATERIALIZED (
 SELECT DISTINCT ON(target.candidate_id,target.snapshot_sha256)
 target.candidate_id,target.snapshot_sha256,job.source_record_id,job.query
 FROM real_preview.geocode_targets target JOIN uec.geocode_jobs job USING(job_id)
 WHERE job.provider_id='geoapify' ORDER BY target.candidate_id,target.snapshot_sha256,job.created_at,job.job_id
), municipalities AS MATERIALIZED (
 SELECT DISTINCT ON(candidate_id,snapshot_sha256) candidate_id,snapshot_sha256,municipality
 FROM real_preview.spain_verified_locality_evidence ORDER BY candidate_id,snapshot_sha256,retrieved_at DESC,evidence_event_id DESC
)
SELECT candidate.candidate_id,candidate.snapshot_sha256,candidate.source_id,candidate.source_group_key,
 location.location_evidence,municipalities.municipality,original.source_record_id,original.query,
 artifact.artifact_id,latest.retrieved_at
FROM real_preview.candidates candidate JOIN latest USING(source_id,snapshot_sha256)
JOIN real_preview.candidate_private_location_evidence location USING(candidate_id,snapshot_sha256,source_id)
JOIN uec.sources source ON source.source_id=candidate.source_id AND source.country_code=candidate.country_code
JOIN uec.raw_artifacts artifact ON artifact.sha256=latest.source_artifact_sha256
JOIN real_preview.source_manifests manifest ON manifest.source_id=candidate.source_id AND manifest.snapshot_sha256=candidate.snapshot_sha256
LEFT JOIN attempted ON attempted.source_id=candidate.source_id AND attempted.source_record_key=candidate.source_group_key
LEFT JOIN restricted ON restricted.candidate_id=candidate.candidate_id
LEFT JOIN original ON original.candidate_id=candidate.candidate_id AND original.snapshot_sha256=candidate.snapshot_sha256
LEFT JOIN municipalities ON municipalities.candidate_id=candidate.candidate_id AND municipalities.snapshot_sha256=candidate.snapshot_sha256
WHERE candidate.default_map_scope AND candidate.latitude IS NULL AND candidate.longitude IS NULL
 AND attempted.source_record_key IS NULL AND restricted.candidate_id IS NULL
 AND manifest.source_artifact_sha256=latest.source_artifact_sha256
 AND manifest.normalized_sha256=latest.normalized_sha256
ORDER BY candidate.source_id,candidate.candidate_id
"""


def plan(connection, sources=SOURCES):
    """Read-only source-key exclusion across all providers and all snapshots."""
    if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
        raise ValueError("wrong_source_test_database")
    rows = connection.execute(_CANDIDATES, (list(sources),)).fetchall()
    # Skip earlier physical requests, including a duplicate address under a
    # different source record. No retry is introduced by query reformatting.
    requested = set()
    for query, in connection.execute(f"""SELECT DISTINCT job.query FROM uec.geocode_jobs job
            JOIN ({ATTEMPTED_JOBS}) reservation USING(job_id)"""):
        requested.add(normalize_query(query))
        if query.lstrip().startswith("{"):
            try:
                country = json.loads(query)["country_code"].lower()
                parsed = LocationIqAdapter._parse_first_pass_query(query, country)
                if parsed:
                    requested.add(normalize_query(parsed[-1]))
            except (KeyError, TypeError, json.JSONDecodeError):
                pass
    # A legacy Spain query omitted the town. Do not equate that incomplete
    # query with a different unattempted facility in another town. Reconstruct
    # physical-address identities from retained current source context instead.
    attempted_rows = connection.execute(f"""WITH latest AS MATERIALIZED (
        SELECT DISTINCT ON(source_id) source_id,snapshot_sha256 FROM real_preview.source_preview_runs
        WHERE source_id=ANY(%s) ORDER BY source_id,created_at DESC,run_id DESC
      ), attempted AS MATERIALIZED (
        SELECT DISTINCT t.source_id,t.source_record_key FROM real_preview.geocode_targets t
        JOIN ({ATTEMPTED_JOBS}) r USING(job_id)
      ), towns AS MATERIALIZED (
        SELECT DISTINCT ON(candidate_id,snapshot_sha256) candidate_id,snapshot_sha256,municipality
        FROM real_preview.spain_verified_locality_evidence ORDER BY candidate_id,snapshot_sha256,retrieved_at DESC,evidence_event_id DESC
      )
      SELECT c.source_id,e.location_evidence,towns.municipality
      FROM real_preview.candidates c JOIN latest USING(source_id,snapshot_sha256)
      JOIN attempted a ON a.source_id=c.source_id AND a.source_record_key=c.source_group_key
      JOIN real_preview.candidate_private_location_evidence e ON e.candidate_id=c.candidate_id AND e.snapshot_sha256=c.snapshot_sha256 AND e.source_id=c.source_id
      LEFT JOIN towns ON towns.candidate_id=c.candidate_id AND towns.snapshot_sha256=c.snapshot_sha256
      WHERE c.default_map_scope AND c.latitude IS NULL""", (list(sources),)).fetchall()
    for source, location, municipality in attempted_rows:
        query = structured_query(source, location, municipality=municipality or "")
        if query:
            country = json.loads(query)["country_code"].lower()
            requested.add(normalize_query(LocationIqAdapter._parse_first_pass_query(query,country)[-1]))
    groups = {}
    counts = Counter()
    for row in rows:
        candidate, snapshot, source, key, location, municipality, original, old_query, artifact, retrieved = row
        query = structured_query(source, location, municipality=municipality or "")
        if query is None:
            counts[(source, "unusable_input")] += 1
            continue
        country = json.loads(query)["country_code"].lower()
        provider_query = LocationIqAdapter._parse_first_pass_query(query, country)[-1]
        identity = normalize_query(provider_query)
        if identity in requested or (old_query and not (source=="es.locations" and municipality)
                                    and normalize_query(old_query) in requested):
            counts[(source, "address_already_attempted")] += 1
            continue
        counts[(source, "eligible_records")] += 1
        # Keep source/country boundaries even when two sources share an address.
        groups.setdefault((source, identity), {"source": source, "query": query, "targets": []})["targets"].append(row)
    for source, _ in groups:
        counts[(source, "new_requests")] += 1
    return list(groups.values()), counts


def provider_query(group, provider):
    """Keep LocationIQ's structured input or use the existing Spanish Geoapify profile."""
    if provider == "locationiq":
        return group["query"]
    if provider != "geoapify" or group["source"] != "es.locations":
        raise ValueError("first_pass_provider_source_not_supported")
    parsed = LocationIqAdapter._parse_first_pass_query(group["query"], "es")
    if parsed is None or not parsed[1]:
        raise ValueError("invalid_first_pass_source_query")
    # Preserve source components for independent Python/SQL validation. Only
    # the adapter formats the text sent to the provider.
    return group["query"]


def stage(connection, group, provider="locationiq"):
    source, query = group["source"], group["query"]
    profile = profile_for_source(source, provider_id=provider)
    if not profile or (provider == "locationiq" and profile.get("query_kind") != "source_address_first_pass"):
        raise ValueError("source_first_pass_profile_unavailable")
    query = provider_query(group, provider)
    # One coordinator stages; short advisory lock prevents overlapping staging
    # runs from creating different jobs for the same physical address.
    connection.execute("SELECT pg_advisory_xact_lock(hashtext('country-first-pass-staging'))")
    usable = []
    for row in group["targets"]:
        candidate, snapshot, source, key, location, municipality, original, old_query, artifact, retrieved = row
        if connection.execute(f"""SELECT 1 FROM real_preview.geocode_targets t
            JOIN ({ATTEMPTED_JOBS}) r USING(job_id)
            WHERE t.source_id=%s AND t.source_record_key=%s LIMIT 1""", (source, key)).fetchone():
            continue
        if original is None:
            projection = f"real-preview:{snapshot}:{key}"
            raw = {"projection": "real_preview_private_geocode_target", "snapshot_sha256": snapshot}
            connection.execute("""INSERT INTO uec.source_records(source_id,source_record_key,artifact_id,raw_fields,parsed_at)
                VALUES(%s,%s,%s,%s::jsonb,%s) ON CONFLICT(source_id,source_record_key,artifact_id) DO NOTHING""",
                (source, projection, artifact, json.dumps(raw), retrieved))
            original = connection.execute("""SELECT source_record_id FROM uec.source_records
                WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s AND raw_fields=%s::jsonb""",
                (source, projection, artifact, json.dumps(raw))).fetchone()
            if not original:
                raise ValueError("source_record_binding_mismatch")
            original = original[0]
        if connection.execute("SELECT 1 FROM uec.public_access_restricted WHERE source_record_id=%s", (original,)).fetchone():
            continue
        usable.append((candidate, snapshot, key, original))
    if not usable:
        return None
    record = usable[0][3]
    job = connection.execute("""INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
        VALUES(%s,%s,%s) ON CONFLICT(source_record_id,provider_id,query) DO NOTHING RETURNING job_id""",
        (record, provider, query)).fetchone()
    if not job:
        job = connection.execute("SELECT job_id FROM uec.geocode_jobs WHERE source_record_id=%s AND provider_id=%s AND query=%s", (record, provider, query)).fetchone()
    job = job[0]
    if connection.execute("SELECT 1 FROM uec.geocode_request_reservations WHERE job_id=%s", (job,)).fetchone():
        return None
    current = connection.execute("""SELECT event_type,attempt_number FROM uec.geocode_job_events
        WHERE job_id=%s ORDER BY occurred_at DESC,event_id DESC LIMIT 1""", (job,)).fetchone()
    if current is not None and current != ("queued",1):
        return None
    for candidate, snapshot, key, _ in usable:
        connection.execute("""INSERT INTO real_preview.geocode_targets(job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", (job,candidate,snapshot,source,key))
    connection.execute("""INSERT INTO uec.geocode_job_events(job_id,event_type,attempt_number,retryable,details)
        SELECT %s,'queued',1,false,%s::jsonb WHERE NOT EXISTS(SELECT 1 FROM uec.geocode_job_events
            WHERE job_id=%s AND event_type='queued' AND details->>'first_pass_only'='true')""",
        (job,json.dumps({"processing_mode":f"private_{provider}_source_profile", "profile_id":profile["profile_id"],
            "first_pass_only":True, "no_provider_retries":True}),job))
    return job, profile["profile_id"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", nargs="+", choices=SOURCES)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--provider", choices=("locationiq", "geoapify"), default="locationiq")
    parser.add_argument("--account", choices=("primary", "secondary"))
    parser.add_argument("--partition", type=int, choices=(0,1,2,3), default=0)
    parser.add_argument("--partitions", type=int, choices=(1,2,3,4), default=1)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--input-mode", choices=("standard", "es_structured_numbered", "es_structured_complex", "es_other_numbered"), default="standard")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--worker-id")
    parser.add_argument("--provider-interval", type=float, default=1.05)
    parser.add_argument("--include-no-number", action="store_true")
    args = parser.parse_args()
    validate_provider_interval(args.provider, args.provider_interval)
    if not 1 <= args.limit <= 5000 or args.partition >= args.partitions:
        raise ValueError("invalid_first_pass_limits")
    args.sources = args.sources or (["es.locations"] if args.provider == "geoapify" else list(SOURCES))
    if args.provider == "geoapify" and (args.account is not None or args.sources != ["es.locations"]):
        raise ValueError("geoapify_first_pass_requires_spain_and_no_named_account")
    if args.input_mode.startswith("es_structured_") and (args.provider != "geoapify" or args.sources != ["es.locations"]):
        raise ValueError("structured_numbered_mode_requires_geoapify_spain")
    if args.input_mode == "es_other_numbered" and args.sources != ["es.locations"]:
        raise ValueError("other_numbered_mode_requires_spain")
    args.account = (args.account or "primary") if args.provider == "locationiq" else None
    daily_budget = 5000 if args.provider == "locationiq" else 3000
    url = os.environ["UEC_DATABASE_URL"]
    repair = {"reopened_pre_call_jobs": 0}
    if args.run and "es.locations" in args.sources:
        with psycopg.connect(url) as connection:
            repair = reopen_local_input_rejections(connection)
    with psycopg.connect(url) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout='90s'")
        groups, counts = plan(connection, args.sources)
        if args.provider == "locationiq":
            usage = connection.execute("""SELECT reserved_requests FROM uec.geocode_account_budgets
                WHERE provider_id='locationiq' AND account_id=%s AND budget_date=(now() AT TIME ZONE 'UTC')::date""", (args.account,)).fetchone()
        else:
            usage = connection.execute("""SELECT reserved_requests FROM uec.geocode_provider_budgets
                WHERE provider_id='geoapify' AND budget_date=(now() AT TIME ZONE 'UTC')::date""").fetchone()
    summary = {source: {kind:value for (item,kind),value in counts.items() if item==source} for source in args.sources}
    remaining = max(0,daily_budget-(usage[0] if usage else 0))
    # Stable hash partitions remain disjoint even as other workers finish jobs.
    groups = partition_groups(groups,args.partition,args.partitions)
    groups, deferred_no_number = defer_explicit_no_number(groups, include_no_number=args.include_no_number)
    blocked_context = 0
    if args.provider == "geoapify":
        # The Spanish exact-address bridge needs a source-bound town. Keep
        # these addresses in the inventory, but do not reserve a request the
        # adapter would reject locally before reaching the provider.
        blocked_context = sum(not json.loads(group["query"])["locality"].strip() for group in groups)
        groups = [group for group in groups if json.loads(group["query"])["locality"].strip()]
    groups.sort(key=lambda g:(SOURCES.index(g["source"]),g["query"]))
    groups, deferred_formats = select_input_mode(groups, args.input_mode, args.seed)
    groups = groups[:min(args.limit,remaining)]
    print(json.dumps({"stage":"first_pass_plan","sources":summary,"provider":args.provider,"account":args.account,"selected_requests":len(groups),"provider_input_blocked_requests":blocked_context,"deferred_no_street_number":deferred_no_number,"deferred_input_formats":deferred_formats,"input_mode":args.input_mode,"reopened_pre_call_jobs":repair["reopened_pre_call_jobs"],"remaining_account_ledger":remaining,"provider_calls":0}),flush=True)
    if not args.run or not groups:
        return
    spec=importlib.util.spec_from_file_location("first_pass_worker",ROOT/"pipeline/scripts/stages/geocode-worker.py")
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    observed = {}
    original_adapter = worker.get_adapter
    class Observed:
        def __init__(self,adapter):self.adapter=adapter
        def geocode(self,query):
            outcome=self.adapter.geocode(query)
            observed["acceptance"]=outcome.acceptance
            observed["error"]=outcome.response.get("error") if isinstance(outcome.response,dict) else None
            return outcome
    def configured_adapter(*args_, **kwargs):
        adapter = original_adapter(*args_, **kwargs)
        if args.input_mode.startswith("es_structured_"):
            adapter.spanish_structured_search = True
        return Observed(adapter)
    worker.get_adapter = configured_adapter
    processed=accepted=0
    for group in groups:
        with psycopg.connect(url) as connection:
            staged=stage(connection,group,args.provider)
        if not staged:
            continue
        job,profile=staged
        observed.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            # Queue event 1 is not a request. Claim 2 is the first request;
            # max_attempts=2 forbids a subsequent claim, and retries=1 means
            # exactly one provider invocation within that claim.
            count=worker.run(url,args.provider,1,0,1,daily_budget=daily_budget,max_attempts=2,
                provider_interval=args.provider_interval,private_source_profile_id=profile,job_ids=(job,),
                provider_account=args.account,worker_id=args.worker_id or f"country-first-pass-{args.provider}-{args.account or 'default'}")
        if not count:
            break
        processed+=count
        accepted+=int(observed.get("acceptance") in {"address_components_match","high_confidence_address_match"})
        if processed%100==0:
            print(json.dumps({"stage":"first_pass_progress","provider":args.provider,"account":args.account,"processed":processed,"accepted":accepted}),flush=True)
        if (observed.get("acceptance") in {"authentication_rejected","provider_rate_limited"}
                or observed.get("error") in {"authentication_rejected","provider_rate_limited"}):
            break
    print(json.dumps({"stage":"first_pass_finished","provider":args.provider,"account":args.account,"input_mode":args.input_mode,"processed":processed,"accepted":accepted,"local_only":True,"deployed":False}),flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"stage":"first_pass_blocked","error_type":type(error).__name__,"sqlstate":getattr(error,"sqlstate",None)}),flush=True)
        raise SystemExit(1)
