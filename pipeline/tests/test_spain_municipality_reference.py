import unittest

from pipeline.sources.spain_rgseaa.municipality_reference import (
    SOURCE_URL, exact_municipality_reference_index, normalized_reference_key,
    resolve_municipality_reference,
)


class SpainIgnMunicipalityReferenceTests(unittest.TestCase):
    def setUp(self):
        self.reference = {
            "municipality_code": "28079", "municipality_name": "Madrid",
            "province_name": "Madrid", "latitude": 40.4169, "longitude": -3.7035,
            "coordinate_origin": "Mapa", "population": 3300000,
            "source_artifact_sha256": "a" * 64, "source_url": SOURCE_URL,
        }

    def test_exact_name_and_official_province_equivalent_resolves_coarse_point(self):
        result = resolve_municipality_reference("Madrid", "Madrid", [self.reference])
        self.assertEqual(result["outcome"], "matched")
        self.assertEqual(result["precision"], "locality_reference_coarse")
        self.assertEqual(result["match_method"], "exact_ign_municipality_and_official_province")
        self.assertEqual(result["reference_source_id"], "ign-ngmep-2026:28079")

    def test_indexed_join_supports_only_allowlisted_official_province_aliases(self):
        index = exact_municipality_reference_index([self.reference])
        result = resolve_municipality_reference("Madrid", "Madrid", index)
        self.assertEqual(result["outcome"], "matched")
        self.assertEqual(resolve_municipality_reference("Madrid", "Sevilla", index)["outcome"],
                         "not_found")

    def test_wrong_province_and_unmatched_name_do_not_resolve(self):
        self.assertEqual(resolve_municipality_reference("Madrid", "Sevilla", [self.reference])["outcome"],
                         "not_found")
        self.assertEqual(resolve_municipality_reference("Madrid City", "Madrid", [self.reference])["outcome"],
                         "not_found")

    def test_duplicate_exact_names_remain_ambiguous(self):
        other = {**self.reference, "municipality_code": "28080"}
        self.assertEqual(resolve_municipality_reference("Madrid", "Madrid", [self.reference, other])["outcome"],
                         "ambiguous_exact_municipality_and_province")

    def test_untrusted_coordinate_origin_and_invalid_coordinates_fail_closed(self):
        approximate = {**self.reference, "coordinate_origin": "En estudio"}
        self.assertEqual(resolve_municipality_reference("Madrid", "Madrid", [approximate])["outcome"],
                         "coordinate_origin_untrusted")
        invalid = {**self.reference, "longitude": float("nan")}
        self.assertEqual(resolve_municipality_reference("Madrid", "Madrid", [invalid])["outcome"],
                         "invalid_ign_coordinates")

    def test_observed_official_archive_origin_spellings_resolve_and_are_preserved(self):
        for origin in ("GPS. PNRGM", "Coordinado IGR.Poblaciones",
                       "Coordinado_IGR Poblaciones"):
            with self.subTest(origin=origin):
                observed = {**self.reference, "coordinate_origin": origin}
                result = resolve_municipality_reference("Madrid", "Madrid", [observed])
                self.assertEqual(result["outcome"], "matched")
                self.assertEqual(result["coordinate_origin"], origin)

    def test_reference_provenance_is_required(self):
        missing = {key: value for key, value in self.reference.items() if key != "source_artifact_sha256"}
        self.assertEqual(resolve_municipality_reference("Madrid", "Madrid", [missing])["outcome"],
                         "reference_provenance_missing")
        wrong_source = {**self.reference, "source_url": "https://example.invalid/municipalities.csv"}
        self.assertEqual(resolve_municipality_reference("Madrid", "Madrid", [wrong_source])["outcome"],
                         "reference_provenance_mismatch")

    def test_normalized_join_key_requires_both_official_values(self):
        self.assertEqual(normalized_reference_key("Madrid", "Madrid"), "madrid|madrid")
        with self.assertRaisesRegex(ValueError, "municipality_reference_key_incomplete"):
            normalized_reference_key("Madrid", "")


if __name__ == "__main__":
    unittest.main()
