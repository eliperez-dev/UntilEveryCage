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
        fsis = project_observation({"source_id": "us.fsis", "normalized": {
            "species_slaughtered": {"meat_slaughter": "yes"},
            "processing_activities": {"meat_processing": "yes"}}})
        self.assertEqual(fsis["taxonomy_mapping_method"], "direct")
        self.assertEqual(fsis["taxonomy_display_category"], "slaughter")
        cfia = project_observation({"source_id": "ca.cfia.federal-meat", "normalized": {
            "source_function_codes": "codes_1=a", "activity_categories": ["slaughter"]}})
        self.assertEqual(cfia["taxonomy_mapping_method"], "direct")
        self.assertEqual(cfia["taxonomy_display_category"], "slaughter")

    def test_unknown_partial_conflicting_and_events_fail_closed(self):
        self.assertEqual(project_observation(self.by_name["unknown-code"])["taxonomy_mapping_status"], "unmapped")
        self.assertEqual(project_observation(self.by_name["partial-denmark"])["taxonomy_mapping_status"], "partial")
        self.assertEqual(project_observation(self.by_name["conflicting-france-signals"])["taxonomy_mapping_status"], "conflicting")
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
                       "fsa_approved_establishments", "ca.cfia.federal-meat", "it.853-2004",
                       "es.cat.feed-sandach", "au.npi.facilities"):
            document = crosswalk_document(source)
            self.assertEqual(document["source_id"], source)
            self.assertEqual(document["taxonomy_version"], TAXONOMY_VERSION)
            self.assertTrue(document["crosswalk_version"])
            self.assertTrue(document["ruleset_version"])
            self.assertTrue(document["rules"])
            self.assertTrue(all(rule.get("mapping_method") in {"direct", "derived", "candidate"}
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


if __name__ == "__main__":
    unittest.main()
