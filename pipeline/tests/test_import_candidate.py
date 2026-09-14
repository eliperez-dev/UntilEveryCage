import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.sources.uk.fsa_approved.adapter import FsaApprovedEstablishmentsAdapter

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("import_candidate", ROOT / "scripts/maintenance/import-candidate.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CandidateImportContractTests(unittest.TestCase):
    def test_server_marker_is_required_even_after_cli_acknowledgement(self):
        class FakeConnection:
            def execute(self, *_args):
                class Result:
                    def fetchone(self):
                        return None
                return Result()
        with self.assertRaises(MODULE.CandidateImportError):
            MODULE.verify_disposable_marker(FakeConnection())

        class MarkedConnection(FakeConnection):
            def execute(self, *_args):
                class Result:
                    def fetchone(self):
                        return (MODULE.DISPOSABLE_MARKER,)
                return Result()
        MODULE.verify_disposable_marker(MarkedConnection())

    def test_database_guard_requires_explicit_non_default_loopback_target(self):
        for url, acknowledged in [
            ("postgresql://uec:x@db.example:5433/uec", True),
            ("postgresql://uec:x@127.0.0.1:5432/uec", True),
            ("postgresql://uec:x@127.0.0.1:5433/uec", False),
        ]:
            with self.subTest(url=url, acknowledged=acknowledged):
                with self.assertRaises(MODULE.CandidateImportError):
                    MODULE.require_disposable_database(url, acknowledged)
        MODULE.require_disposable_database("postgresql://uec:x@127.0.0.1:5433/uec", True)

    def test_manifest_and_normalized_hash_and_state_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            normalized = root / "records.jsonl"
            normalized.write_text(json.dumps({"source_id": "test", "source_row": 2, "normalized": {"establishment_id": "A"}}) + "\n", encoding="utf-8")
            manifest = {
                "source_id": "test", "source_url": "https://example.invalid/source",
                "retrieved_at_utc": "2026-09-13T00:00:00Z", "checksum_sha256": "0" * 64,
                "byte_size": 1, "normalized_rows": 1,
                "normalized_sha256": hashlib.sha256(normalized.read_bytes()).hexdigest(),
                "release_state": "not-created", "publication_state": "private-candidate",
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            raw = root / "raw.bin"
            raw.write_bytes(b"raw fixture")
            manifest["checksum_sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
            manifest["byte_size"] = raw.stat().st_size
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            loaded, rows = MODULE.load_inputs(manifest_path, normalized, raw)
            self.assertEqual(loaded["source_id"], "test")
            self.assertEqual(len(rows), 1)
            manifest["release_state"] = "promoted"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(MODULE.CandidateImportError):
                MODULE.load_inputs(manifest_path, normalized, raw)

    def test_raw_artifact_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.bin"; raw.write_bytes(b"actual")
            normalized = root / "records.jsonl"; normalized.write_text("", encoding="utf-8")
            manifest = {"source_id":"test", "source_url":"https://example.invalid", "retrieved_at_utc":"2026-09-13T00:00:00Z", "checksum_sha256":"0"*64, "byte_size":6, "normalized_rows":0, "normalized_sha256":hashlib.sha256(b"").hexdigest(), "release_state":"not-created", "publication_state":"private-candidate"}
            path = root / "manifest.json"; path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(MODULE.CandidateImportError):
                MODULE.load_inputs(path, normalized, raw)

    def test_uk_handoff_output_composes_with_importer_without_database(self):
        """Exercise the real UK adapter output through the import preflight."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "uk-monthly.csv"
            raw.write_bytes(
                b"AppNo,TradingName,Country,CompetentAuthority,X,Y,AddressWithheld,All_Activities,Address1,Town,Postcode\n"
                b"UK-E2E-1,Example Foods,England,Food Standards Agency,-0.12,51.50,No,CP,House Farm,London,SW1\n"
            )
            run_dir = root / "run"
            raw_hash = hashlib.sha256(raw.read_bytes()).hexdigest()
            artifact = {
                "source_url": "https://example.invalid/uk-synthetic.csv",
                "retrieved_at_utc": "2026-09-13T00:00:00Z",
                "checksum_sha256": raw_hash,
                "byte_size": raw.stat().st_size,
                "code_version": "test",
                "config_version": "test",
            }
            manifest = FsaApprovedEstablishmentsAdapter().run(raw, run_dir, artifact)
            loaded, rows = MODULE.load_inputs(run_dir / "manifest.json", run_dir / "normalized/records.jsonl", raw)
            self.assertEqual(loaded, manifest)
            self.assertEqual(len(rows), 1)
            self.assertTrue(all(row["normalized"]["coordinates"] is None for row in rows))
            self.assertEqual(rows[0]["normalized"]["privacy_gate"], "privacy-review-required")
            self.assertEqual(rows[0]["normalized"]["coordinate_gate"], "privacy-review-required")
            self.assertEqual(rows[0]["normalized"]["publication_gate"], "blocked")
            self.assertTrue(all(MODULE._record_parts(row)[0] for row in rows))
            self.assertEqual(manifest["release_state"], "not-created")
            self.assertEqual(manifest["publication_state"], "private-candidate")


if __name__ == "__main__":
    unittest.main()
