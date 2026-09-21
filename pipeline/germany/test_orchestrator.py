#!/usr/bin/env python3
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

try:
    from .orchestrator import register_input, run_registered_input
except ImportError:
    from orchestrator import register_input, run_registered_input


ROOT = Path(__file__).parent
FIXTURE = ROOT / "fixtures" / "synthetic_source.csv"
CONFIG = {
    "source_url": "https://example.invalid/synthetic-germany.csv",
    "retrieval_timestamp": "2026-09-13T00:00:00Z",
    "source_publication_date": "2026-09-12",
}


class OrchestratorTests(unittest.TestCase):
    def test_identical_bytes_share_raw_artifact_but_keep_distinct_acquisition_events(self):
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory)
            raw = FIXTURE.read_bytes()
            first_path, first = register_input(raw, staging, CONFIG)
            first_manifest_path = Path(first["acquisition_manifest"])
            first_manifest_bytes = first_manifest_path.read_bytes()
            later_observation = {**CONFIG, "retrieval_timestamp": "2026-09-14T00:00:00Z"}
            second_path, second = register_input(raw, staging, later_observation)
            second_manifest_path = Path(second["acquisition_manifest"])

            self.assertEqual(first_path, second_path)
            self.assertEqual(first_path.name, f"{hashlib.sha256(raw).hexdigest()}.artifact")
            self.assertEqual(first_path.read_bytes(), raw)
            self.assertEqual(len(list((staging / "raw").glob("*.artifact"))), 1)
            self.assertEqual(first["raw_artifact"], str(first_path))
            self.assertEqual(second["raw_artifact"], str(first_path))
            self.assertEqual(first["checksum_sha256"], second["checksum_sha256"])
            self.assertEqual(first["byte_size"], second["byte_size"])

            self.assertNotEqual(first_manifest_path, second_manifest_path)
            self.assertEqual(len(list((staging / "raw" / "registrations").glob("*.manifest.json"))), 2)
            self.assertEqual(first_manifest_path.read_bytes(), first_manifest_bytes)
            self.assertEqual(json.loads(first_manifest_bytes), first)
            self.assertEqual(json.loads(second_manifest_path.read_text(encoding="utf-8")), second)
            self.assertEqual(first["retrieval_timestamp"], CONFIG["retrieval_timestamp"])
            self.assertEqual(second["retrieval_timestamp"], later_observation["retrieval_timestamp"])
            self.assertEqual(first["source_url"], CONFIG["source_url"])
            self.assertEqual(first["source_publication_date"], CONFIG["source_publication_date"])

    def test_suppression_survives_rerun_and_candidate_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_path, _ = register_input(FIXTURE.read_bytes(), root, CONFIG)
            prior = {"release_id": "de-release-previous", "eligible": True}
            suppressed = {"DE-SYN-002"}
            first = run_registered_input(raw_path, root / "runs-one", CONFIG, prior, suppressed)
            second = run_registered_input(raw_path, root / "runs-two", CONFIG, prior, suppressed)
            self.assertEqual(first["status"], "candidate-ready")
            self.assertEqual(first["publication_state"], "human-gate-required")
            self.assertFalse(first["release_promoted"])
            for run_root in (root / "runs-one", root / "runs-two"):
                run_dir = next(run_root.iterdir())
                rows = [json.loads(line) for line in (run_dir / "release-candidate" / "records.jsonl").read_text().splitlines()]
                self.assertNotIn("DE-SYN-002", {row["source_id"] for row in rows})
            self.assertEqual(first["manifest"], second["manifest"])

    def test_failure_preserves_prior_reference_and_emits_no_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad = root / "bad.csv"
            bad.write_text("source_id,name\nBROKEN,row\n", encoding="utf-8")
            prior = {"release_id": "de-release-previous", "eligible": True}
            result = run_registered_input(bad, root / "runs", CONFIG, prior)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["publication_state"], "unchanged")
            self.assertEqual(result["prior_eligible_release"], prior)
            run_dir = next((root / "runs").iterdir())
            self.assertFalse((run_dir / "release-candidate").exists())

    def test_pending_terms_can_stage_but_cannot_create_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_path, _ = register_input(FIXTURE.read_bytes(), root, CONFIG)
            restricted = {**CONFIG, "terms_status": "pending_confirmation", "acquisition_status": "restricted_pending_terms"}
            result = run_registered_input(raw_path, root / "runs", restricted)
            self.assertEqual(result["status"], "staged-restricted")
            self.assertFalse(result["candidate_created"])
            self.assertEqual(result["geocoding"], "disabled")
            self.assertEqual(set(result["public_surfaces"]), {"api", "map", "export", "cache", "history"})
            self.assertFalse(any(result["public_surfaces"].values()))
            run_dir = next((root / "runs").iterdir())
            self.assertFalse((run_dir / "release-candidate").exists())
            self.assertFalse((run_dir / "released" / "records.jsonl").exists())

    def test_pending_terms_alone_blocks_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_path, _ = register_input(FIXTURE.read_bytes(), root, CONFIG)
            result = run_registered_input(raw_path, root / "runs", {**CONFIG, "terms_status": "pending_confirmation"})
            self.assertEqual(result["status"], "staged-restricted")
            self.assertFalse(result["candidate_created"])
            self.assertFalse(any(result["public_surfaces"].values()))
            self.assertFalse((next((root / "runs").iterdir()) / "release-candidate").exists())


if __name__ == "__main__":
    unittest.main()
