import importlib.util
import os
from pathlib import Path
import unittest
import uuid
from unittest.mock import MagicMock, patch

from pipeline.geocoding.accounts import account_for_provider, attribute_history
from pipeline.geocoding.registry import get_adapter

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("account_worker", ROOT / "pipeline/scripts/stages/geocode-worker.py")
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)
ACTIVATION_SPEC = importlib.util.spec_from_file_location("account_activation", ROOT / "pipeline/scripts/stages/activate-locationiq-preview.py")
ACTIVATION = importlib.util.module_from_spec(ACTIVATION_SPEC)
ACTIVATION_SPEC.loader.exec_module(ACTIVATION)


class GeocodeAccountTests(unittest.TestCase):
    def test_account_selection_is_explicit_and_other_providers_unchanged(self):
        self.assertEqual(account_for_provider("locationiq",None),"primary")
        self.assertEqual(account_for_provider("locationiq","secondary"),"secondary")
        self.assertIsNone(account_for_provider("geoapify",None))
        for provider,account in (("locationiq","arbitrary"),("geoapify","secondary")):
            with self.assertRaises(ValueError): account_for_provider(provider,account)

    def test_secondary_account_uses_only_its_own_secret(self):
        with patch.dict(os.environ,{"LOCATIONIQ_API_KEY":"synthetic-primary",
                                    "LOCATIONIQ_SECONDARY_API_KEY":"synthetic-secondary"}):
            self.assertEqual(get_adapter("locationiq",provider_account="secondary",
                private_source_profile_id="locationiq-de-bltu").api_key,"synthetic-secondary")
            self.assertEqual(get_adapter("locationiq",
                private_source_profile_id="locationiq-de-bltu").api_key,"synthetic-primary")
        with patch.dict(os.environ,{"LOCATIONIQ_API_KEY":"synthetic-primary",
                                    "LOCATIONIQ_SECONDARY_API_KEY":""}):
            with self.assertRaises(ValueError):
                get_adapter("locationiq",provider_account="secondary")

    def test_account_reservation_uses_atomic_database_admission(self):
        connection=MagicMock()
        expected=(uuid.uuid4(),None)
        connection.execute.return_value.fetchone.return_value=expected
        job=uuid.uuid4()
        self.assertEqual(WORKER._reserve_request(connection,"locationiq",job,3,1,5000,1.05,
            provider_account="secondary"),expected)
        sql,parameters=connection.execute.call_args.args
        self.assertIn("reserve_geocode_account_request",sql)
        self.assertEqual(parameters,("locationiq","secondary",job,3,1,5000,1.05))

    def test_history_requires_explicit_secondary_worker_mapping(self):
        connection=MagicMock()
        for workers in ((),("same","same")):
            with self.assertRaises(ValueError):
                attribute_history(connection,budget_date="2026-10-27",secondary_workers=workers)
        connection.execute.assert_not_called()

    def test_retry_keeps_attempt_history_and_skips_stale_claims(self):
        connection=MagicMock()
        connection.__enter__.return_value=connection
        job,stale=uuid.uuid4(),uuid.uuid4()
        cursors=[MagicMock() for _ in range(5)]
        cursors[0].fetchone.return_value=(ACTIVATION.DATABASE,)
        cursors[1].fetchall.return_value=[(job,"review_required",2),(stale,"failed",2)]
        cursors[2].fetchone.return_value=("review_required",2)
        cursors[4].fetchone.return_value=("started",3)
        connection.execute.side_effect=cursors
        with patch.object(ACTIVATION.psycopg,"connect",return_value=connection):
            report,jobs=ACTIVATION.requeue_unmatched("synthetic",limit=2,provider_account="secondary")
        self.assertEqual(jobs,(job,))
        self.assertEqual(report["provider_calls"],0)
        selection,parameters=connection.execute.call_args_list[1].args
        self.assertEqual(parameters,("secondary",2))
        self.assertIn("geocode_request_account_attributions",selection)
        self.assertIn("accepted.status='accepted'",selection)
        self.assertEqual(connection.execute.call_args_list[3].args[1][:2],(job,2))


if __name__ == "__main__": unittest.main()
