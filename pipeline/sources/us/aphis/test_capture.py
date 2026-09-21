import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from .capture import build_capture_manifest, write_document_inventory


class CaptureManifestTests(unittest.TestCase):
    def test_records_ordered_page_provenance_and_totals(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            header = ["Customer Number", "Certificate Number", "Inspection Date"]
            for name, rows in (("page-01.csv", [["1", "1-R-1", "1/2/2025"]]), ("page-02.csv", [["2", "2-R-2", "1/3/2025"], ["3", "3-R-3", "1/4/2025"]])):
                with (root / name).open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(header)
                    writer.writerows(rows)
            output = root / "capture-manifest.json"
            lineage = root / "staging" / "inspections-with-lineage.csv"
            manifest = build_capture_manifest(
                [root / "page-01.csv", root / "page-02.csv"],
                output_path=output,
                source_url="https://example.invalid/inspection-reports",
                retrieved_at_utc="2026-09-19T18:00:00Z",
                query_context={"earliest_inspection_date": "2025-01-01"},
                excluded_files=["unrelated-download.csv"],
                lineage_output_path=lineage,
            )

            self.assertEqual(manifest["input_rows"], 3)
            self.assertEqual(manifest["page_count"], 2)
            self.assertEqual([page["ordinal"] for page in manifest["pages"]], [1, 2])
            self.assertEqual(manifest["excluded_files"], ["unrelated-download.csv"])
            self.assertEqual(manifest["derived_artifact"]["input_rows"], 3)
            self.assertTrue(manifest["derived_artifact"]["row_sequence_match"])
            with lineage.open(encoding="utf-8", newline="") as handle:
                lineage_rows = list(csv.DictReader(handle))
            self.assertEqual(lineage_rows[1]["__capture_page_ordinal"], "2")
            self.assertEqual(lineage_rows[1]["__capture_page_row"], "1")
            self.assertEqual(lineage_rows[1]["__capture_page_retrieved_at_utc"], "unknown")
            self.assertEqual(lineage_rows[1]["__capture_source_url"], "https://example.invalid/inspection-reports")
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["input_rows"], 3)

    def test_rejects_header_drift(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "page-01.csv").write_text("a,b\n1,2\n", encoding="utf-8")
            (root / "page-02.csv").write_text("a,c\n3,4\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "header mismatch"):
                build_capture_manifest(
                    [root / "page-01.csv", root / "page-02.csv"],
                    output_path=root / "manifest.json",
                    source_url="https://example.invalid",
                    retrieved_at_utc="2026-09-19T18:00:00Z",
                    query_context={},
                )

    def test_document_inventory_keeps_missing_downloads_explicit(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "document-inventory.json"
            inventory = write_document_inventory(
                output,
                source_url="https://example.invalid",
                query_context={"provider_total": 3},
                associated_ui_link_rows=3,
                document_route="public-document-route",
                downloaded_documents=0,
                status="associated-links-visible-download-not-captured",
                failure_reason="browser blocked",
            )

            self.assertEqual(inventory["associated_ui_link_rows"], 3)
            self.assertEqual(inventory["downloaded_documents"], 0)
            self.assertTrue(inventory["non_ui_endpoint_not_attempted"])
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], inventory["status"])


if __name__ == "__main__":
    unittest.main()
