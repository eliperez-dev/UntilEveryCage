import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
from pipeline.contracts.refresh import RefreshRequest
from pipeline.geocoding.private_profiles import profile_for_source
from .adapter import CONFIG
from .refresh import RefreshError, _explicitly_restricted_from_address_queue, refresh


ROOT = Path(__file__).parent


class GermanyRefreshTests(unittest.TestCase):
    def test_row_free_acquisition_sidecar_is_verified_and_preserved(self):
        raw = ROOT.parent.parent / "germany" / "fixtures" / "synthetic_bltu.csv"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "capture.json"
            metadata.write_text(json.dumps({"sha256": hashlib.sha256(raw.read_bytes()).hexdigest(), "byte_size": raw.stat().st_size, "final_url": "https://example.invalid/current-bltu.csv", "effective_date": "2026-09-14"}), encoding="utf-8")
            result = refresh(run_dir=root / "run", raw_path=raw, acquisition_metadata_path=metadata, retrieved_at_utc="2026-09-14T00:00:00Z")
            self.assertEqual(result["report"]["publication_eligibility"], "blocked")
            saved = json.loads((root / "run" / "acquisition-metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["final_url"], "https://example.invalid/current-bltu.csv")

    def test_assisted_refresh_is_private_and_repeatable(self):
        raw = ROOT.parent.parent / "germany" / "fixtures" / "synthetic_bltu.csv"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = refresh(run_dir=root / "one", raw_path=raw, retrieved_at_utc="2026-09-14T00:00:00Z")
            second = refresh(run_dir=root / "two", raw_path=raw, retrieved_at_utc="2026-09-14T00:00:00Z")
            self.assertEqual(first["report"]["sha256"], second["report"]["sha256"])
            self.assertEqual(first["report"]["normalized_rows"], 2)
            self.assertEqual(first["report"]["publication_eligibility"], "blocked")
            self.assertFalse(any((root / "one" / "lifecycle").glob("*/released/records.jsonl")))

    def test_live_mode_rejects_guessed_export_url(self):
        with self.assertRaises(RefreshError):
            refresh(run_dir=Path(tempfile.mkdtemp()), fetch=True, export_url="https://example.invalid/export.csv")

    def test_shared_runner_live_hook_emits_candidate_and_privacy_withheld_queue(self):
        raw = ROOT.parent.parent / "germany" / "fixtures" / "synthetic_bltu.csv"
        payload = raw.read_bytes()

        def fake_fetch(*, output_root, run_id, timeout_seconds, max_bytes):
            path = Path(output_root) / run_id / "bltu-general-list.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            return {"source_id": "de.locations", "artifact_path": str(path),
                    "final_url": "https://bltu.bvl.bund.de/public-export.csv",
                    "retrieved_at_utc": "2026-10-25T00:00:00Z", "effective_date": "unknown",
                    "publication_date": None, "sha256": hashlib.sha256(payload).hexdigest(),
                    "byte_size": len(payload), "privacy_caveat": "private"}

        with tempfile.TemporaryDirectory() as directory:
            catalog = RefreshCatalog()
            runner = RefreshRunner(catalog)
            self.assertEqual(type(catalog.adapters["de.locations"].adapter).__name__, "GermanyRefreshAdapter")
            self.assertIsNone(profile_for_source("de.locations"))
            request = RefreshRequest(
                source_ids=("de.locations",), mode="live-acquisition",
                output_root=Path(directory) / "runs", retries=0,
                options={"authorized_live_sources": ["de.locations"],
                         "terms_review_paths": {"de.locations": str(ROOT / "terms-review.json")},
                         "timeout_seconds": 30, "max_bytes": 1024 * 1024,
                         "acquisition_run_id": "mock-de-live"})
            with patch("pipeline.sources.germany.refresh.fetch_bltu", side_effect=fake_fetch):
                result = runner.run(request)
            run_id = result["run_id"]
            source_dir = Path(directory) / "runs" / run_id / "sources" / "de.locations"
            self.assertEqual(result["exit_status"], "ok")
            handoff = json.loads((source_dir / "candidate-handoff" / "manifest.json").read_text())
            self.assertEqual(handoff["source_url"], CONFIG["source_url"])
            self.assertNotIn("?", handoff["source_url"])
            queue = json.loads((source_dir / "geocode-queue" / "geocode-queue-metadata.json").read_text())
            self.assertEqual(queue["records_seen"], queue["records_eligible_for_local_queue"]
                             + queue["records_withheld_explicit_restriction"])
            self.assertGreater(queue["records_queued"], 0)
            self.assertEqual(queue["records_withheld_explicit_restriction"], 0)
            self.assertEqual(queue["provider_review_state"], "not_configured")
            self.assertFalse(queue["durable_db_jobs"])
            self.assertFalse(queue["external_provider_called"])

    def test_pending_publication_review_is_not_an_explicit_queue_restriction(self):
        self.assertFalse(_explicitly_restricted_from_address_queue({
            "normalized": {"privacy_gate": "pending-review", "address_state": "source-present-pending-privacy-review"}}))
        self.assertTrue(_explicitly_restricted_from_address_queue({
            "normalized": {"privacy_gate": "restricted-withheld-address"}}))
        self.assertTrue(_explicitly_restricted_from_address_queue({
            "normalized": {"source_address_restricted": True}}))


if __name__ == "__main__":
    unittest.main()
