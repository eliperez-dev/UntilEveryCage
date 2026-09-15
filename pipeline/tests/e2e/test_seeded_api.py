import json, os, subprocess, sys, unittest, urllib.request
import uuid
from datetime import datetime, timezone
import psycopg
try:
    from .fixture import E2EEnvironment
except ImportError:
    from fixture import E2EEnvironment

class SeededApiE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
        cls.env = E2EEnvironment().start(); cls.env.seed_official_scenario()
    @classmethod
    def tearDownClass(cls): cls.env.stop()
    def get(self, path):
        with urllib.request.urlopen(f'http://localhost:{self.env.api_port}{path}', timeout=10) as r: return json.loads(r.read())
    def test_exact_city_and_unmapped_are_distinct(self):
        rows = self.get('/api/v2/locations?limit=100')['data']
        self.assertEqual({r['display_precision'] for r in rows}, {'exact','city','unmapped'})
    def test_restricted_record_is_absent(self):
        names = {r['canonical_name'] for r in self.get('/api/v2/locations?limit=100')['data']}
        self.assertNotIn('E2E restricted', names)

    def test_official_record_without_publication_approval_is_absent(self):
        names = {r['canonical_name'] for r in self.get('/api/v2/locations?limit=100')['data']}
        self.assertNotIn('E2E unapproved', names)

    def test_final_page_has_no_spurious_cursor(self):
        response = self.get('/api/v2/locations?limit=100')
        self.assertIsNone(response['meta']['next_cursor'])
    def test_lifecycle_and_history_are_returned(self):
        row = self.get('/api/v2/locations?lifecycle_status=active_observed&limit=100')['data'][0]
        self.assertEqual(row['lifecycle_status'], 'active_observed'); self.assertEqual(row['observation_count'], 1)

    def test_pagination_and_category_filter_are_applied(self):
        rows = self.get('/api/v2/locations?limit=2')['data']
        self.assertEqual(len(rows), 2)
        logistics = self.get('/api/v2/locations?category=logistics_and_storage&limit=10')['data']
        self.assertEqual(len(logistics), 1)
        self.assertEqual(logistics[0]['canonical_name'], 'E2E unmapped')

    def test_cursor_traversal_is_stable_and_non_overlapping(self):
        first = self.get('/api/v2/locations?limit=1')
        self.assertEqual(len(first['data']), 1)
        cursor = first['meta']['next_cursor']
        self.assertIsNotNone(cursor)
        second = self.get(f'/api/v2/locations?limit=10&cursor={cursor}')
        self.assertTrue(second['data'])
        self.assertNotEqual(first['data'][0]['facility_id'], second['data'][0]['facility_id'])

    def test_detail_endpoint_matches_public_list_contract(self):
        listed = self.get('/api/v2/locations?category=slaughter&limit=100')['data']
        self.assertEqual(len(listed), 1)
        detail = self.get(f"/api/v2/locations/{listed[0]['facility_id']}")
        self.assertEqual(detail['api_version'], 'v2')
        self.assertEqual(detail['data']['facility_id'], listed[0]['facility_id'])
        self.assertEqual(detail['data']['category'], listed[0]['category'])
        self.assertEqual(detail['data']['publication_profile'], listed[0]['publication_profile'])
        self.assertEqual(detail['data']['factual_review_status'], 'reviewed')
        self.assertEqual(detail['data']['privacy_screening_status'], 'passed')
        self.assertEqual(detail['data']['project_approval'], 'approved')
        self.assertEqual(detail['data']['release_id'], detail['meta']['release_id'])
        self.assertEqual(detail['data']['provenance_source_id'], 'e2e.official')

    def test_csv_export_is_escaped_bounded_and_manifest_bound(self):
        request = urllib.request.Request(f"http://localhost:{self.env.api_port}/api/v2/locations.csv?profile=official")
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.headers['Content-Type'], 'text/csv; charset=utf-8')
            self.assertEqual(response.headers['X-Uec-Manifest-Sha256'], 'dcf1cb50c078057cac2527936332e35892c2c13ecdcf2f545176acd17897cde7')
            body = response.read().decode()
        self.assertIn('release_profile', body)
        self.assertIn('manifest_sha256', body)
        self.assertNotIn('E2E restricted', body)

    def test_provenance_and_precision_are_returned_for_each_public_record(self):
        response = self.get('/api/v2/locations?limit=100')
        self.assertEqual(response['meta']['release_id'], 'e2e-promoted')
        self.assertEqual(response['meta']['ruleset_version'], 'e2e-v1')
        self.assertEqual(response['meta']['profile'], 'official')
        for row in response['data']:
            self.assertEqual(row['source_type'], 'official')
            self.assertEqual(row['publication_profile'], 'official')
            self.assertEqual(row['factual_review_status'], 'reviewed')
            self.assertEqual(row['privacy_screening_status'], 'passed')
            self.assertEqual(row['project_approval'], 'approved')
            self.assertEqual(row['reviewer_role'], 'maintainer')
            self.assertEqual(row['provenance_source_id'], 'e2e.official')
            self.assertEqual(row['provenance_source_name'], 'Synthetic official source')
            self.assertEqual(row['provenance_source_url'], 'https://example.invalid/official')
            self.assertEqual(row['release_id'], response['meta']['release_id'])
            self.assertEqual(row['release_ruleset_version'], response['meta']['ruleset_version'])
            self.assertIn(row['category'], ('slaughter', 'fish_processing', 'logistics_and_storage'))
            self.assertIsNotNone(row['provenance_retrieved_at'])
            self.assertIn(row['display_precision'], ('exact', 'city', 'unmapped'))
            self.assertEqual(row['observation_count'], 1)
            self.assertIsNotNone(row['first_observed_at'])
            self.assertIsNotNone(row['last_observed_at'])

    def test_facets_apply_filters_and_never_include_restricted_record(self):
        body = self.get('/api/v2/discovery/facets?profile=official&category=slaughter')
        self.assertEqual(body['meta']['release_id'], 'e2e-promoted')
        self.assertEqual(body['meta']['ruleset_version'], 'e2e-v1')
        self.assertEqual(body['meta']['coverage_scope'], 'selected_promoted_release_public_facilities')
        self.assertIn('not story-wide or animal counts', body['meta']['count_semantics'])
        self.assertEqual(body['dimensions']['category'], [{'value': 'slaughter', 'count': 1}])
        self.assertNotIn('restricted', json.dumps(body))
        empty = self.get('/api/v2/discovery/facets?country_code=ZZ')
        self.assertEqual(empty['dimensions']['category'], [])

    def test_combination_filters_and_zero_result_are_deterministic(self):
        rows = self.get('/api/v2/locations?country_code=DK&category=slaughter&display_precision=exact&limit=10')['data']
        self.assertEqual(len(rows), 1)
        restricted = self.get('/api/v2/locations?country_code=DK&category=retail_and_prepared_food&limit=10')['data']
        self.assertEqual(restricted, [])
        empty = self.get('/api/v2/locations?country_code=ZZ&limit=10')
        self.assertEqual(empty['data'], [])

    def test_failed_candidate_does_not_replace_promoted_release(self):
        self.env.create_failed_candidate()
        script = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', 'stages', 'validate-release.py')
        result = subprocess.run([sys.executable, script, 'e2e-failed-candidate', '--expected-records', '0'], env={**os.environ, 'UEC_DATABASE_URL': self.env.database_url}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        response = self.get('/api/v2/locations?limit=100')
        self.assertEqual(response['meta']['release_id'], 'e2e-promoted')
        self.assertTrue(response['data'])

    def test_blocked_candidate_remains_unpublished_and_prior_release_stays_promoted(self):
        self.env.create_failed_candidate()
        script = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', 'stages', 'validate-release.py')
        result = subprocess.run([sys.executable, script, 'e2e-failed-candidate', '--expected-records', '1'], env={**os.environ, 'UEC_DATABASE_URL': self.env.database_url}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        import psycopg
        with psycopg.connect(self.env.database_url) as db:
            statuses = dict(db.execute("SELECT release_id, status FROM uec.releases WHERE release_id IN ('e2e-promoted', 'e2e-failed-candidate')").fetchall())
        self.assertEqual(statuses, {'e2e-promoted': 'promoted', 'e2e-failed-candidate': 'candidate'})
        response = self.get('/api/v2/locations?limit=100')
        self.assertEqual(response['meta']['release_id'], 'e2e-promoted')

    def test_z_restoration_requires_an_explicit_append_only_event(self):
        self.env.restore_restricted_record()
        names = {r['canonical_name'] for r in self.get('/api/v2/locations?limit=100')['data']}
        self.assertIn('E2E restricted', names)

    def test_z1_approval_does_not_follow_source_record_into_new_profile(self):
        with psycopg.connect(self.env.database_url) as db:
            facility_id, observation_id = db.execute("SELECT facility_id, observation_id FROM uec.observations o JOIN uec.source_records r USING (source_record_id) WHERE r.source_record_key = 'exact'").fetchone()
            db.execute("INSERT INTO uec.releases (release_id,status,ruleset_version,profile,summary) VALUES ('e2e-secondary-later','promoted','e2e-v2','secondary','{}')")
            db.execute("INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) VALUES ('e2e-secondary-later',%s,%s,true)", (facility_id, observation_id))
        self.assertEqual(self.get('/api/v2/locations?profile=secondary&limit=100')['data'], [])

    def test_z1b_candidate_review_does_not_revoke_independent_promoted_approval(self):
        promoted = 'e2e-promoted'
        candidate = 'e2e-independent-candidate'
        with psycopg.connect(self.env.database_url) as db:
            record_id, facility_id, observation_id = db.execute("SELECT r.source_record_id, o.facility_id, o.observation_id FROM uec.observations o JOIN uec.source_records r USING (source_record_id) WHERE r.source_record_key='unmapped'").fetchone()
            db.execute("INSERT INTO uec.releases (release_id,status,ruleset_version,profile,summary) VALUES (%s,'candidate','e2e-v2','official','{}')", (candidate,))
            db.execute("INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) VALUES (%s,%s,%s,true)", (candidate, facility_id, observation_id))
            db.execute("INSERT INTO uec.publication_review_events (source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role) VALUES (%s,%s,'reviewed','passed','approved',true,'maintainer')", (record_id, candidate))
        names = {row['canonical_name']: row for row in self.get('/api/v2/locations?limit=100')['data']}
        self.assertIn('E2E unmapped', names)
        self.assertEqual(names['E2E unmapped']['project_approval'], 'approved')

        with psycopg.connect(self.env.database_url) as db:
            db.execute("INSERT INTO uec.publication_review_events (source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role) VALUES (%s,%s,'rejected','passed','denied',false,'maintainer')", (record_id, candidate))
        names = {row['canonical_name']: row for row in self.get('/api/v2/locations?limit=100')['data']}
        self.assertIn('E2E unmapped', names)
        self.assertEqual(names['E2E unmapped']['project_approval'], 'approved')

        with psycopg.connect(self.env.database_url) as db:
            db.execute("INSERT INTO uec.publication_review_events (source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role) VALUES (%s,%s,'rejected','passed','denied',false,'maintainer')", (record_id, promoted))
        names = {row['canonical_name'] for row in self.get('/api/v2/locations?limit=100')['data']}
        self.assertNotIn('E2E unmapped', names)

    def test_z2_summary_excludes_suppressed_observation(self):
        now = datetime.now(timezone.utc)
        with psycopg.connect(self.env.database_url) as db:
            facility_id = db.execute("SELECT facility_id FROM uec.facilities WHERE canonical_name='E2E exact'").fetchone()[0]
            artifact, record, observation = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            db.execute("INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) VALUES (%s,'e2e/suppressed-summary',%s,1,%s)", (artifact, uuid.uuid4().hex * 2, now))
            db.execute("INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) VALUES (%s,'e2e.official','suppressed-summary',%s,'{}',%s)", (record, artifact, now))
            db.execute("INSERT INTO uec.observations (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,first_observed_at) VALUES (%s,%s,%s,%s,'{}','{}','e2e-v1','e2e','slaughter','approved',false,%s)", (observation, facility_id, record, now, now))
            db.execute("INSERT INTO uec.record_access_events (source_record_id,action,reason_category,policy_version,maintainer) VALUES (%s,'public_access_revoked','privacy','ethics-v1','e2e')", (record,))
        row = next(r for r in self.get('/api/v2/locations?limit=100')['data'] if r['canonical_name'] == 'E2E exact')
        self.assertEqual(row['observation_count'], 1)

    def test_z3_facility_suppression_without_source_link_revokes_public_observation(self):
        with psycopg.connect(self.env.database_url) as db:
            facility_id = db.execute("SELECT facility_id FROM uec.facilities WHERE canonical_name='E2E exact'").fetchone()[0]
            self.assertEqual(db.execute("SELECT count(*) FROM uec.facility_source_links WHERE facility_id=%s", (facility_id,)).fetchone()[0], 0)
            case_id = uuid.uuid4()
            db.execute("INSERT INTO uec.suppression_cases (case_id,reason_category,status,policy_version,actor,decision) VALUES (%s,'privacy','active','ethics-v1','e2e','suppress')", (case_id,))
            db.execute("INSERT INTO uec.suppression_references (case_id,facility_id,scope) VALUES (%s,%s,'whole_record')", (case_id, facility_id))
        names = {r['canonical_name'] for r in self.get('/api/v2/locations?limit=100')['data']}
        self.assertNotIn('E2E exact', names)
        with urllib.request.urlopen(f'http://localhost:{self.env.api_port}/api/v2/locations.csv?profile=official', timeout=10) as response:
            self.assertNotIn('E2E exact', response.read().decode())

if __name__ == '__main__': unittest.main()
