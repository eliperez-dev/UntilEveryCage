#!/usr/bin/env python3
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

try:
    from .adapter import parse, normalize, run, source_metadata
    from .bltu_adapter import run as run_bltu
except ImportError:
    from adapter import parse, normalize, run, source_metadata
    from bltu_adapter import run as run_bltu


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

    def test_nonfinite_coordinates_are_unresolved_and_json_is_standard(self):
        header = "source_id,name,activity_code,species_codes,street,city,zip,latitude,longitude\n"
        rows = "DE-NAN,Synthetic,CP,,Street,City,,nan,10\nDE-INF,Synthetic,SH,,Street,City,,50,inf\n"
        raw = (header + rows).encode()
        normalized, quarantine = normalize(parse(raw, source_metadata(raw, CONFIG)))
        self.assertFalse(quarantine)
        self.assertEqual(len(normalized), 2)
        for row in normalized:
            self.assertEqual(row["coordinate_status"], "unresolved")
            self.assertIsNone(row["latitude"])
            self.assertIsNone(row["longitude"])
            json.dumps(row, allow_nan=False)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "nonfinite.csv"
            source.write_bytes(raw)
            run(source, root / "out", CONFIG)
            lines = (root / "out" / "normalized" / "records.jsonl").read_text(encoding="utf-8").splitlines()
            def reject_constant(value):
                raise ValueError(f"non-standard JSON constant: {value}")
            self.assertEqual(len([json.loads(line, parse_constant=reject_constant) for line in lines]), 2)

    def test_bltu_positional_mapping_preserves_duplicate_headers_and_quarantines_unknowns(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            config = {"source_url": "https://example.invalid/bltu", "terms_status": "pending_confirmation"}
            manifest = run_bltu(ROOT / "fixtures" / "synthetic_bltu.csv", output, config)
            self.assertEqual(manifest["input_rows"], 3)
            self.assertEqual(manifest["normalized_rows"], 1)
            self.assertEqual(manifest["quarantined_rows"], 2)
            records = [json.loads(line) for line in (output / "normalized" / "records.jsonl").read_text().splitlines()]
            self.assertEqual(len(records[0]["source_columns"]), 50)
            self.assertEqual(records[0]["source_id"], "DE-SYN-002")
            self.assertEqual(records[0]["source_columns"][10]["header"], "SH")
            self.assertIsNone(records[0]["latitude"])
            self.assertTrue(manifest["schema_fingerprint"])
            self.assertTrue(manifest["config_fingerprint"])
            self.assertEqual(manifest["mapping_version"], "de-bltu-activity-map-2")
            diagnostics = json.loads((output / "validation-report.json").read_text())
            self.assertEqual(diagnostics["schema_status"], "matched")
            self.assertEqual(diagnostics["row_length_counts"], {"50": 3})
            quarantined = [json.loads(line) for line in (output / "quarantined" / "records.jsonl").read_text().splitlines()]
            self.assertIn("unmapped activity code", [row["quarantine_reason"] for row in quarantined])

    def test_bltu_schema_shift_with_same_width_quarantines_every_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lines = (ROOT / "fixtures" / "synthetic_bltu.csv").read_text(encoding="utf-8").splitlines()
            headers = lines[0].split(";")
            headers[10], headers[11] = headers[11], headers[10]
            raw = root / "shifted.csv"
            raw.write_text(";".join(headers) + "\n" + "\n".join(lines[1:]) + "\n", encoding="utf-8")
            output = root / "out"
            manifest = run_bltu(raw, output, {"source_url": "https://example.invalid/bltu"})
            self.assertEqual(manifest["normalized_rows"], 0)
            self.assertEqual(manifest["quarantined_rows"], 3)
            self.assertFalse((output / "released" / "records.jsonl").exists())
            self.assertEqual(json.loads((output / "validation-report.json").read_text())["schema_status"], "unrecognized")
            reasons = [json.loads(line)["quarantine_reason"] for line in (output / "quarantined" / "records.jsonl").read_text().splitlines()]
            self.assertTrue(all(reason == "unrecognized header schema" for reason in reasons))

    def test_bltu_mapping_is_explicit_and_coordinates_are_never_enriched(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            run_bltu(ROOT / "fixtures" / "synthetic_bltu.csv", output, {"source_url": "https://example.invalid/bltu", "terms_status": "pending_confirmation"})
            records = [json.loads(line) for line in (output / "normalized" / "records.jsonl").read_text().splitlines()]
            self.assertTrue(all(row["interpretation"]["status"] == "mapped" for row in records))
            self.assertTrue(all(row["coordinate_status"] == "source_unavailable" for row in records))
            self.assertTrue(all(row["latitude"] is None and row["longitude"] is None for row in records))


if __name__ == "__main__":
    unittest.main()
