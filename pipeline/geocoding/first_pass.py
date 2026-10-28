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

import psycopg

from .locationiq import LocationIqAdapter
from .private_profiles import profile_for_source

ROOT = Path(__file__).resolve().parents[2]
DATABASE = "uec_launch_sources_test_20261025"
SOURCES = (
    "fsa_approved_establishments", "fss_approved_establishments", "nz.locations",
    "es.cat.feed-sandach", "es.locations",
)


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


_CANDIDATES = """
WITH latest AS MATERIALIZED (
 SELECT DISTINCT ON(source_id) * FROM real_preview.source_preview_runs
 WHERE source_id=ANY(%s) ORDER BY source_id,created_at DESC,run_id DESC
), attempted AS MATERIALIZED (
 SELECT DISTINCT target.source_id,target.source_record_key
 FROM real_preview.geocode_targets target
 JOIN uec.geocode_request_reservations reservation USING(job_id)
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
    for query, in connection.execute("""SELECT DISTINCT job.query FROM uec.geocode_jobs job
            JOIN uec.geocode_request_reservations reservation USING(job_id)"""):
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
    attempted_rows = connection.execute("""WITH latest AS MATERIALIZED (
        SELECT DISTINCT ON(source_id) source_id,snapshot_sha256 FROM real_preview.source_preview_runs
        WHERE source_id=ANY(%s) ORDER BY source_id,created_at DESC,run_id DESC
      ), attempted AS MATERIALIZED (
        SELECT DISTINCT t.source_id,t.source_record_key FROM real_preview.geocode_targets t
        JOIN uec.geocode_request_reservations r USING(job_id)
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


def stage(connection, group):
    source, query = group["source"], group["query"]
    profile = profile_for_source(source, provider_id="locationiq")
    if not profile or profile.get("query_kind") != "source_address_first_pass":
        raise ValueError("source_first_pass_profile_unavailable")
    # One coordinator stages; short advisory lock prevents overlapping staging
    # runs from creating different jobs for the same physical address.
    connection.execute("SELECT pg_advisory_xact_lock(hashtext('country-first-pass-staging'))")
    usable = []
    for row in group["targets"]:
        candidate, snapshot, source, key, location, municipality, original, old_query, artifact, retrieved = row
        if connection.execute("""SELECT 1 FROM real_preview.geocode_targets t
            JOIN uec.geocode_request_reservations r USING(job_id)
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
        VALUES(%s,'locationiq',%s) ON CONFLICT(source_record_id,provider_id,query) DO NOTHING RETURNING job_id""",
        (record, query)).fetchone()
    if not job:
        job = connection.execute("SELECT job_id FROM uec.geocode_jobs WHERE source_record_id=%s AND provider_id='locationiq' AND query=%s", (record, query)).fetchone()
    job = job[0]
    if connection.execute("SELECT 1 FROM uec.geocode_request_reservations WHERE job_id=%s", (job,)).fetchone():
        return None
    for candidate, snapshot, key, _ in usable:
        connection.execute("""INSERT INTO real_preview.geocode_targets(job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", (job,candidate,snapshot,source,key))
    connection.execute("""INSERT INTO uec.geocode_job_events(job_id,event_type,attempt_number,retryable,details)
        SELECT %s,'queued',1,false,%s::jsonb WHERE NOT EXISTS(SELECT 1 FROM uec.geocode_job_events WHERE job_id=%s)""",
        (job,json.dumps({"processing_mode":"private_locationiq_source_profile", "profile_id":profile["profile_id"],
            "first_pass_only":True, "no_provider_retries":True}),job))
    return job, profile["profile_id"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", nargs="+", choices=SOURCES, default=list(SOURCES))
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--account", choices=("primary", "secondary"), default="primary")
    parser.add_argument("--partition", type=int, choices=(0,1,2,3), default=0)
    parser.add_argument("--partitions", type=int, choices=(1,2,4), default=1)
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()
    if not 1 <= args.limit <= 5000 or args.partition >= args.partitions:
        raise ValueError("invalid_first_pass_limits")
    url = os.environ["UEC_DATABASE_URL"]
    with psycopg.connect(url) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout='90s'")
        groups, counts = plan(connection, args.sources)
        usage = connection.execute("""SELECT reserved_requests FROM uec.geocode_account_budgets
            WHERE provider_id='locationiq' AND account_id=%s AND budget_date=(now() AT TIME ZONE 'UTC')::date""", (args.account,)).fetchone()
    summary = {source: {kind:value for (item,kind),value in counts.items() if item==source} for source in args.sources}
    remaining = max(0,5000-(usage[0] if usage else 0))
    # Stable hash partitions remain disjoint even as other workers finish jobs.
    import hashlib
    groups = [group for group in groups if int(hashlib.sha256((group["source"]+group["query"]).encode()).hexdigest(),16)%args.partitions == args.partition]
    groups.sort(key=lambda g:(SOURCES.index(g["source"]),g["query"]))
    groups = groups[:min(args.limit,remaining)]
    print(json.dumps({"stage":"first_pass_plan","sources":summary,"account":args.account,"selected_requests":len(groups),"remaining_account_ledger":remaining,"provider_calls":0}),flush=True)
    if not args.run or not groups:
        return
    spec=importlib.util.spec_from_file_location("first_pass_worker",ROOT/"pipeline/scripts/stages/geocode-worker.py")
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    observed = {}
    original_adapter = worker.get_adapter
    class Observed:
        def __init__(self,adapter):self.adapter=adapter
        def geocode(self,query):
            outcome=self.adapter.geocode(query);observed["acceptance"]=outcome.acceptance;return outcome
    worker.get_adapter=lambda *a,**kw:Observed(original_adapter(*a,**kw))
    processed=accepted=0
    for group in groups:
        with psycopg.connect(url) as connection:
            staged=stage(connection,group)
        if not staged:
            continue
        job,profile=staged
        observed.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            # Queue event 1 is not a request. Claim 2 is the first request;
            # max_attempts=2 forbids a subsequent claim, and retries=1 means
            # exactly one provider invocation within that claim.
            count=worker.run(url,"locationiq",1,0,1,daily_budget=5000,max_attempts=2,
                provider_interval=1.05,private_source_profile_id=profile,job_ids=(job,),
                provider_account=args.account,worker_id=f"country-first-pass-locationiq-{args.account}")
        if not count:
            break
        processed+=count
        accepted+=int(observed.get("acceptance")=="address_components_match")
        if processed%100==0:
            print(json.dumps({"stage":"first_pass_progress","account":args.account,"processed":processed,"accepted":accepted}),flush=True)
        if observed.get("acceptance") in {"authentication_rejected","provider_rate_limited"}:
            break
    print(json.dumps({"stage":"first_pass_finished","account":args.account,"processed":processed,"accepted":accepted,"local_only":True,"deployed":False}),flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"stage":"first_pass_blocked","error_type":type(error).__name__,"sqlstate":getattr(error,"sqlstate",None)}),flush=True)
        raise SystemExit(1)
