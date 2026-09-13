import json, os, subprocess, sys, unittest, urllib.request
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
        with urllib.request.urlopen(f'http://localhost:{self.env.api_port}{path}') as r: return json.loads(r.read())
    def test_exact_city_and_unmapped_are_distinct(self):
        rows = self.get('/api/v2/locations?limit=100')['data']
        self.assertEqual({r['display_precision'] for r in rows}, {'exact','city','unmapped'})
    def test_restricted_record_is_absent(self):
        names = {r['canonical_name'] for r in self.get('/api/v2/locations?limit=100')['data']}
        self.assertNotIn('E2E restricted', names)
    def test_lifecycle_and_history_are_returned(self):
        row = self.get('/api/v2/locations?lifecycle_status=active_observed&limit=100')['data'][0]
        self.assertEqual(row['lifecycle_status'], 'active_observed'); self.assertEqual(row['observation_count'], 1)

    def test_pagination_and_category_filter_are_applied(self):
        rows = self.get('/api/v2/locations?limit=2')['data']
        self.assertEqual(len(rows), 2)
        logistics = self.get('/api/v2/locations?category=logistics_and_storage&limit=10')['data']
        self.assertEqual(len(logistics), 1)
        self.assertEqual(logistics[0]['canonical_name'], 'E2E unmapped')

    def test_provenance_and_precision_are_returned_for_each_public_record(self):
        response = self.get('/api/v2/locations?limit=100')
        self.assertEqual(response['meta']['release_id'], 'e2e-promoted')
        self.assertEqual(response['meta']['ruleset_version'], 'e2e-v1')
        self.assertEqual(response['meta']['profile'], 'official')
        for row in response['data']:
            self.assertEqual(row['source_type'], 'official')
            self.assertEqual(row['provenance_source_id'], 'e2e.official')
            self.assertEqual(row['provenance_source_name'], 'Synthetic official source')
            self.assertEqual(row['provenance_source_url'], 'https://example.invalid/official')
            self.assertEqual(row['release_id'], response['meta']['release_id'])
            self.assertEqual(row['release_ruleset_version'], response['meta']['ruleset_version'])
            self.assertIsNotNone(row['provenance_retrieved_at'])
            self.assertIn(row['display_precision'], ('exact', 'city', 'unmapped'))
            self.assertEqual(row['observation_count'], 1)
            self.assertIsNotNone(row['first_observed_at'])
            self.assertIsNotNone(row['last_observed_at'])

    def test_failed_candidate_does_not_replace_promoted_release(self):
        self.env.create_failed_candidate()
        script = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', 'stages', 'validate-release.py')
        result = subprocess.run([sys.executable, script, 'e2e-failed-candidate', '--expected-records', '0'], env={**os.environ, 'UEC_DATABASE_URL': self.env.database_url}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        response = self.get('/api/v2/locations?limit=100')
        self.assertEqual(response['meta']['release_id'], 'e2e-promoted')
        self.assertTrue(response['data'])

if __name__ == '__main__': unittest.main()
