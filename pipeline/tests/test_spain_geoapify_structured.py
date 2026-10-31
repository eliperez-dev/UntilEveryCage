"""Source-component matching and a rollback-only retained-response proof."""
import copy
import hashlib
import json
import os
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlsplit

import psycopg
from psycopg.types.json import Jsonb

from pipeline.geocoding.geoapify import GeoapifyAdapter
from pipeline.geocoding.first_pass import structured_query
from pipeline.tests.test_locationiq_first_pass import Response, query

ROOT = Path(__file__).parents[2]


def feature():
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-3.7038, 40.4168]},
            "properties": {"country_code": "es", "street": "Calle Example", "housenumber": "4",
                "city": "Madrid", "state": "Comunidad de Madrid", "postcode": "28001",
                "result_type": "building", "address_line1": "4 Calle Example", "rank": {"confidence": .96}}}


def evaluate(features, source_query, **options):
    seen = {}
    def opener(request, **_):
        seen["params"] = parse_qs(urlsplit(request.full_url).query)
        return Response({"type": "FeatureCollection", "features": features})
    adapter = GeoapifyAdapter(api_key="placeholder-test-key", country_code="es",
        private_source_profile=True, allow_locality_match=False, opener=opener, **options)
    return adapter.geocode(source_query), seen


