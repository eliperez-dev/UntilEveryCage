from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.contracts.adapter_contract import SourceArtifact, assert_manifest
from pipeline.contracts.refresh import row_free_summary
from .adapter import ADAPTER_VERSION, HEADERS, SCHEMA_VERSION, SOURCE_ID, NewZealandRmpAdapter
from .refresh import NewZealandRmpRefreshAdapter


def csv_bytes(*rows: dict[str, str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=HEADERS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def row(**changes: str) -> dict[str, str]:
    values = {header: "" for header in HEADERS}
    values.update({
        "MPI ID Number": "MPI-SYNTH-001",
        "Risk Measure Type": "Risk Management Programme",
        "Programme Type": "Custom",
        "Operator Business Name": "Synthetic Meat Processor Ltd",
        "Status": "Registered",
        "Is Suspended": "False",
        "Physical Address": "Synthetic Road 1",
        "Physical Town/City": "Testville",
        "Number of Locations": "2",
        "Product/Material": "Meat products",
        "Primary": "Slaughtering and processing",
        "Secondary Process": "Cold storage",
    })
    values.update(changes)
    return values


class NewZealandRmpAdapterTests(unittest.TestCase):
    def test_preserves_source_values_and_does_not_create_coordinates_or_single_site_claim(self):
        parsed = NewZealandRmpAdapter().parse_bytes(csv_bytes(row()))
        self.assertEqual(parsed["input_rows"], 1)
        self.assertEqual(len(parsed["accepted"]), 1)
        record = parsed["accepted"][0]
        self.assertEqual(record["source_id"], SOURCE_ID)
        self.assertEqual(record["source_values"]["Programme Type"], "Custom")
        self.assertEqual(record["normalized"]["establishment_id"], "MPI-SYNTH-001")
        self.assertEqual(record["normalized"]["location_count"], 2)
        self.assertEqual(record["normalized"]["private_location_evidence"], {
            "address": "Synthetic Road 1", "city": "Testville", "country_code": "NZ",
            "number_of_locations": "2", "location_count": 2,
        })
        self.assertIn("may be multiple", record["normalized"]["facility_identity_state"])
        self.assertIsNone(record["normalized"]["coordinates"])
        self.assertEqual(parsed["multi_location_rows"], 1)

    def test_generic_custom_without_animal_product_evidence_is_quarantined(self):
        parsed = NewZealandRmpAdapter().parse_bytes(csv_bytes(row(
            **{"Product/Material": "General products", "Primary": "Custom", "Secondary Process": "Storage"}
        )))
        self.assertEqual(len(parsed["accepted"]), 0)
        self.assertEqual(parsed["quarantined"][0]["reasons"], ("outside_narrow_animal_product_scope",))

    def test_duplicate_ids_and_invalid_native_flags_are_quarantined(self):
        parsed = NewZealandRmpAdapter().parse_bytes(csv_bytes(
            row(), row(**{"Operator Business Name": "Synthetic second operator"}),
            row(**{"MPI ID Number": "MPI-SYNTH-003", "Is Suspended": "unknown"}),
        ))
        self.assertEqual(len(parsed["accepted"]), 0)
        self.assertEqual(len(parsed["quarantined"]), 3)
        reasons = {reason for item in parsed["quarantined"] for reason in item["reasons"]}
        self.assertEqual(reasons, {"duplicate_mpi_id_number", "invalid_suspension_flag"})

    def test_schema_drift_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "schema drift"):
            NewZealandRmpAdapter().parse_bytes(csv_bytes(row()).replace(b"MPI ID Number", b"Different ID"))

    def test_private_manifest_and_candidate_handoff_are_row_counted_and_no_graph_is_emitted(self):
        content = csv_bytes(row(), row(**{
            "MPI ID Number": "MPI-SYNTH-002",
            "Product/Material": "General products",
            "Primary": "Custom",
            "Secondary Process": "Storage",
        }))
        digest = hashlib.sha256(content).hexdigest()
        artifact = SourceArtifact(
            "https://mpi.example.invalid/rmp", "2026-10-27T06:21:51Z", digest, len(content),
            code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "synthetic.csv"
            raw.write_bytes(content)
            adapter = NewZealandRmpAdapter()
            manifest = adapter.run(raw, root / "run", artifact)
            assert_manifest(manifest, content, SCHEMA_VERSION)
            self.assertEqual(manifest["input_rows"], 2)
            self.assertEqual(manifest["normalized_rows"], 1)
            self.assertEqual(manifest["quarantined_rows"], 1)
            handoff = adapter.write_candidate_handoff(
                root / "handoff", artifact, adapter.parse_bytes(content)
            )
            self.assertEqual(handoff["source_id"], SOURCE_ID)
            self.assertEqual(handoff["normalized_rows"], 1)
            handoff_row = json.loads((root / "handoff" / "normalized" / "records.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(handoff_row["normalized"]["private_location_evidence"]["number_of_locations"], "2")
            self.assertEqual(handoff_row["normalized"]["private_location_evidence"]["location_count"], 2)
            self.assertFalse((root / "handoff" / "graph-candidates").exists())
            self.assertEqual(json.loads((root / "run" / "manifest.json").read_text())["release_state"], "not-created")

    def test_refresh_bridge_writes_private_handoff_and_returns_only_row_free_counts(self):
        content = csv_bytes(row())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "source.csv"
            raw.write_bytes(content)
            summary = NewZealandRmpRefreshAdapter().refresh(
                mode="local-artifact", run_dir=root / "refresh", artifact=raw,
                options={"retrieved_at_utc": "2026-10-27T06:21:51Z"},
            )
            self.assertEqual(summary["lifecycle_status"], "candidate-ready")
            self.assertTrue(summary["candidate_handoff"])
            self.assertEqual(summary["input_rows"], 1)
            self.assertEqual(summary["normalized_rows"], 1)
            self.assertEqual(summary["candidate_observation_rows"], 1)
            row_free_summary(summary)
            self.assertTrue((root / "refresh" / "candidate-handoff" / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
