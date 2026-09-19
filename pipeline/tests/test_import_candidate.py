import importlib.util
import hashlib
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from pipeline.sources.uk.fsa_approved.adapter import FsaApprovedEstablishmentsAdapter

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("import_candidate", ROOT / "scripts/maintenance/import-candidate.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CandidateImportContractTests(unittest.TestCase):
    def test_post_commit_interruption_observer_resumes_without_duplicate_rows(self):
        class Result:
            def __init__(self, row=None):
                self.row = row

            def fetchone(self):
                return self.row

        class Transaction:
            def __init__(self, connection):
                self.connection = connection

            def __enter__(self):
                self.connection.transaction_depth += 1
                return self

            def __exit__(self, exc_type, *_args):
                self.connection.transaction_events.append(exc_type is not None)
                self.connection.transaction_depth -= 1
                return False

        class Connection:
            def __init__(self):
                self.transaction_depth = 0
                self.transaction_events = []
                self.records = {}
                self.observations = {}
                self.artifact_id = uuid.uuid4()
                self.run_id = uuid.uuid4()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def commit(self):
                pass

            def transaction(self):
                return Transaction(self)

            def execute(self, query, params=None):
                compact = " ".join(query.split())
                if "FROM uec.disposable_import_guard" in compact:
                    return Result((MODULE.DISPOSABLE_MARKER,))
                if compact.startswith("SELECT artifact_id FROM uec.raw_artifacts"):
                    return Result((self.artifact_id,))
                if compact.startswith("SELECT run_id FROM uec.acquisition_runs"):
                    return Result((self.run_id,))
                if compact.startswith("INSERT INTO uec.source_records"):
                    key = (params[1], params[2], params[3])
                    if key in self.records:
                        return Result()
                    self.records[key] = params[0]
                    return Result((params[0],))
                if compact.startswith("SELECT source_record_id FROM uec.source_records"):
                    return Result((self.records[(params[0], params[1], params[2])],))
                if compact.startswith("INSERT INTO uec.observations"):
                    key = (params[1], params[2], params[3])
                    if key in self.observations:
                        return Result()
                    self.observations[key] = params[0]
                    return Result((params[0],))
                if compact.startswith("SELECT observation_id FROM uec.observations"):
                    return Result((self.observations[(params[0], params[1], params[2])],))
                return Result()

        rows = [
            {"source_id": "synthetic", "source_row": 1, "normalized": {"establishment_id": "A", "trading_name": "A"}},
            {"source_id": "synthetic", "source_row": 2, "normalized": {"establishment_id": "B", "trading_name": "B"}},
        ]
        manifest = {
            "source_id": "synthetic", "source_url": "https://example.invalid/synthetic",
            "retrieved_at_utc": "2026-09-16T00:00:00Z", "checksum_sha256": "a" * 64,
            "byte_size": 1, "config_version": "test", "country_code": "ZZ",
        }
        connection = Connection()
        observed = []

        def interrupt(batch_number, offset, batch_count):
            observed.append((batch_number, offset, batch_count))
            raise RuntimeError("synthetic process interruption")

        with patch.object(MODULE.psycopg, "connect", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "synthetic process interruption"):
                MODULE.import_candidate("postgresql://loopback", manifest, rows, "candidate-test", False, 1, interrupt)
            resumed = MODULE.import_candidate("postgresql://loopback", manifest, rows, "candidate-test", False, 1)
            duplicate = MODULE.import_candidate("postgresql://loopback", manifest, rows, "candidate-test", False, 1)

        self.assertEqual(observed, [(1, 0, 1)])
        self.assertEqual(resumed, 1)
        self.assertEqual(duplicate, 0)
        self.assertEqual(connection.transaction_events, [False, False, False, False, False])

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
