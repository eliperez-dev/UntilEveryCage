"""Synthetic checks for the private UK provider and independent SQL boundary."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from pipeline.geocoding.private_profiles import profile_for_source

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "uk_contract_worker", ROOT / "pipeline/scripts/stages/geocode-worker.py")
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)


class UkLocationIqContractTests(unittest.TestCase):
    def test_profiles_are_explicit_and_private(self):
        for source, suffix in (("fsa_approved_establishments", "fsa"),
                               ("fss_approved_establishments", "fss")):
            profile = profile_for_source(source, provider_id="locationiq")
            self.assertEqual(profile["profile_id"], f"locationiq-gb-{suffix}-approved-establishments")
            self.assertEqual(profile["country_code"], "GB")
            self.assertEqual(profile["status"], "enabled-private-only")

    def test_worker_keeps_account_rate_and_finite_batch_guards(self):
        profile = "locationiq-gb-fsa-approved-establishments"
        with patch.object(WORKER, "get_adapter"), patch.object(
                WORKER.psycopg, "connect", side_effect=RuntimeError("synthetic database")) as connect:
            with self.assertRaisesRegex(RuntimeError, "synthetic database"):
                WORKER.run("postgresql://synthetic", "locationiq", 1, 0, 1,
                           private_source_profile_id=profile, daily_budget=5000,
                           provider_interval=1.05, provider_account="secondary")
            connect.assert_called_once()
        for limit, budget, interval in ((None, 5000, 1.05), (5001, 5000, 1.05),
                                        (1, 5001, 1.05), (1, 5000, 0.5)):
            with patch.object(WORKER.psycopg, "connect") as connect:
                with self.assertRaises(ValueError):
                    WORKER.run("postgresql://synthetic", "locationiq", limit, 0, 1,
                               private_source_profile_id=profile, daily_budget=budget,
                               provider_interval=interval)
                connect.assert_not_called()

    def test_sql_reconstructs_query_and_requires_latest_source_and_audit(self):
        sql = (ROOT / "pipeline/migrations/104_uk_locationiq_private_enrichment.sql").read_text()
        for fragment in (
            "locationiq_uk_source_query(location.location_evidence)=NEW.query",
            "candidate.snapshot_sha256=target.snapshot_sha256",
            "ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1",
            "NOT EXISTS (SELECT 1 FROM uec.public_access_restricted",
            "NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events",
            "jsonb_array_elements(NEW.response->'results')",
            "viable<>1", "context_count<>1", "uk_locationiq_context_audit",
            "ST_Y(NEW.result::geometry)<>(selected->>'lat')::DOUBLE PRECISION",
            "ST_X(NEW.result::geometry)<>(selected->>'lon')::DOUBLE PRECISION",
            "latitude BETWEEN 49.8 AND 60.9", "longitude BETWEEN -8.7 AND 2.0",
            "coalesce(location->>'country_code','') <> 'GB'",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, sql)
        self.assertNotRegex(sql, r"(?im)^\s*(UPDATE|DELETE|TRUNCATE)\s+real_preview\.(?:candidates|geocode_display_evidence)")


if __name__ == "__main__":
    unittest.main()
