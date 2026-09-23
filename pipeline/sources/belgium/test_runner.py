import json
import tempfile
import unittest
from pathlib import Path

from pipeline.common.refresh_runner import RefreshCatalog
from pipeline.contracts.refresh import RefreshRequest
from pipeline.sources.first_wave import FirstWaveRefreshAdapter, descriptor_for


class BelgiumRunnerTests(unittest.TestCase):
    def test_source_is_registered_live_but_still_publication_gated(self):
        catalog = RefreshCatalog()
        registered = catalog.adapters["be.locations"]
        self.assertTrue(registered.capabilities.live_callable)
        self.assertEqual(registered.capabilities.acquisition, "bounded_private_fetch")
        self.assertEqual(registered.capabilities.publication, "human_gate_required")
        self.assertTrue(callable(getattr(registered.adapter, "acquire", None)))

    def test_fixture_runner_emits_only_scoped_minimized_candidate_rows_repeatably(self):
        adapter = FirstWaveRefreshAdapter(descriptor_for("be.locations"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = adapter.refresh(mode="fixture", run_dir=root / "one", artifact=None, options={})
            second = adapter.refresh(mode="fixture", run_dir=root / "two", artifact=None, options={})
            one = json.loads((root / "one" / "candidate-handoff" / "manifest.json").read_text(encoding="utf-8"))
            two = json.loads((root / "two" / "candidate-handoff" / "manifest.json").read_text(encoding="utf-8"))
            rows = [json.loads(line) for line in (root / "one" / "candidate-handoff" / "normalized" / "records.jsonl").read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(first["deduplicated_source_scoped_facility_candidates"], 3)
        self.assertEqual(first["candidate_observation_rows"], 3)
        self.assertEqual(one["normalized_sha256"], two["normalized_sha256"])
        self.assertTrue(all(row["normalized"]["activity_categories"] for row in rows))
        self.assertTrue(all(not row["source_values"] for row in rows))
        self.assertTrue(all("name" not in row["normalized"] and "postcode" not in row["normalized"] for row in rows))
        self.assertEqual(first["publication_state"], "private-only; not public-release-ready")
        self.assertEqual(first["public_surfaces"], {"api": False, "map": False, "csv": False})

    def test_live_runner_does_not_acquire_without_source_grant_and_terms_record(self):
        catalog = RefreshCatalog()
        with tempfile.TemporaryDirectory() as directory:
            request = RefreshRequest(source_ids=("be.locations",), mode="live-acquisition", output_root=Path(directory))
            result = __import__("pipeline.common.refresh_runner", fromlist=["RefreshRunner"]).RefreshRunner(catalog).run(request)
        self.assertEqual(result["results"][0]["acquisition_classification"], "terms-blocked")
        self.assertEqual(result["results"][0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
