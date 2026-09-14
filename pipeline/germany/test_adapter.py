#!/usr/bin/env python3
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

try:
    from .adapter import parse, normalize, run, source_metadata
except ImportError:
    from adapter import parse, normalize, run, source_metadata


ROOT = Path(__file__).parent
FIXTURE = ROOT / "fixtures" / "synthetic_source.csv"
CONFIG = {
    "source_url": "https://example.invalid/synthetic-germany.csv",
    "retrieval_timestamp": "2026-09-13T00:00:00Z",
    "source_publication_date": "2026-09-12",
}


class GermanyAdapterTests(unittest.TestCase):
    def test_provenance_and_source_values_are_preserved(self):
        raw = FIXTURE.read_bytes()
        metadata = source_metadata(raw, CONFIG)
        records = parse(raw, metadata)
        self.assertEqual(metadata["checksum_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(records[0]["source_id"], "DE-SYN-001")
        self.assertEqual(records[0]["source_values"]["activity_code"], "CP")
        self.assertIn("source_url", records[0]["provenance"])

    def test_classification_anomaly_is_quarantined_and_unknown_is_explicit(self):
        normalized, quarantine = normalize(parse(FIXTURE.read_bytes(), source_metadata(FIXTURE.read_bytes(), CONFIG)))
        self.assertEqual([row["type"] for row in normalized], ["Meat Processing", "Meat Slaughter", "Meat Processing"])
        self.assertEqual(len(quarantine), 1)
        self.assertEqual(quarantine[0]["quarantine_reason"], "unknown activity code")
        unresolved = next(row for row in normalized if row["source_id"] == "DE-SYN-004")
        self.assertEqual(unresolved["coordinate_status"], "unresolved")
        self.assertIsNone(unresolved["latitude"])

    def test_rerun_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            first = run(FIXTURE, Path(directory) / "one", CONFIG)
            second = run(FIXTURE, Path(directory) / "two", CONFIG)
            self.assertEqual(first, second)
            for state in ("parsed", "normalized", "quarantined"):
                one = (Path(directory) / "one" / state / "records.jsonl").read_bytes()
                two = (Path(directory) / "two" / state / "records.jsonl").read_bytes()
                self.assertEqual(one, two)

    def test_failed_input_does_not_replace_previous_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            run(FIXTURE, output, CONFIG)
            before = (output / "normalized" / "records.jsonl").read_bytes()
            bad = Path(directory) / "bad.csv"
            bad.write_text("source_id,name\nBROKEN,row\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                run(bad, output, CONFIG)
            self.assertEqual(before, (output / "normalized" / "records.jsonl").read_bytes())

    def test_no_release_is_created_by_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            manifest = run(FIXTURE, output, CONFIG)
            self.assertEqual(manifest["release_state"], "not-created")
            self.assertFalse((output / "released" / "records.jsonl").exists())
            self.assertEqual(json.loads((output / "run-manifest.json").read_text())["quarantined_rows"], 1)


if __name__ == "__main__":
    unittest.main()
