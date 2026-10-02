from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import unittest

from pipeline.taxonomy_crosswalk import TAXONOMY_VERSION, crosswalk_document, persistence_assignments, project_observation, reproject

FIXTURES = Path(__file__).parent / "fixtures" / "taxonomy_crosswalk_cases.json"
IMPORTER_PATH = Path(__file__).parents[1] / "scripts" / "maintenance" / "import-real-preview.py"
IMPORTER_SPEC = importlib.util.spec_from_file_location("import_real_preview_taxonomy_test", IMPORTER_PATH)
IMPORTER = importlib.util.module_from_spec(IMPORTER_SPEC)
assert IMPORTER_SPEC.loader
IMPORTER_SPEC.loader.exec_module(IMPORTER)


class TaxonomyCrosswalkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(FIXTURES.read_text(encoding="utf-8"))
        cls.by_name = {case["name"]: case["record"] for case in cls.cases}

    def test_initial_source_authority_cases(self):
        direct = project_observation(self.by_name["denmark-direct-slaughter"])
        self.assertEqual(direct["taxonomy_primaries"], ["slaughter"])
        self.assertEqual(direct["taxonomy_mapping_method"], "direct")
        self.assertEqual(direct["taxonomy_mapping_status"], "mapped")

        derived = project_observation(self.by_name["uk-derived-label"])
        self.assertEqual(derived["taxonomy_mapping_method"], "derived")
        self.assertEqual(derived["taxonomy_display_category"], "slaughter")

        candidate = project_observation(self.by_name["australia-candidate"])
        self.assertEqual(candidate["taxonomy_mapping_method"], "candidate")
        self.assertEqual(candidate["taxonomy_mapping_status"], "ambiguous")
        self.assertEqual(candidate["taxonomy_display_category"], "unclassified")

    def test_exact_be_fsis_and_cfia_source_evidence_is_direct(self):
        belgium = project_observation({"source_id": "be.locations", "normalized": {
            "activity_codes": ["593"], "source_activity_categories": ["slaughter"]}})
        self.assertEqual(belgium["taxonomy_mapping_method"], "direct")
        self.assertEqual(belgium["taxonomy_display_category"], "slaughter")
        handoff_belgium = project_observation({"source_id": "be.locations", "normalized": {
            "activity_codes": ["593", "594"], "activity_categories": ["slaughter", "processing"]}})
        self.assertEqual(handoff_belgium["taxonomy_mapping_method"], "direct")
        self.assertEqual(handoff_belgium["taxonomy_mapping_status"], "mapped")
        self.assertEqual(handoff_belgium["taxonomy_primaries"], ["slaughter", "processing_and_preparation"])
        partial_belgium = project_observation({"source_id": "be.locations", "normalized": {
            "activity_codes": ["exact-code-1", "exact-code-2"],
            "source_activity_categories": ["slaughter", "export"]}})
        self.assertEqual(partial_belgium["taxonomy_mapping_status"], "partial")
        self.assertEqual(partial_belgium["taxonomy_mapping_method"], "direct")
        fsis = project_observation({"source_id": "us.fsis", "normalized": {
            "species_slaughtered": {"meat_slaughter": "yes"},
            "processing_activities": {"meat_processing": "yes"}}})
        self.assertEqual(fsis["taxonomy_mapping_method"], "direct")
        self.assertEqual(fsis["taxonomy_display_category"], "slaughter")
        cfia = project_observation({"source_id": "ca.cfia.federal-meat", "normalized": {
            "source_function_codes": "codes_1=a", "activity_categories": ["slaughter"]}})
        self.assertEqual(cfia["taxonomy_mapping_method"], "direct")
        self.assertEqual(cfia["taxonomy_display_category"], "slaughter")

    def test_ontario_activity_labels_are_derived_and_source_evidence_is_preserved(self):
        source_values = {"Plant Type": "Abattoir", "Animal Class": "Cattle"}
        record = {"source_id": "ca.ontario.meat-plants", "source_values": source_values,
                  "normalized": {"activity_categories": ["slaughter", "processing"]}}
        projected = project_observation(record)
        self.assertEqual(projected["taxonomy_mapping_method"], "derived")
        self.assertEqual(projected["taxonomy_mapping_status"], "mapped")
        self.assertEqual(projected["taxonomy_primaries"], ["slaughter", "processing_and_preparation"])
        self.assertTrue(all(row["mapping_method"] == "derived"
                            for row in persistence_assignments(projected)))
        projected_rows, _ = reproject([record])
        self.assertEqual(projected_rows[0]["source_values"], source_values)

    def test_uk_labels_are_conservative_derived_and_keep_unmatched_activity_partial(self):
        mapped = project_observation({"source_id": "fsa_approved_establishments", "normalized": {
            "activities": ["Slaughterhouse", "Fresh Fishery Products Plant"],
            "activity_categories": ["slaughter", "processing"]}})
        self.assertEqual(mapped["taxonomy_mapping_method"], "derived")
        self.assertEqual(mapped["taxonomy_mapping_status"], "mapped")
        self.assertEqual(mapped["taxonomy_primaries"], ["slaughter", "processing_and_preparation"])
        self.assertEqual(mapped["taxonomy_assignments"][0]["source_label"], "Fresh Fishery Products Plant; Slaughterhouse")

        partial = project_observation({"source_id": "fss_approved_establishments", "normalized": {
            "activities": ["Slaughterhouse", "Fresh fishery products plant"],
            "activity_codes": ["SH", "CP"]}})
        self.assertEqual(partial["taxonomy_mapping_status"], "partial")
        self.assertEqual(partial["taxonomy_mapping_method"], "derived")

        substring = project_observation({"source_id": "fsa_approved_establishments", "normalized": {
            "activities": ["Freshery wholesale"], "activity_categories": ["processing"]}})
        self.assertEqual(substring["taxonomy_mapping_status"], "unmapped")
        self.assertEqual(substring["taxonomy_primaries"], [])

        coded = project_observation({"source_id": "fss_approved_establishments", "normalized": {
            "activities": ["SH", "CP"]}})
        self.assertEqual(coded["taxonomy_mapping_method"], "derived")
        self.assertEqual(coded["taxonomy_primaries"], ["slaughter", "processing_and_preparation"])
        self.assertEqual(coded["taxonomy_assignments"][0]["source_code"], "CP; SH")

    def test_unknown_partial_conflicting_and_events_fail_closed(self):
        self.assertEqual(project_observation(self.by_name["unknown-code"])["taxonomy_mapping_status"], "unmapped")
        self.assertEqual(project_observation(self.by_name["partial-denmark"])["taxonomy_mapping_status"], "partial")
        self.assertEqual(project_observation(self.by_name["conflicting-france-signals"])["taxonomy_mapping_status"], "conflicting")
        for name in ("unknown-code", "conflicting-france-signals"):
            persisted = persistence_assignments(project_observation(self.by_name[name]))
            self.assertTrue(persisted)
            self.assertTrue(all(row["primary_key"] == "unclassified" for row in persisted))
            self.assertTrue(all(row["leaf_key"] is None for row in persisted))
        event = project_observation(self.by_name["event-only"])
        self.assertEqual(event["taxonomy_mapping_status"], "unclassified")
        self.assertEqual(event["taxonomy_primaries"], [])

    def test_italy_and_spain_remain_unclassified_with_original_values(self):
        for name in ("italy-unclassified", "spain-unclassified"):
            original = self.by_name[name]
            projected = project_observation(original)
            self.assertEqual(projected["taxonomy_primaries"], [])
            self.assertEqual(projected["taxonomy_display_category"], "unclassified")
            rows, _ = reproject([original])
            self.assertEqual(rows[0]["source_values"], original["source_values"])

    def test_multi_activity_precedence_is_order_independent(self):
        original = self.by_name["multiple-activities"]
        reversed_record = {**original, "normalized": {**original["normalized"], "activity_codes": list(reversed(original["normalized"]["activity_codes"]))}}
        first = project_observation(original)
        second = project_observation(reversed_record)
        self.assertEqual(first, second)
        self.assertEqual(first["taxonomy_primaries"], ["slaughter", "processing_and_preparation"])
        self.assertEqual(first["taxonomy_display_category"], "slaughter")

    def test_reprojection_preserves_evidence_and_is_idempotent(self):
        record = {"source_id": "dk.smiley", "source_values": {"code": "keep"},
                  "normalized": {"activity_codes": ["EB.10.10.99"]}}
        first, _ = reproject([record])
        second, report = reproject(first)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["source_values"], record["source_values"])
        self.assertEqual(first[0]["normalized"], record["normalized"])
        self.assertEqual(report["display_change"], {"unchanged": 1})

    def test_report_counts_do_not_depend_on_input_order(self):
        rows = [case["record"] for case in self.cases]
        _, report_a = reproject(rows)
        _, report_b = reproject(list(reversed(rows)))
        self.assertEqual(report_a, report_b)

    def test_crosswalk_documents_match_frozen_persistence_envelope(self):
        for source in ("dk.smiley", "be.locations", "us.fsis", "fr.dgal.section-i",
                       "fsa_approved_establishments", "ca.cfia.federal-meat", "ca.ontario.meat-plants", "it.853-2004",
                       "es.cat.feed-sandach", "au.npi.facilities"):
            document = crosswalk_document(source)
            self.assertEqual(document["source_id"], source)
            self.assertEqual(document["taxonomy_version"], TAXONOMY_VERSION)
            self.assertTrue(document["crosswalk_version"])
            self.assertTrue(document["ruleset_version"])
            self.assertTrue(document["rules"])
            self.assertTrue(all(rule.get("method") in {"direct", "derived", "candidate"}
                                for rule in document["rules"]))

    def test_assignment_rows_match_core_adapter_shape(self):
        projected = project_observation(self.by_name["multiple-activities"])
        rows = persistence_assignments(projected)
        self.assertEqual([row["assignment_ordinal"] for row in rows], [1, 2])
        self.assertEqual({row["primary_key"] for row in rows}, {"slaughter", "processing_and_preparation"})
        self.assertTrue(all(row["mapping_method"] == "direct" and row["mapping_status"] == "mapped" for row in rows))

    def test_real_preview_importer_exposes_persistence_payload_and_crosswalk(self):
        contract = IMPORTER.activity_contract(
            {"activity_codes": ["EB.10.10.99"], "activity_descriptions": ["Slaughterhouse"]},
            "dk.smiley", {"FVST_branchenummer": "EB.10.10.99"})
        self.assertEqual(contract["category"], "slaughter")
        self.assertEqual(contract["activity_categories"], ["slaughter"])
        self.assertEqual(contract["taxonomy_assignment_rows"][0]["primary_key"], "slaughter")
        self.assertEqual(contract["taxonomy_assignment_rows"][0]["source_code"], "EB.10.10.99")
        self.assertEqual(contract["crosswalk_document"]["source_id"], "dk.smiley")
        merged = IMPORTER.merge_activity_contracts([contract, contract])
        self.assertEqual(len(merged["taxonomy_assignment_rows"]), 1)

        belgium = IMPORTER.activity_contract(
            {"activity_codes": ["593"], "activity_categories": ["slaughter"]},
            "be.locations", {"activity_code": "593"})
        self.assertEqual(belgium["activity_categories"], ["slaughter"])
        self.assertEqual(belgium["activity_mapping_status"], "mapped")
        self.assertEqual(belgium["taxonomy_assignment_rows"][0]["mapping_status"], "mapped")


if __name__ == "__main__":
    unittest.main()
