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

    def test_reference_derived_article_alias_matches_in_iterable_and_indexed_paths(self):
        reference = {**self.reference, "municipality_code": "28001",
                     "municipality_name": "Sampletown, El"}
        expected = "ign_article_reordered_municipality_and_official_province"
        for references in ([reference], exact_municipality_reference_index([reference])):
            with self.subTest(indexed=isinstance(references, dict)):
                result = resolve_municipality_reference("El Sampletown", "Madrid", references)
                self.assertEqual(result["outcome"], "matched")
                self.assertEqual(result["match_method"], expected)
                self.assertEqual(result["municipality_name"], "Sampletown, El")
                self.assertEqual(result["precision"], "locality_reference_coarse")

    def test_exact_slash_component_alias_and_combined_slash_article_alias(self):
        slash_reference = {**self.reference, "municipality_code": "28002",
                           "municipality_name": "Sampletown / Vila Mostra"}
        combined_reference = {**self.reference, "municipality_code": "28003",
                              "municipality_name": "Sampletown (El) / Vila Mostra"}
        slash_result = resolve_municipality_reference(
            "Vila Mostra", "Madrid", exact_municipality_reference_index([slash_reference]))
        self.assertEqual(slash_result["match_method"],
                         "ign_slash_component_municipality_and_official_province")
        combined_result = resolve_municipality_reference(
            "El Sampletown", "Madrid", exact_municipality_reference_index([combined_reference]))
        self.assertEqual(combined_result["match_method"],
                         "ign_slash_component_and_article_reordered_municipality_and_official_province")
        iterable_result = resolve_municipality_reference(
            "El Sampletown", "Madrid", [combined_reference])
        self.assertEqual(combined_result, iterable_result)

    def test_alias_still_requires_exact_official_province_and_known_suffix(self):
        reference = {**self.reference, "municipality_code": "28004",
                     "municipality_name": "Sampletown, El"}
        index = exact_municipality_reference_index([reference])
        self.assertEqual(resolve_municipality_reference(
            "El Sampletown", "Sevilla", index)["outcome"], "not_found")
        self.assertEqual(resolve_municipality_reference(
            "Sampletown, Este", "Madrid", index)["outcome"], "not_found")

    def test_alias_collision_with_distinct_canonical_target_remains_ambiguous(self):
        canonical = {**self.reference, "municipality_code": "28005",
                     "municipality_name": "El Sampletown"}
        alias_target = {**self.reference, "municipality_code": "28006",
                        "municipality_name": "Sampletown, El"}
        rows = [canonical, alias_target]
        for references in (rows, exact_municipality_reference_index(rows)):
            with self.subTest(indexed=isinstance(references, dict)):
                self.assertEqual(resolve_municipality_reference(
                    "El Sampletown", "Madrid", references)["outcome"],
                    "ambiguous_exact_municipality_and_province")

    def test_duplicate_rows_for_same_official_municipality_are_one_target(self):
        first = {**self.reference, "municipality_code": "28007",
                 "municipality_name": "Sampletown, El"}
        duplicate = dict(first)
        for references in ([first, duplicate], exact_municipality_reference_index([first, duplicate])):
            with self.subTest(indexed=isinstance(references, dict)):
                result = resolve_municipality_reference("El Sampletown", "Madrid", references)
                self.assertEqual(result["outcome"], "matched")
                self.assertEqual(result["match_method"],
                                 "ign_article_reordered_municipality_and_official_province")

    def test_canonical_match_retains_existing_method_and_provenance(self):
        for references in ([self.reference], exact_municipality_reference_index([self.reference])):
            result = resolve_municipality_reference("Madrid", "Madrid", references)
            self.assertEqual(result["match_method"],
                             "exact_ign_municipality_and_official_province")
            self.assertEqual(result["municipality_name"], "Madrid")
            self.assertEqual(result["source_artifact_sha256"], "a" * 64)

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
