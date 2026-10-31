"""Reuse an attempted Polish address for identical, source-bound record targets.

No provider calls or new results. Copy only independently validated display
evidence, retaining its original geocode result and request provenance.
"""
from __future__ import annotations

import argparse
import json
import os

import psycopg

DATABASE = "uec_launch_sources_test_20261025"
SOURCE = "pl.giw.approved-food"

PLAN = """
WITH cohort AS MATERIALIZED (
 SELECT target.*,job.source_record_id,job.query,location.location_evidence,
        EXISTS(SELECT 1 FROM uec.geocode_request_reservations reservation
               WHERE reservation.job_id=job.job_id) AS requested
 FROM real_preview.geocode_targets target JOIN uec.geocode_jobs job USING(job_id)
 JOIN real_preview.candidates candidate USING(candidate_id,snapshot_sha256,source_id)
 JOIN real_preview.candidate_private_location_evidence location USING(candidate_id,snapshot_sha256,source_id)
 JOIN uec.source_records record ON record.source_record_id=job.source_record_id
   AND record.source_id=target.source_id
   AND record.source_record_key='real-preview:'||target.snapshot_sha256||':'||target.source_record_key
   AND record.raw_fields->>'snapshot_sha256'=target.snapshot_sha256
 JOIN real_preview.private_geocoding_source_profiles profile ON profile.source_id=target.source_id
   AND profile.profile_id='geoapify-pl-giw-approved-food' AND profile.enabled
   AND profile.country_code='PL' AND profile.provider_id='geoapify'
 WHERE target.source_id='pl.giw.approved-food' AND candidate.country_code='PL'
   AND candidate.default_map_scope AND location.location_evidence->>'country_code'='PL'
   AND job.provider_id='geoapify'
   AND target.snapshot_sha256=(SELECT snapshot_sha256 FROM real_preview.source_preview_runs
     WHERE source_id='pl.giw.approved-food' ORDER BY created_at DESC,run_id DESC LIMIT 1)
   AND EXISTS(SELECT 1 FROM uec.geocode_job_events event WHERE event.job_id=job.job_id
     AND event.event_type='queued' AND event.details->>'processing_mode'='private_geoapify_source_profile'
     AND event.details->>'profile_id'=profile.profile_id)
   AND NOT EXISTS(SELECT 1 FROM uec.public_access_restricted restricted
     WHERE restricted.source_record_id=job.source_record_id)
   AND NOT EXISTS(SELECT 1 FROM real_preview.geocode_targets other
     JOIN uec.geocode_jobs other_job ON other_job.job_id=other.job_id
     JOIN uec.public_access_restricted restricted ON restricted.source_record_id=other_job.source_record_id
     WHERE other.candidate_id=target.candidate_id)
   AND NOT EXISTS(SELECT 1 FROM real_preview.enrichment_state_events state
     WHERE state.candidate_id=target.candidate_id AND state.state_code='restricted')
), requested AS MATERIALIZED (
 SELECT DISTINCT ON(job_id) * FROM cohort WHERE requested
 ORDER BY job_id,created_at,candidate_id
), pending AS MATERIALIZED (
 SELECT own.* FROM cohort own WHERE NOT own.requested
   AND (SELECT event_type FROM uec.geocode_job_events event WHERE event.job_id=own.job_id
     ORDER BY occurred_at DESC,event_id DESC LIMIT 1)='queued'
), unique_parent AS MATERIALIZED (
 SELECT own.candidate_id,min(parent.job_id::text)::uuid AS parent_job
 FROM pending own JOIN requested parent ON parent.query=own.query
   AND parent.location_evidence=own.location_evidence
 GROUP BY own.candidate_id HAVING count(DISTINCT parent.job_id)=1
), planned AS MATERIALIZED (
 SELECT own.candidate_id,own.snapshot_sha256,own.source_id,own.source_record_key,
        own.job_id AS pending_job,parent.job_id AS parent_job,
        point.geocode_result_id,point.display_latitude,point.display_longitude,
        point.display_precision,point.display_geometry_source,point.coordinate_review_status,
        point.match_confidence,point.match_confidence_band
 FROM pending own JOIN unique_parent USING(candidate_id)
 JOIN requested parent ON parent.job_id=unique_parent.parent_job
 LEFT JOIN LATERAL (
   SELECT evidence.* FROM real_preview.geocode_display_evidence evidence
   JOIN uec.geocode_results result USING(geocode_result_id)
   WHERE evidence.candidate_id=parent.candidate_id AND result.source_record_id=parent.source_record_id
     AND result.provider_id='geoapify' AND result.query=parent.query AND result.status='accepted'
     AND result.match_method='geoapify_forward' AND result.result IS NOT NULL
     AND evidence.display_latitude=ST_Y(result.result::geometry)
     AND evidence.display_longitude=ST_X(result.result::geometry)
     AND NOT EXISTS(SELECT 1 FROM real_preview.geocode_display_evidence other
       WHERE other.candidate_id=parent.candidate_id
         AND (other.display_latitude,other.display_longitude)<>
             (evidence.display_latitude,evidence.display_longitude))
   ORDER BY evidence.created_at DESC,evidence.evidence_id DESC LIMIT 1
 ) point ON true
)
"""

