import json, os, unittest, urllib.request
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
        for row in self.get('/api/v2/locations?limit=100')['data']:
            self.assertEqual(row['source_type'], 'official')
            self.assertIn(row['display_precision'], ('exact', 'city', 'unmapped'))
            self.assertEqual(row['observation_count'], 1)
            self.assertIsNotNone(row['first_observed_at'])
            self.assertIsNotNone(row['last_observed_at'])

if __name__ == '__main__': unittest.main()
