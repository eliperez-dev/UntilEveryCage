import unittest
from pathlib import Path
import importlib.util
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).parents[1]


class GeocodeOperatorStatusContractTests(unittest.TestCase):
    def test_usage_comes_from_reservations_not_replayed_result_rows(self):
        spec = importlib.util.spec_from_file_location("operator_status_test",
            ROOT / "scripts/diagnostics/geocode-operator-status.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursors = [MagicMock() for _ in range(6)]
        cursors[0].fetchall.return_value = [("queued", "locationiq", 12)]
        cursors[1].fetchall.return_value = [("DE", 12)]
        cursors[2].fetchall.return_value = [("2026-10-27", "locationiq", 5000)]
        cursors[3].fetchone.return_value = (12,)
        cursors[4].fetchone.return_value = (100,)
        cursors[5].fetchall.return_value = [("2026-10-27","locationiq","secondary",367,5000)]
        connection.execute.side_effect = cursors
        with patch.object(module.psycopg, "connect", return_value=connection):
            report = module.status("postgresql://synthetic", "locationiq")
        self.assertEqual(report["daily_usage"],
                         [{"day": "2026-10-27", "provider": "locationiq", "count": 5000}])
        self.assertIn("geocode_provider_budgets", connection.execute.call_args_list[2].args[0])
        self.assertIn("uec.sources AS source",connection.execute.call_args_list[1].args[0])
        self.assertNotIn("record.country_code",connection.execute.call_args_list[1].args[0])
        self.assertIn("_uec_parent_geocode_result_id", connection.execute.call_args_list[4].args[0])
        self.assertEqual(report["account_usage"][0]["remaining"],4633)
        for call in connection.execute.call_args_list:
            self.assertEqual(call.args[1], ("locationiq",))

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
