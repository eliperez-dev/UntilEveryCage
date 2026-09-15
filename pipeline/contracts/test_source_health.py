import json
import tempfile
import unittest
from pathlib import Path

from .source_health import HealthEvidenceError, build_health_snapshot, write_health_snapshot


class SourceHealthTests(unittest.TestCase):
    def write_run(self, root: Path, source_id: str, *, drift=None, retrieved="2026-09-14T00:00:00Z", status="success") -> Path:
        run = root / source_id
        run.mkdir()
        manifest = {
            "source_id": source_id,
            "source_url": f"https://example.test/{source_id}",
            "retrieved_at_utc": retrieved,
            "effective_date": None,
            "checksum_sha256": "a" * 64,
            "byte_size": 12,
            "code_version": "test",
            "config_version": "test",
            "input_rows": 4,
            "normalized_rows": 3,
            "quarantined_rows": 1,
            "release_state": "not-created",
            "publication_state": "private-candidate",
        }
        qa = {
            "source_id": source_id,
            "input_rows": 4,
            "normalized_rows": 3,
            "quarantined_rows": 1,
            "drift_alarms": drift or [],
            "disappeared_not_observed_count": 2,
        }
        run_status = {
            "status": status,
            "publication_state": "human-gate-required",
            "release_promoted": False,
        }
        for name, value in (("manifest.json", manifest), ("qa.json", qa), ("run-status.json", run_status)):
            (run / name).write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        return run

    def import_evidence(self, root: Path, source_id: str) -> Path:
        path = root / f"{source_id}-import.json"
        path.write_text(json.dumps({
            "source_id": source_id,
            "status": "resumed",
            "imported_rows": 3,
            "rerun_imported_rows": 0,
            "default_visible_rows": 0,
            "publication_eligible_rows": 0,
            "public_exposure": False,
        }), encoding="utf-8")
        return path

    def test_uk_denmark_italy_snapshots_are_conservative_and_row_free(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for source_id in ("uk.locations", "dk.smiley", "it.853-2004"):
                run = self.write_run(root, source_id)
                snapshot = build_health_snapshot(
                    run, as_of_utc="2026-09-15T00:00:00Z", import_evidence_path=self.import_evidence(root, source_id)
                )
                self.assertEqual(snapshot["health_state"], "private-validated")
                self.assertTrue(snapshot["private_validation"])
                self.assertFalse(snapshot["public_exposure"])
                self.assertEqual(snapshot["publication_eligibility"], "blocked")
                self.assertEqual(snapshot["run"]["disappearance_semantics"], "not-observed; never inferred as closure")
                self.assertEqual(snapshot["import"]["rerun_imported_rows"], 0)
                self.assertNotIn("source_values", json.dumps(snapshot))
                self.assertNotIn("address", json.dumps(snapshot))

    def test_drift_and_stale_evidence_degrade_without_false_health(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.write_run(Path(directory), "dk.smiley", drift=["count_drift"])
            snapshot = build_health_snapshot(run, as_of_utc="2026-09-20T00:00:00Z", stale_after_hours=24)
            self.assertEqual(snapshot["health_state"], "degraded")
            self.assertEqual(snapshot["freshness"]["state"], "stale")

    def test_missing_evidence_and_privacy_leak_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self.write_run(root, "it.853-2004")
            (run / "qa.json").unlink()
            with self.assertRaisesRegex(HealthEvidenceError, "missing QA"):
                build_health_snapshot(run, as_of_utc="2026-09-15T00:00:00Z")
            run = self.write_run(root, "it.853-2004-leak")
            qa = json.loads((run / "qa.json").read_text())
            qa["source_values"] = {"private": "never include"}
            (run / "qa.json").write_text(json.dumps(qa), encoding="utf-8")
            with self.assertRaisesRegex(HealthEvidenceError, "prohibited payload"):
                build_health_snapshot(run, as_of_utc="2026-09-15T00:00:00Z")

    def test_failed_and_partial_runs_never_look_publishable(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.write_run(Path(directory), "uk.locations", status="failed")
            snapshot = build_health_snapshot(run, as_of_utc="2026-09-15T00:00:00Z")
            self.assertEqual(snapshot["health_state"], "failed")
            self.assertFalse(snapshot["public_exposure"])
            self.assertEqual(snapshot["publication_eligibility"], "blocked")

    def test_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self.write_run(root, "dk.smiley")
            snapshot = build_health_snapshot(run, as_of_utc="2026-09-15T00:00:00Z")
            first, second = root / "one.json", root / "two.json"
            write_health_snapshot(first, snapshot)
            write_health_snapshot(second, snapshot)
            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
