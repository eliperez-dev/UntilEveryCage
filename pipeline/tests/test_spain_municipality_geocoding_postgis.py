"""Rollback-only acceptance checks for the private Spain municipality bridge."""
from __future__ import annotations

import hashlib
import os
import unittest
import uuid

import psycopg
from psycopg.types.json import Jsonb


DATABASE_NAME = "uec_launch_sources_test_20261025"
PROFILE_ID = "geoapify-es-aesan-verified-municipality"
PROVIDER_VERSION = "spain-municipality-rollback-acceptance"


@unittest.skipUnless(
    os.environ.get("UEC_SPAIN_MUNICIPALITY_REAL_ACCEPTANCE") == "true"
    and os.environ.get("UEC_DATABASE_URL"),
    "set UEC_SPAIN_MUNICIPALITY_REAL_ACCEPTANCE=true and assigned UEC_DATABASE_URL",
)
class SpainMunicipalityGeocodingPostGISTests(unittest.TestCase):
    def test_bridge_acceptance_and_rejection_cases_rollback(self):
        connection = psycopg.connect(os.environ["UEC_DATABASE_URL"])
        try:
            self.assertEqual(connection.execute("SELECT current_database()").fetchone()[0], DATABASE_NAME)
            migration_count = connection.execute(
                "SELECT count(*) FROM uec.schema_migrations WHERE version='094_spain_verified_municipality_geocoding'"
            ).fetchone()[0]
            self.assertEqual(migration_count, 1)
            profile_count = connection.execute("""
                SELECT count(*) FROM real_preview.private_geocoding_source_profiles
                 WHERE profile_id=%s AND source_id='es.locations' AND country_code='ES' AND enabled
            """, (PROFILE_ID,)).fetchone()[0]
            self.assertEqual(profile_count, 1)

            selected = connection.execute("""
                SELECT job.source_record_id,job.query,target.candidate_id,target.snapshot_sha256,
                       evidence.municipality,evidence.province,evidence.source_record_key_hash
                  FROM uec.geocode_jobs job
                  JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
                  JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
                  JOIN real_preview.candidate_private_location_evidence location
                    ON location.candidate_id=candidate.candidate_id
                  JOIN real_preview.private_geocoding_source_profiles profile
                    ON profile.profile_id=%s AND profile.source_id=candidate.source_id AND profile.enabled
                  JOIN uec.geocode_job_events queued ON queued.job_id=job.job_id
                    AND queued.event_type='queued'
                    AND queued.details->>'processing_mode'='private_geoapify_source_profile'
                    AND queued.details->>'profile_id'=profile.profile_id
                  JOIN real_preview.spain_verified_locality_evidence evidence
                    ON evidence.evidence_event_id::text=queued.details->>'locality_evidence_event_id'
                   AND evidence.candidate_id=candidate.candidate_id
                   AND evidence.snapshot_sha256=candidate.snapshot_sha256
                   AND evidence.source_id=candidate.source_id
                 WHERE job.provider_id='geoapify' AND candidate.source_id='es.locations'
                   AND candidate.country_code='ES' AND location.location_evidence->>'country_code'='ES'
                   AND candidate.snapshot_sha256=(
                       SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                        WHERE run.source_id='es.locations'
                        ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1)
                   AND NOT EXISTS (
                       SELECT 1 FROM real_preview.spain_verified_locality_evidence newer
                        WHERE newer.candidate_id=evidence.candidate_id
                          AND newer.snapshot_sha256=evidence.snapshot_sha256
                          AND (newer.retrieved_at,newer.evidence_event_id)
                              > (evidence.retrieved_at,evidence.evidence_event_id))
                   AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                                   WHERE restricted.source_record_id=job.source_record_id)
                 ORDER BY job.created_at,job.job_id
                 LIMIT 1
            """, (PROFILE_ID,)).fetchone()
            self.assertIsNotNone(selected)
            source_record_id,query,candidate_id,snapshot,municipality,province,source_record_key_hash = selected

            bridge_function = connection.execute(
                "SELECT pg_get_functiondef('real_preview.capture_spain_verified_municipality_display()'::regprocedure)"
            ).fetchone()[0]
            self.assertIn("geoapify-es-aesan-verified-municipality", bridge_function)
            self.assertIn("queued.details->>'locality_evidence_event_id'=evidence.evidence_event_id::text",
                          bridge_function)
            self.assertIn("spain_verified_locality_evidence newer", bridge_function)

            def feature(*, city=municipality, county=province, country="ES", confidence=0.96, place_id="synthetic"):
                return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-3.7, 40.4]},
                        "properties": {"place_id": place_id, "result_type": "city", "country_code": country,
                                       "city": city, "county": county, "state": "Synthetic Autonomous Region",
                                       "rank": {"confidence": confidence}}}

            def insert_result(features, *, restrict=False, result_source_record_id=None,
                              result_query=None, result_candidate_id=None):
                result_source_record_id = result_source_record_id or source_record_id
                result_query = result_query or query
                result_candidate_id = result_candidate_id or candidate_id
                if restrict:
                    connection.execute("""
                        INSERT INTO uec.record_access_events
                            (source_record_id,action,reason_category,policy_version,maintainer,note,occurred_at)
                        VALUES (%s,'public_access_revoked','privacy','spain-municipality-rollback-test',
                                'rollback acceptance fixture',NULL,now()+interval '1 day')
                    """, (result_source_record_id,))
                response = {"type": "FeatureCollection", "features": features,
                            "_uec_selected_feature_index": 0}
                result_id = connection.execute("""
                    INSERT INTO uec.geocode_results
                        (source_record_id,provider_id,provider_version,query,provider_address_id,result,
                         precision,match_method,status,attempt_number,retryable,response,queried_at)
                    VALUES (%s,'geoapify',%s,%s,'rollback-municipality-fixture',
                            ST_GeogFromText('SRID=4326;POINT(-3.7 40.4)'), 'city','geoapify_forward',
                            'accepted',1,false,%s,now())
                    RETURNING geocode_result_id
                """, (result_source_record_id,PROVIDER_VERSION,result_query,Jsonb(response))).fetchone()[0]
                count = connection.execute("""
                    SELECT count(*) FROM real_preview.geocode_display_evidence
                     WHERE candidate_id=%s AND geocode_result_id=%s
                """, (result_candidate_id,result_id)).fetchone()[0]
                details = None
                if count:
                    details = connection.execute("""
                        SELECT display_precision,display_geometry_source,coordinate_review_status
                          FROM real_preview.geocode_display_evidence
                         WHERE candidate_id=%s AND geocode_result_id=%s
                    """, (result_candidate_id,result_id)).fetchone()
                return result_id,count,details

            def make_profile_probe(queue_profile_id, *, wrong_evidence_id=False):
                probe_group = f"rollback-spain-municipality-{uuid.uuid4()}"
                probe_candidate = connection.execute("""
                    INSERT INTO real_preview.candidates
                        (snapshot_sha256,source_id,source_group_key,representative_observation_id,
                         location_class,country_code,observation_count)
                    SELECT source.snapshot_sha256,source.source_id,%s,source.representative_observation_id,
                           'unmapped_private_observation','ES',1
                      FROM real_preview.candidates source WHERE source.candidate_id=%s
                    RETURNING candidate_id
                """, (probe_group,candidate_id)).fetchone()[0]
                connection.execute("""
                    INSERT INTO real_preview.candidate_private_location_evidence
                        (candidate_id,snapshot_sha256,source_id,location_evidence)
                    VALUES (%s,%s,'es.locations','{"country_code":"ES"}'::jsonb)
                """, (probe_candidate,snapshot))
                probe_record_key = f"rollback-spain-municipality-record-{uuid.uuid4()}"
                probe_source_record = connection.execute("""
                    INSERT INTO uec.source_records(source_id,source_record_key,artifact_id,raw_fields,parsed_at)
                    SELECT 'es.locations',%s,source.artifact_id,
                           '{"projection":"rollback_spain_municipality_bridge_test"}'::jsonb,now()
                      FROM uec.source_records source WHERE source.source_record_id=%s
                    RETURNING source_record_id
                """, (probe_record_key,source_record_id)).fetchone()[0]
                probe_event_hash = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
                probe_lookup_hash = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
                probe_source_key_hash = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
                probe_evidence = connection.execute("""
                    INSERT INTO real_preview.spain_verified_locality_evidence
                        (event_sha256,source_id,candidate_id,snapshot_sha256,lookup_hash,
                         source_record_key_hash,lookup_source_id,lookup_method_version,lookup_url,
                         lookup_request_url,retrieved_at,municipality,province)
                    VALUES (%s,'es.locations',%s,%s,%s,%s,
                            'es.locations.aesan-rgseaa-public-finder','es-aesan-rgseaa-locality-v1',
                            'https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal.jsp',
                            'https://rgsa-web-aesan.mscbs.es/rgsa/procesaBusquedaServlet',
                            now(),'Synthetic Municipality','Synthetic Province')
                    RETURNING evidence_event_id
                """, (probe_event_hash,probe_candidate,snapshot,probe_lookup_hash,probe_source_key_hash)).fetchone()[0]
                probe_query = "Synthetic Municipality, Synthetic Province, Spain"
                probe_job = connection.execute("""
                    INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                    VALUES (%s,'geoapify',%s) RETURNING job_id
                """, (probe_source_record,probe_query)).fetchone()[0]
                connection.execute("""
                    INSERT INTO real_preview.geocode_targets
                        (job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                    VALUES (%s,%s,%s,'es.locations',%s)
                """, (probe_job,probe_candidate,snapshot,probe_group))
                queued_evidence_id = uuid.uuid4() if wrong_evidence_id else probe_evidence
                connection.execute("""
                    INSERT INTO uec.geocode_job_events(job_id,event_type,attempt_number,retryable,details)
                    VALUES (%s,'queued',1,false,%s)
                """, (probe_job,Jsonb({
                        "processing_mode":"private_geoapify_source_profile",
                        "profile_id":queue_profile_id,
                        "locality_evidence_event_id":str(queued_evidence_id),
                    })))
                probe_feature = feature(city="Synthetic Municipality",county="Synthetic Province")
                return probe_source_record,probe_query,probe_candidate,probe_feature

            def run_case(label, features, expected, *, restrict=False, supersede=False):
                connection.execute("SAVEPOINT spain_municipality_case")
                if supersede:
                    event_digest = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
                    new_lookup_hash = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
                    connection.execute("""
                        INSERT INTO real_preview.spain_verified_locality_evidence
                            (event_sha256,source_id,candidate_id,snapshot_sha256,lookup_hash,
                             source_record_key_hash,lookup_source_id,lookup_method_version,lookup_url,
                             lookup_request_url,retrieved_at,municipality,province)
                        VALUES (%s,'es.locations',%s,%s,%s,%s,
                                'es.locations.aesan-rgseaa-public-finder','es-aesan-rgseaa-locality-v1',
                                'https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal.jsp',
                                'https://rgsa-web-aesan.mscbs.es/rgsa/procesaBusquedaServlet',
                                now()+interval '1 day','Synthetic Superseding Municipality',
                                'Synthetic Superseding Province')
                    """, (event_digest,candidate_id,snapshot,new_lookup_hash,source_record_key_hash))
                _,actual,details = insert_result(features,restrict=restrict)
                self.assertEqual(actual,expected,label)
                if expected:
                    self.assertEqual(details[0],"provider_locality_approximate",label)
                    self.assertIn("approximate municipality point, not facility coordinates",details[1])
                    self.assertEqual(details[2],"approximate_provider_locality_private_display",label)
                connection.execute("ROLLBACK TO SAVEPOINT spain_municipality_case")
                connection.execute("RELEASE SAVEPOINT spain_municipality_case")

            run_case("positive",[feature()],1)
            run_case("wrong_country",[feature(country="PT")],0)
            run_case("wrong_municipality",[feature(city=f"{municipality} synthetic mismatch")],0)
            run_case("wrong_province",[feature(county=f"{province} synthetic mismatch")],0)
            run_case("low_confidence",[feature(confidence=0.89)],0)
            run_case("ambiguous_viable_cities",[feature(place_id="synthetic-a"),feature(place_id="synthetic-b")],0)
            run_case("superseded_evidence",[feature()],0,supersede=True)
            run_case("restricted_source_record",[feature()],0,restrict=True)

            connection.execute("SAVEPOINT spain_municipality_case")
            wrong_profile = make_profile_probe("geoapify-es-aesan-rgseaa")
            _,actual,_ = insert_result([wrong_profile[3]],result_source_record_id=wrong_profile[0],
                                       result_query=wrong_profile[1],result_candidate_id=wrong_profile[2])
            self.assertEqual(actual,0,"wrong profile")
            connection.execute("ROLLBACK TO SAVEPOINT spain_municipality_case")
            connection.execute("RELEASE SAVEPOINT spain_municipality_case")

            connection.execute("SAVEPOINT spain_municipality_case")
            wrong_evidence = make_profile_probe(PROFILE_ID,wrong_evidence_id=True)
            _,actual,_ = insert_result([wrong_evidence[3]],result_source_record_id=wrong_evidence[0],
                                       result_query=wrong_evidence[1],result_candidate_id=wrong_evidence[2])
            self.assertEqual(actual,0,"wrong evidence ID")
            connection.execute("ROLLBACK TO SAVEPOINT spain_municipality_case")
            connection.execute("RELEASE SAVEPOINT spain_municipality_case")

            persisted = connection.execute(
                "SELECT count(*) FROM uec.geocode_results WHERE provider_version=%s",
                (PROVIDER_VERSION,),
            ).fetchone()[0]
            self.assertEqual(persisted,0)
        finally:
            connection.rollback()
            connection.close()


if __name__ == "__main__":
    unittest.main()
