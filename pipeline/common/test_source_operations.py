import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from .acquisition import AcquisitionError
from .source_operations import (
    RetryPolicy,
    SourceOperationsError,
    SourceSchedule,
    build_source_health_index,
    classify_failure,
    finalize_run_operations,
    freshness_for,
    load_source_schedules,
    read_run_history,
    register_deduplicated_artifact,
    run_with_bounded_retries,
)


class SourceOperationsTests(unittest.TestCase):
    def test_checked_in_schedule_inventory_matches_registry(self):
        root = Path(__file__).parents[1]
        schedules = load_source_schedules(registry_path=root / "source_registry.json")
        self.assertEqual(len(schedules), 38)
        self.assertEqual(schedules["dk.smiley"].stale_after_hours, 240)
        self.assertEqual(schedules["fr.dgal.section-i"].interval_hours, 24)
        self.assertIsNone(schedules["us.fsis"].interval_hours)

    def test_schedule_validation_rejects_missing_and_inverted_freshness(self):
        with self.assertRaisesRegex(SourceOperationsError, "missing fields"):
            SourceSchedule.from_mapping({"source_id": "x"})
        with self.assertRaisesRegex(SourceOperationsError, "must cover"):
            SourceSchedule("x", "daily", 24, 12)

    def test_freshness_is_explicit_for_unknown_and_stale_schedules(self):
        unknown = SourceSchedule("x", "unknown", None, None)
        self.assertEqual(freshness_for(unknown, "2026-01-01T00:00:00Z", as_of_utc="2026-09-15T00:00:00Z")["state"], "unknown")
        weekly = SourceSchedule("x", "weekly", 168, 240)
        fresh = freshness_for(weekly, "2026-09-07T00:00:00Z", as_of_utc="2026-09-15T00:00:00Z")
        self.assertEqual(fresh["state"], "current")
        self.assertTrue(fresh["due"])
        self.assertEqual(freshness_for(weekly, "2026-09-01T00:00:00Z", as_of_utc="2026-09-15T00:00:00Z")["state"], "stale")

    def test_retries_are_bounded_and_classified(self):
        calls = []

        def operation():
            calls.append(len(calls) + 1)
            raise AcquisitionError("temporary", failure_class="network", retryable=True, action="retry")

        with self.assertRaisesRegex(RuntimeError, "bounded attempt") as raised:
            run_with_bounded_retries(operation, RetryPolicy(max_attempts=3), sleep=lambda _: None)
        self.assertEqual(calls, [1, 2, 3])
        self.assertEqual(len(raised.exception.attempts), 3)
        self.assertEqual(classify_failure(raised.exception)["failure_class"], "retry-exhausted")

    def test_deduplicated_artifacts_keep_distinct_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = register_deduplicated_artifact(b"same", root, {"source_id": "x", "retrieved_at_utc": "one"})
            second = register_deduplicated_artifact(b"same", root, {"source_id": "x", "retrieved_at_utc": "two"})
            self.assertEqual(first["artifact_path"], second["artifact_path"])
            self.assertEqual(first["artifact_state"], "stored")
            self.assertEqual(second["artifact_state"], "deduplicated")
            self.assertNotEqual(first["observation_id"], second["observation_id"])
            self.assertEqual(len(list((root / "raw/sha256").glob("**/artifact"))), 1)
            self.assertFalse(json.loads(Path(second["observation_path"]).read_text())["retention"]["public_exposure"])

    def _write_run(self, root: Path, name: str, raw: bytes = b"raw") -> tuple[Path, dict]:
        run = root / "runs" / name
        (run / "normalized").mkdir(parents=True)
        (run / "normalized/records.jsonl").write_text(json.dumps({"normalized": {"establishment_id": "A"}}) + "\n", encoding="utf-8")
        manifest = {
            "source_id": "dk.smiley", "source_url": "https://example.test/dk", "retrieved_at_utc": "2026-09-15T00:00:00Z",
            "checksum_sha256": hashlib.sha256(raw).hexdigest(), "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
            "code_version": "test", "config_version": "test", "input_rows": 1, "normalized_rows": 1, "quarantined_rows": 0,
            "schema_fingerprint": "schema-1", "release_state": "not-created", "publication_state": "private-candidate",
        }
        (run / "manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        (run / "qa.json").write_text(json.dumps({"source_id": "dk.smiley", "input_rows": 1, "normalized_rows": 1, "quarantined_rows": 0, "drift_alarms": []}), encoding="utf-8")
        return run, manifest

    def test_history_diff_packet_and_unchanged_rerun_are_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, manifest = self._write_run(root, "first")
            first_status = finalize_run_operations(root, first, manifest=manifest, status={"status": "candidate-ready", "publication_state": "human-gate-required"}, config={"source_id": "dk.smiley"})
            self.assertEqual(first_status["run_classification"], "changed")
            self.assertTrue(first_status["release_preserved"])
            second, manifest2 = self._write_run(root, "second")
            second_status = finalize_run_operations(root, second, manifest=manifest2, status={"status": "candidate-ready", "publication_state": "human-gate-required"}, config={"source_id": "dk.smiley"})
            self.assertEqual(second_status["run_classification"], "unchanged")
            packet = json.loads((second / "review-packet.json").read_text())
            self.assertFalse(packet["release_promotion_allowed"])
            self.assertNotIn("establishment_id", json.dumps(packet))
            history = read_run_history(root, "dk.smiley")
            self.assertEqual([item["run_classification"] for item in history], ["changed", "unchanged"])
            self.assertEqual((second / "release-diff.json").read_bytes(), (second / "release-diff.json").read_bytes())

    def test_failed_run_keeps_prior_release_reference_and_health_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, manifest = self._write_run(root, "first")
            finalize_run_operations(root, first, manifest=manifest, status={"status": "candidate-ready", "publication_state": "human-gate-required"}, config={"source_id": "dk.smiley"})
            failed = root / "runs/failed"
            failed.mkdir(parents=True)
            status = finalize_run_operations(root, failed, manifest=None, status={"status": "failed", "error": "schema drift at secret address", "publication_state": "unchanged"}, config={"source_id": "dk.smiley", "manual_fallback": "operator capture"}, prior_eligible_release={"release_id": "validated-1"})
            self.assertEqual(status["run_classification"], "failed")
            self.assertTrue(status["release_preserved"])
            report = json.loads((failed / "failure-report.json").read_text())
            self.assertFalse(report["public_exposure"])
            self.assertNotIn("secret address", json.dumps(report))
            index = build_source_health_index(root, registry_path=Path(__file__).parents[1] / "source_registry.json", as_of_utc="2026-09-15T00:00:00Z")
            source = next(item for item in index["sources"] if item["source_id"] == "dk.smiley")
            self.assertEqual(source["health_state"], "failed")
            self.assertFalse(source["public_exposure"])


if __name__ == "__main__":
    unittest.main()
