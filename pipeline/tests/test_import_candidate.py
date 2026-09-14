import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