class SpanishStructuredGeoapifyTests(unittest.TestCase):
    def test_provider_structured_input_uses_components_without_text(self):
        outcome, seen = evaluate([feature()], query("Calle de Example 4"), spanish_structured_search=True)
        self.assertEqual(outcome.status, "accepted")
        self.assertNotIn("text", seen["params"])
        self.assertNotIn("state", seen["params"])
        for key, expected in (("street", "calle example"), ("housenumber", "4"),
                              ("city", "Madrid"), ("postcode", "28001"), ("country", "Spain")):
            self.assertEqual(seen["params"][key], [expected])
        self.assertEqual(outcome.response["_uec_request_input_mode"], "geoapify_structured_address_v2")
        changed = feature(); changed["properties"]["housenumber"] = "5"
        self.assertNotEqual(evaluate([changed], query("Calle Example 4"),
            spanish_structured_search=True)[0].status, "accepted")
        changed = feature(); changed["properties"]["state"] = "Catalonia"
        self.assertNotEqual(evaluate([changed], query("Calle Example 4"),
            spanish_structured_search=True)[0].status, "accepted")

    def test_structured_provider_mode_rejects_unparseable_addresses_before_request(self):
        outcome, seen = evaluate([feature()], query("Example Industrial Estate"), spanish_structured_search=True)
        self.assertEqual(outcome.response["error"], "structured_numbered_street_required")
        self.assertEqual(seen, {})

    def test_rejected_diagnostics_retain_component_scores_without_contact_fields(self):
        item = feature()
        item["properties"]["rank"] = {"confidence": .6, "confidence_city_level": 1,
            "confidence_street_level": 1, "confidence_building_level": .2,
            "match_type": "match_by_street", "unrelated": "omit"}
        item["properties"]["contact"] = "omit"
        outcome, _ = evaluate([item], query("Calle Example 4"))
        retained = outcome.response["features"][0]["properties"]
        self.assertEqual(retained["rank_confidence_building_level"], .2)
        self.assertEqual(retained["rank_match_type"], "match_by_street")
        self.assertNotIn("contact", retained)
        self.assertNotIn("unrelated", retained)

    def test_formats_provider_text_but_matches_original_components(self):
        raw_query = query("Industrial Estate, C/ Example, 4, Nave 2")
        outcome, seen = evaluate([feature()], raw_query, spanish_structured_search=False)
        self.assertEqual(outcome.status, "accepted")
        self.assertEqual(outcome.precision, "geoapify_address_point")
        self.assertEqual(seen["params"]["text"], ["calle example 4, Madrid, 28001, Comunidad de Madrid, Spain"])
        self.assertEqual(json.loads(raw_query)["address"], "Industrial Estate, C/ Example, 4, Nave 2")

    def test_default_spain_mode_selects_structured_or_state_free_text_automatically(self):
        outcome, seen = evaluate([feature()], query("Calle Example 4"))
        self.assertEqual(outcome.status, "accepted")
        self.assertNotIn("text", seen["params"])
        self.assertNotIn("state", seen["params"])
        outcome, seen = evaluate([], query("Example Industrial Estate"))
        self.assertIn("text", seen["params"])
        self.assertNotIn("Comunidad de Madrid", seen["params"]["text"][0])
        self.assertEqual(outcome.response["_uec_request_input_mode"], "geoapify_spanish_address_town_v1")

    def test_context_number_type_coordinates_and_ambiguity_are_required(self):
        changes = ({"housenumber": "5"}, {"street": "Calle Other"}, {"city": "Sevilla"},
            {"state": "Catalonia"}, {"postcode": "28002"}, {"country_code": "pt"},
            {"rank": {"confidence": .89}}, {"rank": {"confidence": 1.1}},
            {"rank": {"confidence": True}}, {"result_type": "street"})
        for change in changes:
            item = feature(); item["properties"].update(change)
            self.assertNotEqual(evaluate([item], query("C/ Example, 4"))[0].status, "accepted")
        for geometry in ({"type": "Point", "coordinates": [0, 0]},
                         {"type": "Polygon", "coordinates": [-3.7038, 40.4168]}):
            item = feature(); item["geometry"] = geometry
            self.assertNotEqual(evaluate([item], query("C/ Example, 4"))[0].status, "accepted")
        self.assertEqual(evaluate([feature(), feature()], query("C/ Example, 4"))[0].acceptance,
                         "ambiguous_multiple_viable_results")
        self.assertNotEqual(evaluate([feature()], query("Calle Example"))[0].status, "accepted")

    def test_omitted_road_type_keeps_confidence_context_and_uniqueness_requirements(self):
        self.assertEqual(evaluate([feature()], query("Example 4"))[0].status, "accepted")
        low = feature(); low["properties"]["rank"]["confidence"] = .89
        self.assertNotEqual(evaluate([low], query("Example 4"))[0].status, "accepted")
        other = feature(); other["properties"]["street"] = "Avenida Example"
        self.assertEqual(evaluate([feature(), other], query("Example 4"))[0].acceptance,
                         "ambiguous_multiple_viable_results")
        self.assertNotEqual(evaluate([feature()], query("CR Example 4"))[0].status, "accepted")

    def test_invalid_context_does_not_call_provider(self):
        for value in ('{"schema_version":"wrong"}', query("Calle Example 4", locality=""),
                      query("Calle Example 4", country="GB")):
            outcome, seen = evaluate([feature()], value)
            self.assertEqual(outcome.acceptance, "unresolved")
            self.assertEqual(outcome.response["error"], "invalid_source_address")
            self.assertEqual(seen, {})


@unittest.skipUnless(os.environ.get("UEC_SPAIN_STRUCTURED_SQL_TESTS") == "1",
                     "assigned retained Spain database required")