APPLY = """, selected AS MATERIALIZED (
 SELECT * FROM planned WHERE pending_job=ANY(%s::uuid[])
), linked AS (
 INSERT INTO real_preview.geocode_targets(job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
 SELECT parent_job,candidate_id,snapshot_sha256,source_id,source_record_key FROM selected
 ON CONFLICT DO NOTHING RETURNING job_id,candidate_id
), bound AS MATERIALIZED (
 SELECT selected.* FROM selected WHERE EXISTS(SELECT 1 FROM linked
   WHERE linked.job_id=selected.parent_job AND linked.candidate_id=selected.candidate_id)
 OR EXISTS(SELECT 1 FROM real_preview.geocode_targets target
   WHERE target.job_id=selected.parent_job AND target.candidate_id=selected.candidate_id)
), points AS (
 INSERT INTO real_preview.geocode_display_evidence(candidate_id,geocode_result_id,
   display_latitude,display_longitude,display_precision,display_geometry_source,coordinate_review_status,
   match_confidence,match_confidence_band)
 SELECT candidate_id,geocode_result_id,display_latitude,display_longitude,
   display_precision,display_geometry_source,coordinate_review_status,match_confidence,match_confidence_band FROM bound
 WHERE geocode_result_id IS NOT NULL
 ON CONFLICT DO NOTHING RETURNING candidate_id
), closed AS (
 INSERT INTO uec.geocode_job_events(job_id,event_type,retryable,details)
 SELECT pending_job,'cancelled',false,jsonb_build_object(
   'processing_mode','shared_query_reconciliation','outbound_request_sent',false,
   'shared_requested_job_id',parent_job,'basis','identical_retained_source_location_evidence')
 FROM bound RETURNING job_id
)
SELECT (SELECT count(*) FROM linked),(SELECT count(*) FROM points),(SELECT count(*) FROM closed)
"""


def reconcile(connection, *, apply=False):
    if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
        raise ValueError("wrong_source_test_database")
    if not apply:
        rows = connection.execute(PLAN + "SELECT count(*),count(geocode_result_id) FROM planned").fetchone()
        return {"source_id": SOURCE, "mode": "preview", "shared_targets": rows[0],
                "targets_with_validated_point": rows[1], "provider_calls": 0}
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('poland-shared-query-reconciliation'))")
        locked = connection.execute(PLAN + """SELECT job.job_id FROM uec.geocode_jobs job
            JOIN planned ON planned.pending_job=job.job_id ORDER BY job.job_id
            FOR UPDATE OF job SKIP LOCKED""").fetchall()
        # A new statement rechecks request reservations and latest events after
        # acquiring the same job locks used by the provider worker.
        links, points, closed = connection.execute(PLAN + APPLY, ([row[0] for row in locked],)).fetchone()
    return {"source_id": SOURCE, "mode": "apply", "targets_linked": links,
            "display_evidence_added": points, "duplicate_jobs_closed": closed,
            "provider_calls": 0, "results_appended": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with psycopg.connect(os.environ["UEC_DATABASE_URL"],
                         application_name="uec-shared-query-reconciliation",
                         options="-c statement_timeout=30000") as connection:
        print(json.dumps(reconcile(connection, apply=args.apply), sort_keys=True))


if __name__ == "__main__":
    main()
