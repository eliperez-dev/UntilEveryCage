from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner, RefreshRunnerError
from pipeline.contracts.refresh import AdapterCapabilities, RegisteredAdapter, RefreshRequest, canonical_plan


class FakeAdapter:
    source_id = "fixture.one"
    adapter_version = "test-v1"

    def __init__(self, *, failures: int = 0, rows: bool = False) -> None:
        self.failures, self.calls = failures, 0
        self.rows = rows

    def refresh(self, *, mode, run_dir, artifact, options):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("temporary adapter failure")
        if self.rows:
            return {"records": [{"private": "must not be returned"}]}
        return {"input_rows": 2, "normalized_rows": 2, "quarantined_rows": 0, "mode": mode}


def catalog_for(*adapters: FakeAdapter, statuses=None) -> RefreshCatalog:
    catalog = RefreshCatalog.__new__(RefreshCatalog)
    statuses = statuses or {}
    catalog.sources = {adapter.source_id: {"source_id": adapter.source_id, "adapter_status": statuses.get(adapter.source_id, "implemented_partial")} for adapter in adapters}
    catalog.capabilities = {adapter.source_id: AdapterCapabilities(source_id=adapter.source_id, adapter_version=adapter.adapter_version, schema_version="test-v1", acquisition="fixture", geocoding="disabled", publication="human_gate_required") for adapter in adapters}
    catalog.adapters = {adapter.source_id: RegisteredAdapter(catalog.capabilities[adapter.source_id], adapter) for adapter in adapters}
    return catalog


class RefreshRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output_root = Path(__file__).parents[1] / ".." / "data" / "staging" / ".d2-framework-tests"
        shutil.rmtree(cls.output_root, ignore_errors=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.output_root, ignore_errors=True)

    def output(self, name: str) -> Path:
        path = self.output_root / name
        shutil.rmtree(path, ignore_errors=True)
        return path

    def test_selection_is_deterministic_and_all_eligible_uses_authoritative_status(self):
        one, two = FakeAdapter(), FakeAdapter(); catalog = catalog_for(one, two, statuses={"fixture.two": "reference_only"})
        selected = catalog.select(RefreshRequest(all_eligible=True, mode="live-acquisition"))
        self.assertEqual(selected, ("fixture.one",))
        request = RefreshRequest(source_ids=("fixture.one",), mode="fixture", artifact_paths={"fixture.one": "fixture.csv"})
        first = canonical_plan(request, catalog.select(request), catalog.capabilities)
        second = canonical_plan(request, catalog.select(request), catalog.capabilities)
        self.assertEqual(first, second)
        self.assertEqual(first["run_id"], "refresh-" + first["plan_hash"][:16])

    def test_failure_isolated_and_retry_is_bounded(self):
        good, bad = FakeAdapter(), FakeAdapter(failures=5)
        good.source_id, bad.source_id = "fixture.good", "fixture.bad"
        catalog = catalog_for(good, bad)
        request = RefreshRequest(source_ids=("fixture.good", "fixture.bad"), mode="fixture",
                                 artifact_paths={"fixture.good": "a", "fixture.bad": "b"}, output_root=self.output("retry"), retries=2)
        result = RefreshRunner(catalog).run(request)
        self.assertEqual(result["exit_status"], "failed")
        self.assertEqual(result["counts"]["succeeded"], 1)
        self.assertEqual(bad.calls, 3)

    def test_unsupported_source_is_explicit(self):
        catalog = catalog_for(FakeAdapter())
        catalog.sources["reference.only"] = {"source_id": "reference.only", "adapter_status": "reference_only"}
        catalog.capabilities["reference.only"] = AdapterCapabilities(source_id="reference.only", adapter_version="none", schema_version="none", acquisition="none", geocoding="disabled", publication="human_gate_required")
        result = RefreshRunner(catalog).run(RefreshRequest(source_ids=("reference.only",), mode="live-acquisition", output_root=self.output("unsupported")))
        self.assertEqual(result["counts"]["unsupported"], 1)
        self.assertEqual(result["exit_status"], "failed")

    def test_resume_reuses_completed_source_manifest(self):
        adapter = FakeAdapter(); catalog = catalog_for(adapter)
        output = self.output("resume")
        request = RefreshRequest(source_ids=(adapter.source_id,), mode="live-acquisition", output_root=output)
        first = RefreshRunner(catalog).run(request)
        resumed = RefreshRunner(catalog).run(RefreshRequest(source_ids=(adapter.source_id,), mode="live-acquisition", output_root=output, resume=True))
        self.assertEqual(first["counts"]["succeeded"], 1)
        self.assertEqual(resumed["counts"]["resumed"], 1)
        self.assertEqual(adapter.calls, 1)

    def test_row_bearing_adapter_summary_fails_closed(self):
        adapter = FakeAdapter(rows=True); catalog = catalog_for(adapter)
        result = RefreshRunner(catalog).run(RefreshRequest(source_ids=(adapter.source_id,), mode="live-acquisition", output_root=self.output("rows")))
        self.assertEqual(result["counts"]["failed"], 1)
        self.assertIn("row-bearing", result["results"][0]["attempts"][0]["error"])

    def test_import_requires_loopback(self):
        with self.assertRaises(RefreshRunnerError):
            RefreshRunner(catalog_for(FakeAdapter())).run(RefreshRequest(source_ids=("fixture.one",), mode="live-acquisition", import_candidates=True, database_url="postgresql://db.example/uec"))

    def test_import_is_explicit_and_requires_injected_generic_importer(self):
        catalog = catalog_for(FakeAdapter())
        request = RefreshRequest(source_ids=("fixture.one",), mode="live-acquisition", output_root=self.output("import"), import_candidates=True, database_url="postgresql://127.0.0.1/uec")
        failed = RefreshRunner(catalog).run(request)
        self.assertEqual(failed["counts"]["failed"], 1)
        seen = []
        def importer(run_dir, database_url):
            seen.append((run_dir, database_url))
            return {"status": "imported", "inserted": 2, "release_created": False}
        ok = RefreshRunner(catalog, candidate_importer=importer).run(request)
        self.assertEqual(ok["counts"]["succeeded"], 1)
        self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main()
