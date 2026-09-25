import unittest

from .refresh import row_free_summary, validate_refresh_adapter


class RefreshAdapterContractTests(unittest.TestCase):
    def test_minimal_refresh_hook_is_valid_without_live_acquisition(self):
        class SyntheticRefreshAdapter:
            source_id = "test.synthetic"
            adapter_version = "synthetic-v1"

            def refresh(self, *, mode, run_dir, artifact, options):
                return {"input_rows": 1, "normalized_rows": 1, "quarantined_rows": 0}

        adapter = SyntheticRefreshAdapter()
        validate_refresh_adapter(adapter)
        self.assertEqual(adapter.refresh(mode="fixture", run_dir=None, artifact=None, options={})["input_rows"], 1)

    def test_live_acquisition_is_optional_but_must_be_callable(self):
        class InvalidRefreshAdapter:
            source_id = "test.synthetic"
            adapter_version = "synthetic-v1"
            refresh = object()
            acquire = object()

        with self.assertRaisesRegex(ValueError, "callable refresh"):
            validate_refresh_adapter(InvalidRefreshAdapter())

    def test_refresh_result_is_aggregate_only(self):
        with self.assertRaisesRegex(ValueError, "row-bearing key"):
            row_free_summary({"input_rows": 1, "records": [{"name": "synthetic"}]})


if __name__ == "__main__":
    unittest.main()
