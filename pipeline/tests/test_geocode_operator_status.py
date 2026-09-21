import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class GeocodeOperatorStatusContractTests(unittest.TestCase):
    def test_operator_status_is_aggregate_only_and_eta_is_documented(self):
        source = (ROOT / "scripts/diagnostics/geocode-operator-status.py").read_text()
        self.assertIn("privacy_boundary", source)
        self.assertIn("eta_days", source)
        self.assertIn("addresses, queries, payloads", source)

    def test_worker_does_not_log_identifiers_or_queries(self):
        source = (ROOT / "scripts/stages/geocode-worker.py").read_text()
        self.assertNotIn("job={job_id}", source)
        self.assertNotIn("source_record_id=", source)
        self.assertNotIn("query=", source)
        self.assertIn("status=", source)

    def test_compose_requires_environment_secret(self):
        source = (ROOT.parent / "docker-compose.pipeline.yml").read_text()
        self.assertIn("GEOAPIFY_API_KEY: ${GEOAPIFY_API_KEY:-}", source)
        self.assertNotIn("--api-key", source)


if __name__ == "__main__":
    unittest.main()
