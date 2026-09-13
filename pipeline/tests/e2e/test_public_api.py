import json
import unittest
import urllib.error
import urllib.request

from fixture import E2EEnvironment

class PublicApiE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = E2EEnvironment().start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    def get(self, path):
        with urllib.request.urlopen(f"http://localhost:{self.env.api_port}{path}") as response:
            return response.status, json.loads(response.read())

    def test_default_is_empty_before_promotion(self):
        status, body = self.get("/api/v2/locations?country_code=DK")
        self.assertEqual(status, 200); self.assertEqual(body["api_version"], "v2"); self.assertEqual(body["data"], [])

    def test_filters_do_not_bypass_publication_gate(self):
        for path in ("?category=retail_and_prepared_food", "?display_precision=city", "?lifecycle_status=explicitly_closed"):
            _, body = self.get("/api/v2/locations" + path)
            self.assertEqual(body["data"], [])

    def test_invalid_pagination_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.get("/api/v2/locations?limit=invalid")
        self.assertEqual(error.exception.code, 400)

if __name__ == "__main__":
    unittest.main()
