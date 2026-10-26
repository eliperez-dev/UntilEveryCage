import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import uuid

from pipeline.geocoding.base import GeocodeOutcome
from pipeline.geocoding.private_profiles import profile_by_id, profile_for_source
from pipeline.geocoding.registry import get_adapter

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("locationiq_worker_test", ROOT / "pipeline/scripts/stages/geocode-worker.py")
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)
ACTIVATION_SPEC = importlib.util.spec_from_file_location(
    "locationiq_activation_unit_test", ROOT / "pipeline/scripts/stages/activate-locationiq-preview.py")
ACTIVATION = importlib.util.module_from_spec(ACTIVATION_SPEC)
ACTIVATION_SPEC.loader.exec_module(ACTIVATION)


class LocationIqIntegrationTests(unittest.TestCase):
    def test_activation_cohort_is_validated_before_database_access(self):
        with patch.object(ACTIVATION.psycopg, "connect") as connect:
            with self.assertRaises(ValueError):
                ACTIVATION.activate("postgresql://synthetic", cohort="retry-everything")
        connect.assert_not_called()

    def test_activation_filters_previous_provider_results_without_reusing_locationiq_targets(self):
        for cohort, expected in (("all", None), ("unqueried", False),
                                 ("previous-provider-unmapped", True)):
            connection = Mock()
            connection.__enter__ = Mock(return_value=connection)
            connection.__exit__ = Mock(return_value=False)
            connection.transaction.return_value.__enter__ = Mock()
            connection.transaction.return_value.__exit__ = Mock(return_value=False)
            connection.execute.side_effect = [Mock(fetchone=lambda: (ACTIVATION.DATABASE,)),
                                              Mock(fetchone=lambda: (True,)),
                                              Mock(fetchall=lambda: [])]
            with self.subTest(cohort=cohort), patch.object(
                    ACTIVATION.psycopg, "connect", return_value=connection):
                summary, jobs = ACTIVATION.activate("postgresql://synthetic", limit=100, cohort=cohort)
            sql, params = connection.execute.call_args.args
            self.assertEqual(params, (expected, expected, 100))
            self.assertIn("candidate.display_latitude IS NULL", sql)
            self.assertIn("job.provider_id='locationiq'", sql)
            self.assertIn("result.provider_id='geoapify') = %s::boolean", sql)
            self.assertEqual(summary["cohort"], cohort)
            self.assertEqual(summary["provider_calls"], 0)
            self.assertEqual(jobs, ())

    def test_provider_profiles_remain_distinct_and_import_default_is_unchanged(self):
        self.assertEqual(profile_for_source("de.locations")["profile_id"], "geoapify-de-bltu")
        self.assertEqual(profile_for_source("de.locations", provider_id="locationiq")["profile_id"], "locationiq-de-bltu")
        with patch.dict("os.environ", {"LOCATIONIQ_API_KEY":"synthetic-key"}):
            adapter = get_adapter("locationiq", private_source_profile_id="locationiq-de-bltu")
        self.assertEqual(adapter.country_code, "de")
        for provider, profile in (("geoapify","locationiq-de-bltu"),("locationiq","geoapify-de-bltu")):
            with self.assertRaises(ValueError):
                get_adapter(provider, private_source_profile_id=profile)
        self.assertIsNone(profile_for_source("es.locations", provider_id="locationiq"))
        self.assertEqual(profile_by_id("geoapify-es-aesan-rgseaa")["source_id"], "es.locations")

    def test_locationiq_requires_explicit_source_finite_batch_and_shared_free_tier_limits(self):
        valid = {"private_source_profile_id":"locationiq-de-bltu","daily_budget":5000,"provider_interval":1.05}
        for override in ({"private_source_profile_id":None},{"daily_budget":5001},{"provider_interval":1},
                         {"limit":None},{"limit":5001}):
            options = {**valid,"limit":24,**override}
            with self.subTest(override=override), self.assertRaises(ValueError), patch.object(WORKER.psycopg,"connect") as connect:
                WORKER.run("postgresql://synthetic","locationiq",options.pop("limit"),0,1,**options)
            connect.assert_not_called()

    def test_primary_resume_skips_current_address_points_from_another_provider(self):
        source = (ROOT / "pipeline/scripts/stages/geocode-worker.py").read_text(encoding="utf-8")
        self.assertIn("result.status='accepted' AND result.provider_id<>job.provider_id",source)
        self.assertIn("evidence.display_precision='provider_address_point_high_confidence'",source)
        self.assertIn("evidence.display_geometry_source=candidate.display_geometry_source",source)

    def test_authentication_or_provider_limit_stops_the_batch(self):
        for acceptance in ("authentication_rejected","provider_rate_limited"):
            connection = Mock()
            connection.__enter__ = Mock(return_value=connection)
            connection.__exit__ = Mock(return_value=False)
            job = (uuid.uuid4(),uuid.uuid4(),"Synthetic Street 1, 12345, Berlin, Germany",2,uuid.uuid4(),"queued")
            adapter = Mock()
            adapter.geocode.return_value = GeocodeOutcome("failed",acceptance,None,None,None,None,
                                                        "locationiq_forward",acceptance=="provider_rate_limited",{"error":acceptance})
            with patch.object(WORKER.psycopg,"connect",return_value=connection), \
                 patch.object(WORKER,"get_adapter",return_value=adapter), \
                 patch.object(WORKER,"_claim_job",side_effect=[job,job]) as claim, \
                 patch.object(WORKER,"_is_restricted",return_value=False), \
                 patch.object(WORKER,"_reserve_request",return_value=(uuid.uuid4(),None)), \
                 patch.object(WORKER,"_persist_outcome",return_value="failed"):
                self.assertEqual(WORKER.run("postgresql://synthetic","locationiq",24,0,1,
                    daily_budget=5000,provider_interval=1.05,private_source_profile_id="locationiq-de-bltu"),1)
            self.assertEqual(claim.call_count,1)
            self.assertEqual(adapter.geocode.call_count,1)


if __name__ == "__main__":
    unittest.main()