class SpanishStructuredGeoapifyPostgisTests(unittest.TestCase):
    def test_retained_projection_replay_uses_stored_rows_without_another_request(self):
        with psycopg.connect(os.environ["UEC_DATABASE_URL"], options="-c statement_timeout=30000") as connection:
            self.assertEqual(connection.execute("SELECT current_database()").fetchone()[0],
                             "uec_launch_sources_test_20261025")
            row = connection.execute("""SELECT DISTINCT result.geocode_result_id,
                    EXISTS(SELECT 1 FROM real_preview.geocode_display_evidence evidence
                           WHERE evidence.geocode_result_id=result.geocode_result_id) AS mapped
                FROM uec.geocode_results result JOIN uec.geocode_jobs job
                  ON job.source_record_id=result.source_record_id AND job.provider_id=result.provider_id AND job.query=result.query
                JOIN real_preview.geocode_targets target USING(job_id)
                WHERE target.source_id='es.locations' AND result.provider_id='geoapify'
                  AND result.status='accepted' AND result.match_method='geoapify_forward'
                  AND CASE WHEN result.query LIKE '{%' THEN real_preview.spanish_geoapify_address_matches(
                    result.response->'features'->coalesce((result.response->>'_uec_selected_feature_index')::integer,0),
                    result.query::jsonb->>'address',result.query::jsonb->>'locality',
                    result.query::jsonb->>'postcode',result.query::jsonb->>'region') ELSE false END
                ORDER BY mapped,result.geocode_result_id LIMIT 1""").fetchone()
            self.assertIsNotNone(row, "retained matching Spanish result required")
            result_id = row[0]
            def counts():
                return connection.execute("""SELECT
                    (SELECT count(*) FROM real_preview.geocode_display_evidence WHERE geocode_result_id=%s),
                    (SELECT count(*) FROM uec.geocode_results r JOIN uec.geocode_results original
                       ON original.geocode_result_id=%s AND r.source_record_id=original.source_record_id
                         AND r.provider_id=original.provider_id AND r.query=original.query),
                    (SELECT count(*) FROM uec.geocode_request_reservations reservation JOIN uec.geocode_jobs job USING(job_id)
                       JOIN uec.geocode_results original ON original.geocode_result_id=%s
                         AND original.source_record_id=job.source_record_id AND original.provider_id=job.provider_id
                         AND original.query=job.query)""", (result_id,result_id,result_id)).fetchone()
            before = counts()
            with connection.transaction(force_rollback=True):
                connection.execute("SELECT count(*) FROM real_preview.project_spain_geoapify_result(%s)", (result_id,))
                after = counts()
                self.assertGreaterEqual(after[0], 1)
                self.assertEqual(after[1:], before[1:])
                connection.execute("SELECT count(*) FROM real_preview.project_spain_geoapify_result(%s)", (result_id,))
                self.assertEqual(counts(), after)
                connection.execute("SELECT count(*) FROM real_preview.project_spain_geoapify_result(%s)",
                                   ("00000000-0000-0000-0000-000000000000",))
                self.assertEqual(counts(), after)
                with connection.transaction(force_rollback=True):
                    fresh = connection.execute("""INSERT INTO uec.geocode_results(source_record_id,provider_id,
                        provider_version,query,provider_address_id,result,precision,match_method,status,
                        attempt_number,retryable,response,queried_at)
                        SELECT source_record_id,provider_id,'projection-wrapper-rollback',query,provider_address_id,
                          result,precision,match_method,status,attempt_number,retryable,response,queried_at
                        FROM uec.geocode_results WHERE geocode_result_id=%s RETURNING geocode_result_id""", (result_id,)).fetchone()[0]
                    self.assertGreaterEqual(connection.execute("SELECT count(*) FROM real_preview.geocode_display_evidence WHERE geocode_result_id=%s",
                                                               (fresh,)).fetchone()[0], 1)
                self.assertEqual(counts(), after)
            self.assertEqual(counts(), before)

    def test_real_retained_match_and_rejection_guards_rollback(self):
        from pipeline.scripts.release_baseline import load_contract, verify_connection, _migration_checksums
        with psycopg.connect(os.environ["UEC_DATABASE_URL"]) as connection:
            self.assertEqual(connection.execute("SELECT current_database()").fetchone()[0],
                             "uec_launch_sources_test_20261025")
            contract = load_contract(ROOT / "pipeline/contracts/development-baseline.json")
            migration = ROOT / "pipeline/migrations/113_spain_geoapify_structured_address.sql"
            before = _migration_checksums()
            installed = connection.execute("SELECT 1 FROM uec.schema_migrations WHERE version=%s",(migration.stem,)).fetchone()
            if installed is None:
                before.pop(migration.stem)
            self.assertEqual(verify_connection(connection, contract, before)["status"], "verified")
            connection.execute(migration.read_text(encoding="utf-8"))
            if installed is None:
                connection.execute("INSERT INTO uec.schema_migrations(version,sha256) VALUES(%s,%s)",
                                   (migration.stem,hashlib.sha256(migration.read_bytes()).hexdigest()))
            self.assertEqual(verify_connection(connection, contract)["status"], "verified")
            # SQL independently rejects a postcode mismatch and malformed
            # properties, even if Python marked the outcome accepted.
            for change in ({}, {"postcode":"28002"}, {"city":"Other Town"},
                           {"housenumber":"5"}, {"result_type":None}, {"rank":{"confidence":True}}):
                item=feature(); item["properties"].update(change)
                accepted=connection.execute("SELECT real_preview.spanish_geoapify_address_matches(%s,%s,%s,%s,%s)",
                    (Jsonb(item),"Estate, C/ Example, 4, Nave 2","Madrid","28001","Comunidad de Madrid")).fetchone()[0]
                self.assertEqual(accepted,not bool(change))
            rows = connection.execute("""SELECT DISTINCT r.geocode_result_id,r.source_record_id,r.response,
                    t.candidate_id,t.snapshot_sha256,t.source_record_key,e.location_evidence,v.municipality
                FROM uec.geocode_results r JOIN uec.geocode_jobs j ON j.source_record_id=r.source_record_id
                    AND j.provider_id=r.provider_id AND j.query=r.query
                JOIN real_preview.geocode_targets t USING(job_id)
                JOIN real_preview.candidate_private_location_evidence e USING(candidate_id,snapshot_sha256,source_id)
                JOIN LATERAL(SELECT municipality FROM real_preview.spain_verified_locality_evidence v
                    WHERE v.candidate_id=t.candidate_id AND v.snapshot_sha256=t.snapshot_sha256
                    ORDER BY retrieved_at DESC,evidence_event_id DESC LIMIT 1) v ON true
                WHERE r.match_method='geoapify_query_diagnostic_v1' AND t.source_id='es.locations'
                ORDER BY r.geocode_result_id""").fetchall()
            proved = ambiguous = 0
            for _, record, retained, candidate, snapshot, key, location, municipality in rows:
                features = copy.deepcopy(retained.get("features", []))
                for item in features:
                    props = item["properties"]
                    if "rank_confidence" in props:
                        props["rank"] = {"confidence": props.pop("rank_confidence")}
                raw_query = structured_query("es.locations", location, municipality=municipality)
                outcome, _ = evaluate(features, raw_query)
                if outcome.acceptance == "ambiguous_multiple_viable_results":
                    ambiguous += 1
                    source=json.loads(raw_query)
                    viable=connection.execute("""SELECT count(*) FROM jsonb_array_elements(%s) item
                        WHERE real_preview.spanish_geoapify_address_matches(item,%s,%s,%s,%s)""",
                        (Jsonb(features),source["address"],source["locality"],source["postcode"],source["region"])).fetchone()[0]
                    self.assertGreater(viable,1)
                if outcome.status != "accepted":
                    continue
                proved += 1
                with connection.transaction(force_rollback=True):
                    job = connection.execute("""INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                        VALUES(%s,'geoapify',%s) ON CONFLICT(source_record_id,provider_id,query)
                        DO NOTHING RETURNING job_id""", (record, raw_query)).fetchone()
                    if job is None:
                        job = connection.execute("SELECT job_id FROM uec.geocode_jobs WHERE source_record_id=%s AND provider_id='geoapify' AND query=%s", (record, raw_query)).fetchone()
                    connection.execute("""INSERT INTO real_preview.geocode_targets(job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                        VALUES(%s,%s,%s,'es.locations',%s) ON CONFLICT DO NOTHING""", (job[0],candidate,snapshot,key))
                    connection.execute("""INSERT INTO uec.geocode_job_events(job_id,event_type,attempt_number,retryable,details)
                        VALUES(%s,'queued',1,false,%s)""", (job[0],Jsonb({"processing_mode":"private_geoapify_source_profile","profile_id":"geoapify-es-aesan-rgseaa"})))
                    selected = features[outcome.response["_uec_selected_feature_index"]]
                    for label in ("valid", "wrong_town", "wrong_number", "wrong_province", "wrong_postcode", "low_confidence", "ambiguous", "wrong_geometry", "forged_query"):
                        with connection.transaction(force_rollback=True):
                            payload = copy.deepcopy(outcome.response)
                            props = payload["features"][payload["_uec_selected_feature_index"]]["properties"]
                            if label == "wrong_town":
                                for field in ("city","town","municipality","village","suburb"): props[field]="Definitely Different Locality"
                            if label == "wrong_number": props["housenumber"]="999999"
                            if label == "wrong_province": props.update(province="Definitely Different Province",state="Definitely Different Region",state_code="")
                            if label == "low_confidence": props["rank"]["confidence"]=.5
                            if label == "ambiguous": payload["features"]=[selected,selected]; payload["_uec_selected_feature_index"]=0
                            test_query=raw_query
                            if label in ("forged_query","wrong_postcode"):
                                changed=json.loads(raw_query)
                                changed["locality" if label=="forged_query" else "postcode"]="forged town" if label=="forged_query" else "00000"
                                test_query=json.dumps(changed)
                                forged_job=connection.execute("""INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                                    VALUES(%s,'geoapify',%s) RETURNING job_id""",(record,test_query)).fetchone()[0]
                                connection.execute("""INSERT INTO real_preview.geocode_targets(job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                                    VALUES(%s,%s,%s,'es.locations',%s)""",(forged_job,candidate,snapshot,key))
                                connection.execute("""INSERT INTO uec.geocode_job_events(job_id,event_type,attempt_number,retryable,details)
                                    VALUES(%s,'queued',1,false,%s)""",(forged_job,Jsonb({"processing_mode":"private_geoapify_source_profile","profile_id":"geoapify-es-aesan-rgseaa"})))
                            latitude=outcome.latitude if label!="wrong_geometry" else 0
                            result=connection.execute("""INSERT INTO uec.geocode_results(source_record_id,provider_id,provider_version,query,result,
                                precision,match_method,status,attempt_number,retryable,response,queried_at)
                                VALUES(%s,'geoapify','structured-rollback-acceptance',%s,ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,
                                'geoapify_address_point','geoapify_forward','accepted',1,false,%s,now()) RETURNING geocode_result_id""",
                                (record,test_query,outcome.longitude,latitude,Jsonb(payload))).fetchone()[0]
                            if label in ("valid","wrong_town","wrong_number","wrong_province","low_confidence"):
                                source=json.loads(raw_query)
                                rule=connection.execute("SELECT real_preview.spanish_geoapify_address_matches(%s,%s,%s,%s,%s)",
                                    (Jsonb(payload["features"][payload["_uec_selected_feature_index"]]),source["address"],source["locality"],source["postcode"],source["region"])).fetchone()[0]
                                self.assertEqual(rule,label=="valid",f"matcher_{label}")
                            matched=connection.execute("SELECT count(*) FROM real_preview.geocode_display_evidence WHERE candidate_id=%s AND geocode_result_id=%s",(candidate,result)).fetchone()[0]
                            self.assertEqual(matched,int(label=="valid"),label)
            self.assertGreaterEqual(proved, 1, "retained real match required")
            self.assertGreaterEqual(ambiguous, 1, "retained ambiguous control required")
            connection.rollback()
            self.assertEqual(verify_connection(connection, contract, before)["status"], "verified")
            self.assertEqual(connection.execute("SELECT count(*) FROM uec.geocode_results WHERE provider_version='structured-rollback-acceptance'").fetchone()[0],0)


if __name__ == "__main__":
    unittest.main()
