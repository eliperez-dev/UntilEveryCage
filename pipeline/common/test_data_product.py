import json
import tempfile
import unittest
from pathlib import Path

from pipeline.common.data_product import (
    DataProductError,
    CSV_FIELDS,
    data_dictionary,
    paginate_rows,
    render_csv,
    validate_public_rows,
    verify_package,
    write_package,
)


def metadata(profile="official", count=1):
    return {
        "release_id": "release-2026-09-15",
        "profile": profile,
        "status": "promoted",
        "test_only": False,
        "eligible": True,
        "publication_state": "project-published",
        "ruleset_version": "rules-v1",
        "schema_version": "uec-location-projection-v1",
        "generated_at": "2026-09-15T00:00:00Z",
        "retrieved_at": "2026-09-14T00:00:00Z",
        "source_coverage": [{"source_id": "source-a", "row_count": count}],
        "row_counts": {"eligible_rows": count},
        "checksums": {},
        "review_state": "project-approved and privacy-screened",
        "limitations": ["Synthetic fixture; not a complete denominator."],
        "supersedes": None,
    }


def row(profile="official", **overrides):
    result = {
        "facility_id": "00000000-0000-0000-0000-000000000001",
        "canonical_name": "=Not a formula",
        "country_code": "DK",
        "city": "Testby",
        "category": "slaughter",
        "display_precision": "city",
        "latitude": 55.0,
        "longitude": 10.0,
        "lifecycle_status": "active_observed",
        "first_observed_at": "2026-01-01T00:00:00Z",
        "last_observed_at": "2026-09-01T00:00:00Z",
        "observation_count": 1,
        "source_type": "official",
        "factual_review_status": "reviewed",
        "privacy_screening_status": "passed",
        "project_approval": "approved",
        "reviewer_role": "maintainer",
        "publication_warning": None,
        "publication_profile": profile,
        "release_id": "release-2026-09-15",
        "release_ruleset_version": "rules-v1",
        "provenance_source_id": "source-a",
        "provenance_source_name": "Synthetic source",
        "provenance_source_url": "https://example.invalid/source",
        "provenance_retrieved_at": "2026-09-14T00:00:00Z",
        "source_rights_status": "attribution_required",
        "publication_eligible": True,
    }
    result.update(overrides)
    return result


class DataProductTests(unittest.TestCase):
    def test_deterministic_csv_and_geojson_package(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            a = write_package(first, metadata(), [row()])
            b = write_package(second, metadata(), [row()])
            self.assertEqual(a["files"], b["files"])
            self.assertEqual((first / "locations.csv").read_bytes(), (second / "locations.csv").read_bytes())
            self.assertEqual((first / "locations.geojson").read_bytes(), (second / "locations.geojson").read_bytes())
            self.assertEqual(verify_package(first)["status"], "verified")

    def test_pagination_has_export_parity(self):
        rows = [row(facility_id=f"00000000-0000-0000-0000-{number:012d}") for number in range(7)]
        validated = validate_public_rows(rows, metadata(count=7))
        traversed = []
        cursor = None
        while True:
            page, cursor = paginate_rows(validated, limit=3, cursor=cursor)
            traversed.extend(item["facility_id"] for item in page)
            if cursor is None:
                break
        self.assertEqual(traversed, [item["facility_id"] for item in validated])

    def test_formula_prefix_is_neutralized_only_in_csv(self):
        rendered = render_csv([row()]).decode()
        self.assertIn("'=Not a formula", rendered)
        self.assertNotIn("street_address", rendered)

    def test_release_and_profile_gates_fail_closed(self):
        for changes, message in [
            ({"test_only": True}, "test-only"),
            ({"status": "candidate"}, "promoted"),
            ({"eligible": False}, "eligible"),
            ({"profile": "community"}, "profile"),
        ]:
            candidate = metadata()
            candidate.update(changes)
            with self.assertRaisesRegex(DataProductError, message):
                write_package(Path(tempfile.mkdtemp()), candidate, [row()])

    def test_rows_cannot_bypass_suppression_or_rights(self):
        for changes, message in [
            ({"suppressed": True}, "suppressed"),
            ({"source_rights_status": "unknown"}, "rights"),
            ({"privacy_screening_status": "pending"}, "publication-eligible"),
            ({"street_address": "private"}, "restricted fields"),
            ({"release_id": "other"}, "selected release"),
        ]:
            with self.assertRaisesRegex(DataProductError, message):
                write_package(Path(tempfile.mkdtemp()), metadata(), [row(**changes)])

    def test_malformed_metadata_and_tampering_fail_verification(self):
        for field in ("release_id", "generated_at", "source_coverage", "row_counts", "checksums"):
            invalid = metadata()
            del invalid[field]
            with self.assertRaises(DataProductError):
                write_package(Path(tempfile.mkdtemp()), invalid, [row()])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_package(path, metadata(), [row()])
            (path / "locations.csv").write_bytes((path / "locations.csv").read_bytes() + b"tampered")
            with self.assertRaisesRegex(DataProductError, "checksum"):
                verify_package(path)

    def test_empty_release_is_valid_and_geojson_has_no_features(self):
        with tempfile.TemporaryDirectory() as directory:
            write_package(Path(directory), metadata(count=0), [])
            geojson = json.loads((Path(directory) / "locations.geojson").read_text())
            self.assertEqual(geojson["features"], [])

    def test_mixed_rights_are_carried_per_row(self):
        second = row(facility_id="00000000-0000-0000-0000-000000000002", provenance_source_id="source-b", source_rights_status="cleared")
        with tempfile.TemporaryDirectory() as directory:
            result = write_package(Path(directory), {**metadata(count=2), "source_coverage": [{"source_id": "source-a", "row_count": 1}, {"source_id": "source-b", "row_count": 1}]}, [row(), second])
            self.assertEqual(result["manifest"]["row_counts"]["packaged_rows"], 2)
            self.assertIn("source_rights_status", (Path(directory) / "data-dictionary.json").read_text())

    def test_large_export_is_not_silently_truncated(self):
        rows = [row(facility_id=f"00000000-0000-0000-0000-{number:012d}") for number in range(1001)]
        with tempfile.TemporaryDirectory() as directory:
            result = write_package(Path(directory), metadata(count=len(rows)), rows)
            self.assertEqual(result["manifest"]["row_counts"]["packaged_rows"], 1001)

    def test_dictionary_is_machine_readable_and_field_order_is_stable(self):
        dictionary = data_dictionary()
        self.assertEqual([field["name"] for field in dictionary["fields"]], list(CSV_FIELDS))
        self.assertEqual(dictionary["schema_version"], "uec-location-projection-v1")


if __name__ == "__main__":
    unittest.main()
