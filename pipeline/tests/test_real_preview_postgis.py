"""Disposable PostGIS integration for the isolated preview migration."""

import json
import importlib.util
import io
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

import psycopg
from pipeline.geocoding.base import GeocodeOutcome
from pipeline.taxonomy.persistence import persist_preview_candidate_assignment_set
from pipeline.taxonomy_crosswalk import crosswalk_document, persistence_assignments, project_observation

MIGRATIONS = sorted((Path(__file__).parents[1] / "migrations").glob("*.sql"))
DATABASE_URL = os.environ.get("UEC_REAL_PREVIEW_TEST_DATABASE_URL")
WORKER_SPEC = importlib.util.spec_from_file_location(
    "preview_geocode_worker", Path(__file__).parents[1] / "scripts/stages/geocode-worker.py"
)
WORKER = importlib.util.module_from_spec(WORKER_SPEC)
WORKER_SPEC.loader.exec_module(WORKER)


@unittest.skipUnless(DATABASE_URL, "requires a dedicated disposable PostGIS test database")
class RealPreviewPostgisTests(unittest.TestCase):
    def test_private_rows_are_idempotent_and_stay_out_of_public_release_membership(self):
        with psycopg.connect(DATABASE_URL) as connection:
            database_name = connection.execute("SELECT current_database()").fetchone()[0]
            if not database_name.startswith("uec_real_preview_test"):
                self.fail("integration database must use the dedicated uec_real_preview_test prefix")
            extensions = connection.execute("SELECT extname FROM pg_extension WHERE extname='postgis'").fetchall()
            self.assertEqual(len(extensions), 1, "dedicated integration database must have PostGIS")
            with connection.transaction():
                for migration in MIGRATIONS:
                    connection.execute(migration.read_text(encoding="utf-8"))
                connection.execute("INSERT INTO real_preview.imports(snapshot_sha256,observation_count) VALUES (%s,4)", ("a" * 64,))
                row = ("a" * 64, "it.853-2004", "synthetic-source-key", "numeric_source_coordinate", True,
                       "IT", "Example", None, 44.1, 11.2, "numeric")
                insert = """INSERT INTO real_preview.observations
                    (snapshot_sha256,source_id,source_identifier,location_class,facility_candidate,country_code,city,postal_code,latitude,longitude,coordinate_precision)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING"""
                numeric_observation_id = connection.execute(insert + " RETURNING preview_id", row).fetchone()[0]
                connection.execute(insert, row)
                coarse_observation_id = connection.execute(insert + " RETURNING preview_id", ("a" * 64, "fr.dgal.section-i", "synthetic-coarse-key", "city_postal", True,
                    "FR", "Example", None, None, None, "city")).fetchone()[0]
                unmapped_observation_id = connection.execute(insert + " RETURNING preview_id", ("a" * 64, "us.fsis", "synthetic-private-key", "unmapped_private_observation", True,
                    "US", None, None, None, None, None)).fetchone()[0]
                candidate_insert = """INSERT INTO real_preview.candidates
                    (snapshot_sha256,source_id,source_group_key,representative_observation_id,location_class,country_code,city,latitude,longitude,observation_count,
                     display_name,activity_label,activity_source,evidence_summary,source_record_url,source_name,observed_at,default_map_scope,map_scope_reason)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING"""
                numeric_candidate = ("a" * 64, "it.853-2004", "source-group-1", numeric_observation_id, "numeric_source_coordinate", "IT", "Example", 44.1, 11.2,
                    "Synthetic Facility", "Meat processing", "source", "Synthetic evidence summary", "https://example.test/record", "Synthetic source", "2026-09-20T12:00:00Z", True, None)
                connection.execute(candidate_insert, numeric_candidate)
                connection.execute(candidate_insert, numeric_candidate)
                activity_insert = """INSERT INTO real_preview.candidates
                    (snapshot_sha256,source_id,source_group_key,representative_observation_id,location_class,country_code,city,latitude,longitude,observation_count,
                     display_name,activity_label,activity_source,evidence_summary,source_record_url,source_name,observed_at,default_map_scope,map_scope_reason,
                     category,activity_categories,source_activity_codes,source_activity_labels,activity_mapping_status,classification_ruleset_version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
                activity_candidate = (numeric_candidate[0], numeric_candidate[1], "source-group-activity",
                    numeric_observation_id, *numeric_candidate[4:],
                    "slaughter", ["slaughter", "fish_processing"], ["EB.10.10.99", "EB.03.21.00"],
                    ["Slaughterhouse", "Fish plant"], "mapped", "denmark-classification-v1")
                connection.execute(activity_insert, activity_candidate)
                activity_row = connection.execute("""
                    SELECT category,activity_categories,source_activity_codes,source_activity_labels,
                           activity_mapping_status,classification_ruleset_version
                    FROM real_preview.candidates WHERE source_group_key='source-group-activity'
                """).fetchone()
                self.assertEqual(activity_row, (
                    "slaughter", ["slaughter", "fish_processing"], ["EB.10.10.99", "EB.03.21.00"],
                    ["Slaughterhouse", "Fish plant"], "mapped", "denmark-classification-v1"))
                taxonomy_candidate_id = connection.execute(
                    "SELECT candidate_id FROM real_preview.candidates WHERE source_group_key='source-group-1'"
                ).fetchone()[0]
                projection = project_observation({"source_id": "it.853-2004"})
                taxonomy_document = crosswalk_document("it.853-2004")
                taxonomy_rows = persistence_assignments(projection)
                taxonomy_set_id = persist_preview_candidate_assignment_set(
                    connection, candidate_id=str(taxonomy_candidate_id),
                    representative_observation_id=str(numeric_observation_id), snapshot_sha256="a" * 64,
                    source_id="it.853-2004", document=taxonomy_document, assignment_rows=taxonomy_rows,
                )
                replayed_set_id = persist_preview_candidate_assignment_set(
                    connection, candidate_id=str(taxonomy_candidate_id),
                    representative_observation_id=str(numeric_observation_id), snapshot_sha256="a" * 64,
                    source_id="it.853-2004", document=taxonomy_document, assignment_rows=taxonomy_rows,
                )
                self.assertEqual(taxonomy_set_id, replayed_set_id)
                lineage = connection.execute(
                    "SELECT source_identifier,display_category,primary_key,mapping_status FROM real_preview.candidate_taxonomy_assignments_lineage WHERE candidate_id=%s",
                    (taxonomy_candidate_id,),
                ).fetchone()
                self.assertEqual(lineage, ("synthetic-source-key", "unclassified", "unclassified", "unclassified"))
                connection.execute(candidate_insert, ("a" * 64, "fr.dgal.section-i", "source-group-2", coarse_observation_id, "city_postal", "FR", "Example", None, None,
                    None, None, None, None, None, None, None, True, None))
                connection.execute(candidate_insert, ("a" * 64, "us.fsis", "source-group-3", unmapped_observation_id, "unmapped_private_observation", "US", None, None, None,
                    None, None, None, None, None, None, None, False, "general-food"))
                missing_artifact_observation_id = connection.execute(insert + " RETURNING preview_id", ("a" * 64, "au.npi.facilities", "synthetic-au-key", "unmapped_private_observation", True,
                    "AU", None, None, None, None, None)).fetchone()[0]
                connection.execute(candidate_insert, ("a" * 64, "au.npi.facilities", "source-group-au", missing_artifact_observation_id,
                    "unmapped_private_observation", "AU", None, None, None, None, None, None, None, None, None, None, False, "no-display-location"))
                coarse_candidate_id = connection.execute(
                    "SELECT candidate_id FROM real_preview.candidates WHERE source_group_key='source-group-2'"
                ).fetchone()[0]
                fsis_candidate_id = connection.execute(
                    "SELECT candidate_id FROM real_preview.candidates WHERE source_group_key='source-group-3'"
                ).fetchone()[0]
                missing_artifact_candidate_id = connection.execute(
                    "SELECT candidate_id FROM real_preview.candidates WHERE source_group_key='source-group-au'"
                ).fetchone()[0]
                france_projection = project_observation({
                    "source_id": "fr.dgal.section-i",
                    "normalized": {"source_category": "SH CP"},
                })
                self.assertEqual(france_projection["taxonomy_mapping_status"], "mapped")
                self.assertEqual(set(france_projection["taxonomy_primaries"]), {"slaughter", "processing_and_preparation"})
                persist_preview_candidate_assignment_set(
                    connection, candidate_id=str(coarse_candidate_id),
                    representative_observation_id=str(coarse_observation_id), snapshot_sha256="a" * 64,
                    source_id="fr.dgal.section-i", document=crosswalk_document("fr.dgal.section-i"),
                    assignment_rows=persistence_assignments(france_projection),
                )
                fsis_projection = project_observation({
                    "source_id": "us.fsis",
                    "normalized": {"source_category": "UNKNOWN-SOURCE-CODE"},
                })
                self.assertEqual(fsis_projection["taxonomy_mapping_status"], "unmapped")
                persist_preview_candidate_assignment_set(
                    connection, candidate_id=str(fsis_candidate_id),
                    representative_observation_id=str(unmapped_observation_id), snapshot_sha256="a" * 64,
                    source_id="us.fsis", document=crosswalk_document("us.fsis"),
                    assignment_rows=persistence_assignments(fsis_projection),
                )
                france_lineage = connection.execute("""
                    SELECT source_identifier,display_category,count(*)::int,
                           count(DISTINCT primary_key)::int,bool_and(source_code_reference IS NOT NULL)
                    FROM real_preview.candidate_taxonomy_assignments_lineage
                    WHERE candidate_id=%s GROUP BY source_identifier,display_category
                """, (coarse_candidate_id,)).fetchone()
                self.assertEqual(france_lineage, ("synthetic-coarse-key", "slaughter", 2, 2, True))
                self.assertEqual(connection.execute("""
                    SELECT count(DISTINCT candidate_id) FROM real_preview.candidate_taxonomy_assignments_lineage
                    WHERE source_id='fr.dgal.section-i' AND primary_key=ANY(%s)
                """, (["slaughter", "processing_and_preparation"],)).fetchone()[0], 1)
                self.assertEqual(connection.execute("""
                    SELECT count(DISTINCT candidate_id) FROM real_preview.candidate_taxonomy_assignments_lineage
                    WHERE source_id='fr.dgal.section-i' AND leaf_label ILIKE '%%cutting%%'
                """).fetchone()[0], 1)
                self.assertEqual(connection.execute("""
                    SELECT display_category,primary_key,mapping_status,mapping_method
                    FROM real_preview.candidate_taxonomy_assignments_lineage WHERE candidate_id=%s
                    GROUP BY display_category,primary_key,mapping_status,mapping_method
                """, (fsis_candidate_id,)).fetchall(), [("unclassified", "unclassified", "unmapped", "direct")])
                fallback = connection.execute("""
                    SELECT CASE WHEN category=ANY(ARRAY['animal_keeping_and_production','slaughter','processing_and_preparation',
                      'research_and_animal_use','other_regulated_premises','unclassified']::text[]) THEN category ELSE 'unclassified' END
                    FROM real_preview.candidates WHERE candidate_id=%s
                      AND NOT EXISTS (SELECT 1 FROM real_preview.candidate_taxonomy_assignment_sets s WHERE s.candidate_id=%s)
                """, (missing_artifact_candidate_id, missing_artifact_candidate_id)).fetchone()
                self.assertEqual(fallback, ("unclassified",))
                safe_fields = connection.execute("""
                    SELECT display_name,activity_label,activity_source,evidence_summary,source_record_url,source_name,observed_at
                    FROM real_preview.candidates WHERE source_group_key='source-group-1'
                """).fetchone()
                self.assertEqual(safe_fields[:6], ("Synthetic Facility", "Meat processing", "source", "Synthetic evidence summary", "https://example.test/record", "Synthetic source"))
                self.assertIsNotNone(safe_fields[6])
                with self.assertRaises(psycopg.Error):
                    with connection.transaction():
                        connection.execute(candidate_insert, ("a" * 64, "it.853-2004", "source-group-invalid-url", numeric_observation_id,
                            "numeric_source_coordinate", "IT", "Example", 44.1, 11.2, None, None, None, None,
                            "http://example.test/record", None, None, True, None))
                coarse_candidate_id = connection.execute(
                    "SELECT candidate_id FROM real_preview.candidates WHERE source_group_key='source-group-2'"
                ).fetchone()[0]
                connection.execute("""
                    INSERT INTO real_preview.local_reference_display_evidence
                      (candidate_id,snapshot_sha256,source_id,reference_latitude,reference_longitude,
                       display_precision,display_geometry_source,reference_source_id,reference_source)
                    VALUES (%s,%s,%s,48.8,2.3,'locality_reference_coarse',
                            'synthetic municipality reference; approximate, not facility coordinates',
                            'synthetic-ref-1','synthetic reference dataset')
                """, (coarse_candidate_id, "a" * 64, "fr.dgal.section-i"))
                display = connection.execute(
                    "SELECT display_latitude,display_longitude,display_geometry_source FROM real_preview.candidates WHERE candidate_id=%s",
                    (coarse_candidate_id,),
                ).fetchone()
                self.assertEqual(display[:2], (48.8, 2.3))
                self.assertIn("approximate", display[2])
                compact_map_categories = connection.execute("""
                    SELECT CASE WHEN c.display_geometry_source IS NOT NULL THEN ARRAY['unclassified']::text[]
                         ELSE COALESCE(array_agg(DISTINCT a.primary_key ORDER BY a.primary_key),ARRAY['unclassified']::text[]) END
                    FROM real_preview.candidates c
                    LEFT JOIN real_preview.candidate_taxonomy_assignment_sets s ON s.candidate_id=c.candidate_id
                    LEFT JOIN real_preview.candidate_taxonomy_assignments a ON a.assignment_set_id=s.assignment_set_id
                    WHERE c.candidate_id IN (%s,%s) GROUP BY c.candidate_id,c.display_geometry_source ORDER BY c.candidate_id
                """, (taxonomy_candidate_id, coarse_candidate_id)).fetchall()
                self.assertEqual(compact_map_categories, [(["unclassified"],), (["unclassified"],)])
                self.assertEqual(connection.execute(
                    "SELECT display_precision FROM real_preview.local_reference_display_evidence WHERE candidate_id=%s",
                    (coarse_candidate_id,),
                ).fetchone()[0], "locality_reference_coarse")
                with self.assertRaises(psycopg.Error):
                    with connection.transaction():
                        connection.execute(candidate_insert, ("a" * 64, "it.853-2004", "source-group-zero", numeric_observation_id, "numeric_source_coordinate", "IT", "Example", 0.0, 0.0,
                            None, None, None, None, None, None, None, True, None))
                self.assertEqual(connection.execute("SELECT count(*) FROM real_preview.observations").fetchone()[0], 4)
                self.assertEqual(connection.execute("SELECT count(*) FROM real_preview.observations WHERE facility_candidate").fetchone()[0], 4)
                self.assertEqual(connection.execute("SELECT count(*) FROM real_preview.observations WHERE location_class='unmapped_private_observation'").fetchone()[0], 2)
                self.assertEqual(connection.execute("SELECT count(*) FROM real_preview.candidates").fetchone()[0], 5)
                scope_counts = connection.execute("""
                    SELECT count(*) FILTER (WHERE default_map_scope),
                           count(*) FILTER (WHERE NOT default_map_scope),
                           count(*) FILTER (WHERE location_class='unmapped_private_observation'),
                           count(*) FILTER (WHERE default_map_scope AND location_class='numeric_source_coordinate')
                    FROM real_preview.candidates
                """).fetchone()
                self.assertEqual(scope_counts, (3, 2, 2, 2))
                self.assertEqual(connection.execute(
                    "SELECT map_scope_reason FROM real_preview.candidates WHERE source_group_key='source-group-3'"
                ).fetchone()[0], "general-food")

                # Synthetic-only worker handoff: the old placeholder job and
                # the configured Geoapify job both keep immutable target rows.
                connection.execute("""
                    INSERT INTO real_preview.source_manifests
                      (snapshot_sha256,source_id,source_artifact_sha256,normalized_sha256,normalized_rows,source_url,retrieved_at,code_version,config_version)
                    VALUES (%s,'au.npi.facilities',%s,%s,1,'https://example.invalid/','2026-10-01T00:00:00Z','synthetic','synthetic')
                """, ("a" * 64, "b" * 64, "c" * 64))
                au_observation_id = connection.execute(insert + " RETURNING preview_id", (
                    "a" * 64, "au.npi.facilities", "synthetic-au-geocode", "city_postal", True,
                    "AU", "Melbourne", "3000", None, None, None,
                )).fetchone()[0]
                connection.execute("""
                    INSERT INTO real_preview.candidates
                      (snapshot_sha256,source_id,source_group_key,representative_observation_id,
                       location_class,country_code,city,postal_code,observation_count)
                    VALUES (%s,'au.npi.facilities','synthetic-au-geocode',%s,
                            'city_postal','AU','Melbourne','3000',1)
                """, ("a" * 64, au_observation_id))
                au_candidate_id = connection.execute(
                    "SELECT candidate_id FROM real_preview.candidates WHERE source_group_key='synthetic-au-geocode'"
                ).fetchone()[0]
                connection.execute("""
                    INSERT INTO real_preview.candidate_private_location_evidence
                      (candidate_id,snapshot_sha256,source_id,location_evidence)
                    VALUES (%s,%s,'au.npi.facilities',%s::jsonb)
                """, (au_candidate_id, "a" * 64, json.dumps({"address": "10 Synthetic Test Road", "city": "Melbourne"})))
                connection.execute("""
                    INSERT INTO uec.sources(source_id,country_code,name,official_url,access_method)
                    VALUES ('au.npi.facilities','AU','Synthetic source','https://example.invalid/','synthetic_test')
                    ON CONFLICT (source_id) DO NOTHING
                """)
                connection.execute("""
                    INSERT INTO uec.raw_artifacts(storage_key,sha256,byte_size,media_type,retrieved_at)
                    VALUES ('synthetic-preview-artifact',%s,1,'text/csv',now()) ON CONFLICT (sha256) DO NOTHING
                """, ("d" * 64,))
                artifact_id = connection.execute("SELECT artifact_id FROM uec.raw_artifacts WHERE sha256=%s", ("d" * 64,)).fetchone()[0]
                source_record_id = connection.execute("""
                    INSERT INTO uec.source_records(source_id,source_record_key,artifact_id,raw_fields,parsed_at)
                    VALUES ('au.npi.facilities','synthetic-preview-link',%s,'{}'::jsonb,now())
                    RETURNING source_record_id
                """, (artifact_id,)).fetchone()[0]
                synthetic_query = "10 Synthetic Test Road, Melbourne, AU"
                placeholder_job_id = connection.execute("""
                    INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                    VALUES (%s,'pending-provider-review',%s) RETURNING job_id
                """, (source_record_id, synthetic_query)).fetchone()[0]
                geoapify_job_id = connection.execute("""
                    INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                    VALUES (%s,'geoapify',%s) RETURNING job_id
                """, (source_record_id, synthetic_query)).fetchone()[0]
                for job_id in (placeholder_job_id, geoapify_job_id):
                    connection.execute("""
                        INSERT INTO real_preview.geocode_targets(job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                        VALUES (%s,%s,%s,'au.npi.facilities','synthetic-au-geocode')
                    """, (job_id, au_candidate_id, "a" * 64))
                connection.execute("""
                    INSERT INTO uec.geocode_job_events(job_id,event_type,attempt_number,retryable,details)
                    VALUES (%s,'queued',1,false,
                      '{"processing_mode":"private_au_preview_pilot","provider_configuration":"geoapify_au_country_filter"}'::jsonb)
                """, (geoapify_job_id,))
                synthetic_response = {
                    "features": [{
                        "geometry": {"type": "Point", "coordinates": [144.9, -37.8]},
                        "properties": {"result_type": "building", "country_code": "au",
                                       "address_line1": "10 Synthetic Test Road",
                                       "rank": {"confidence": 0.97}},
                    }],
                }
                class ReuseConnection:
                    def __enter__(self):
                        return connection

                    def __exit__(self, *_args):
                        return False

                adapter = Mock()
                adapter.geocode.return_value = GeocodeOutcome(
                    "accepted", "high_confidence_address_match", -37.8, 144.9,
                    "synthetic-place", "geoapify_address_point", "geoapify_forward", False,
                    synthetic_response,
                )
                worker_args = (
                    DATABASE_URL, "geoapify", 24, 0, 1,
                )
                worker_options = {
                    "daily_budget": 24, "max_attempts": 1, "provider_interval": 1,
                    "worker_id": "synthetic-au-pilot", "au_npi_pilot": True,
                }
                display_revision_before = connection.execute(
                    "SELECT real_preview.display_evidence_revision()"
                ).fetchone()[0]
                with patch.object(WORKER.psycopg, "connect", return_value=ReuseConnection()), \
                     patch.object(WORKER, "get_adapter", return_value=adapter), \
                     redirect_stdout(io.StringIO()):
                    self.assertEqual(WORKER.run(*worker_args, **worker_options), 1)
                    display_revision_after = connection.execute(
                        "SELECT real_preview.display_evidence_revision()"
                    ).fetchone()[0]
                    self.assertEqual(WORKER.run(*worker_args, **worker_options), 0)
                    self.assertEqual(connection.execute(
                        "SELECT real_preview.display_evidence_revision()"
                    ).fetchone()[0], display_revision_after)
                self.assertNotEqual(display_revision_before, display_revision_after,
                                    "provider display evidence must invalidate the private map cache")
                adapter.geocode.assert_called_once_with(synthetic_query)
                self.assertEqual(connection.execute(
                    "SELECT count(*) FROM real_preview.geocode_targets WHERE candidate_id=%s", (au_candidate_id,)
                ).fetchone()[0], 2)
                api_row = connection.execute("""
                    SELECT candidate.display_latitude,candidate.display_longitude,
                           candidate.display_geometry_source,candidate.coordinate_method,
                           candidate.coordinate_provider,candidate.coordinate_confidence,
                           candidate.coordinate_confidence_band,candidate.latitude,candidate.longitude
                    FROM real_preview.candidates candidate
                    JOIN real_preview.source_manifests manifest
                      ON manifest.snapshot_sha256=candidate.snapshot_sha256 AND manifest.source_id=candidate.source_id
                    WHERE candidate.candidate_id=%s AND candidate.default_map_scope=true
                """, (au_candidate_id,)).fetchone()
                self.assertEqual(api_row[:2], (-37.8, 144.9))
                self.assertIn("normalized source-address line match", api_row[2])
                self.assertEqual(api_row[3:7], ("geoapify_forward", "Geoapify", 0.97, "high"))
                self.assertEqual(api_row[7:], (None, None), "source coordinates remain unchanged")
                self.assertEqual(connection.execute(
                    "SELECT count(*) FROM real_preview.geocode_display_evidence WHERE candidate_id=%s AND coordinate_review_status='automated_high_confidence_private_display'",
                    (au_candidate_id,),
                ).fetchone()[0], 1)

                def queued_job(source_key, query):
                    linked_record = connection.execute("""
                        INSERT INTO uec.source_records(source_id,source_record_key,artifact_id,raw_fields,parsed_at)
                        VALUES ('au.npi.facilities',%s,%s,'{}'::jsonb,now()) RETURNING source_record_id
                    """, (source_key, artifact_id)).fetchone()[0]
                    linked_job = connection.execute("""
                        INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                        VALUES (%s,'geoapify',%s) RETURNING job_id
                    """, (linked_record, query)).fetchone()[0]
                    connection.execute("""
                        INSERT INTO real_preview.geocode_targets(job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                        VALUES (%s,%s,%s,'au.npi.facilities','synthetic-au-geocode')
                    """, (linked_job, au_candidate_id, "a" * 64))
                    connection.execute("""
                        INSERT INTO uec.geocode_job_events(job_id,event_type,attempt_number,retryable,details)
                        VALUES (%s,'queued',1,false,
                          '{"processing_mode":"private_au_preview_pilot"}'::jsonb)
                    """, (linked_job,))
                    return linked_record

                restricted_before_record = queued_job("synthetic-restricted-before", "synthetic before restriction")
                connection.execute("""
                    INSERT INTO uec.record_access_events(source_record_id,action,reason_category,policy_version,maintainer)
                    VALUES (%s,'public_access_revoked','privacy','synthetic-test','synthetic-test')
                """, (restricted_before_record,))
                with patch.object(WORKER.psycopg, "connect", return_value=ReuseConnection()), \
                     patch.object(WORKER, "get_adapter", return_value=adapter), \
                     redirect_stdout(io.StringIO()):
                    self.assertEqual(WORKER.run(*worker_args, **worker_options), 0)
                adapter.geocode.assert_called_once()

                restricted_during_record = queued_job("synthetic-restricted-during", "synthetic during restriction")
                def restrict_during_request(_query):
                    connection.execute("""
                        INSERT INTO uec.record_access_events(source_record_id,action,reason_category,policy_version,maintainer)
                        VALUES (%s,'public_access_revoked','privacy','synthetic-test','synthetic-test')
                    """, (restricted_during_record,))
                    return adapter.geocode.return_value
                adapter.geocode.side_effect = restrict_during_request
                with patch.object(WORKER.psycopg, "connect", return_value=ReuseConnection()), \
                     patch.object(WORKER, "get_adapter", return_value=adapter), \
                     redirect_stdout(io.StringIO()):
                    self.assertEqual(WORKER.run(*worker_args, **worker_options), 1)
                self.assertEqual(connection.execute(
                    "SELECT count(*) FROM uec.geocode_results WHERE source_record_id=%s", (restricted_during_record,)
                ).fetchone()[0], 0)
                self.assertEqual(connection.execute(
                    "SELECT count(*) FROM real_preview.geocode_display_evidence WHERE candidate_id=%s AND coordinate_review_status='automated_high_confidence_private_display'",
                    (au_candidate_id,),
                ).fetchone()[0], 1)
                for relation in (
                    "uec.release_members",
                    "uec.map_facilities_public_discovery",
                    "uec.map_facilities_public_discovery_read_model",
                    "uec.graph_public_relationships",
                    "uec.graph_public_claims",
                ):
                    if connection.execute("SELECT to_regclass(%s)", (relation,)).fetchone()[0]:
                        self.assertEqual(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0], 0)
                public_preview = connection.execute("SELECT to_regclass('uec.real_preview_observations')").fetchone()[0]
                self.assertIsNone(public_preview)
                with self.assertRaises(psycopg.Error):
                    with connection.transaction():
                        connection.execute("UPDATE real_preview.observations SET city='Changed' WHERE source_identifier='synthetic-source-key'")
                with self.assertRaises(psycopg.Error):
                    with connection.transaction():
                        connection.execute("UPDATE real_preview.candidates SET city='Changed' WHERE source_group_key='source-group-1'")
            # The migration and all synthetic rows are rolled back with the disposable test transaction.
            connection.rollback()


if __name__ == "__main__":
    unittest.main()
