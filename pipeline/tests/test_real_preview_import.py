"""Sanitized unit coverage for the real-preview importer contract."""

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "maintenance" / "import-real-preview.py"
SPEC = importlib.util.spec_from_file_location("import_real_preview", MODULE_PATH)
IMPORTER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(IMPORTER)


class RealPreviewImporterTests(unittest.TestCase):
    def test_precision_comes_from_coordinate_and_documented_precision_fields(self):
        numeric = IMPORTER.parse_row("it.853-2004", {
            "source_identifier": "sanitized-fixture", "latitude": 44.1,
            "longitude": 11.2, "coordinate_precision": "numeric", "facility_candidate": True,
        })
        self.assertEqual(numeric[1], "numeric_source_coordinate")
        self.assertEqual(numeric[5:7], (44.1, 11.2))
        self.assertTrue(numeric[-1])
        coarse = IMPORTER.parse_row("fr.dgal.section-i", {
            "source_identifier": "sanitized-fixture", "city": "Example",
            "coordinate_precision": "city",
        })
        self.assertEqual(coarse[1], "city_postal")
        unmapped = IMPORTER.parse_row("us.fsis", {
            "source_identifier": "sanitized-fixture", "id": "numeric-looking-12345",
        })
        self.assertEqual(unmapped[1], "unmapped_private_observation")
        self.assertFalse(unmapped[-1])

    def test_undocumented_or_partial_coordinates_fail_closed(self):
        with self.assertRaises(IMPORTER.ImportFailure):
            IMPORTER.parse_row("it.853-2004", {"source_identifier": "x", "latitude": 44.1, "longitude": 11.2})
        with self.assertRaises(IMPORTER.ImportFailure):
            IMPORTER.parse_row("it.853-2004", {"source_identifier": "x", "latitude": 44.1})

    def test_artifact_hash_is_streamed_and_detected(self):
        with tempfile.TemporaryDirectory(dir=MODULE_PATH.parents[3]) as directory:
            path = Path(directory) / "fixture.jsonl"
            content = b'{"source_identifier":"synthetic","city":"Example"}\n'
            path.write_bytes(content)
            digest, size = IMPORTER.digest_file(path)
            self.assertEqual(digest, hashlib.sha256(content).hexdigest())
            self.assertEqual(size, len(content))

    def test_all_allowlisted_sources_require_matching_raw_and_normalized_artifacts(self):
        with tempfile.TemporaryDirectory(dir=MODULE_PATH.parents[3]) as directory:
            root = Path(directory)
            for source in sorted(IMPORTER.ALLOWED):
                normalized = root / f"{source}.jsonl"
                normalized_content = json.dumps({"source_identifier": "fixture", "source_id": source,
                    "facility_candidate": False}, separators=(",", ":")).encode() + b"\n"
                normalized.write_bytes(normalized_content)
                original = root / f"{source}.bin"
                raw_content = b"synthetic source artifact " + source.encode()
                original.write_bytes(raw_content)
                manifest = {
                    "source_id": source,
                    "normalized_sha256": hashlib.sha256(normalized_content).hexdigest(),
                    "checksum_sha256": hashlib.sha256(raw_content).hexdigest(),
                }
                (root / f"{source}-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            manifests = IMPORTER.find_manifests(root)
            artifacts = IMPORTER.resolve_artifacts(root, manifests)
            self.assertEqual(set(artifacts), IMPORTER.ALLOWED)
            self.assertTrue(all(path.suffix == ".jsonl" for path in artifacts.values()))

    def test_duplicate_source_handoffs_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=MODULE_PATH.parents[3]) as directory:
            root = Path(directory)
            for index in range(2):
                (root / f"handoff-{index}.json").write_text(json.dumps({
                    "source_id": "it.853-2004", "normalized_sha256": "a" * 64,
                }), encoding="utf-8")
            with self.assertRaises(IMPORTER.ImportFailure) as failure:
                IMPORTER.find_manifests(root)
            self.assertEqual(failure.exception.code, "duplicate_handoff")

    def test_aphis_is_rejected_even_when_not_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "forbidden.json").write_text(json.dumps({"source_id": "us.aphis", "normalized_sha256": "a" * 64}), encoding="utf-8")
            with self.assertRaises(IMPORTER.ImportFailure) as failure:
                IMPORTER.find_manifests(root)
            self.assertEqual(failure.exception.code, "forbidden_source_present")

    def test_public_zero_gate_fails_closed_if_any_public_projection_exists(self):
        class EmptyDatabase:
            def execute(self, sql, params=()):
                return type("Result", (), {"fetchone": lambda self: (None,)})()

        self.assertEqual(IMPORTER.public_zero_counts(EmptyDatabase()), (0, 0))

        class PublicRowsDatabase:
            def execute(self, sql, params=()):
                value = "uec.release_members" if "to_regclass" in sql else 1
                return type("Result", (), {"fetchone": lambda self: (value,)})()

        with self.assertRaises(IMPORTER.ImportFailure) as failure:
            IMPORTER.public_zero_counts(PublicRowsDatabase())
        self.assertEqual(failure.exception.code, "public_rows_present")


if __name__ == "__main__":
    unittest.main()
