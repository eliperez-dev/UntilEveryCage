import json
import unittest
from pathlib import Path

from pipeline.taxonomy import (
    DISPLAY_PRECEDENCE,
    MAPPING_METHODS,
    MAPPING_STATUSES,
    PRIMARY_KEYS,
    TAXONOMY_VERSION,
    TaxonomyAssignment,
    TaxonomyContractError,
    assignment_set_key,
    canonical_assignments,
    choose_display_category,
    crosswalk_sha256,
    primary_categories,
    validate_crosswalk,
)


def row(primary, *, status="mapped", method="direct", leaf=None, code="A", label="Original"):
    return TaxonomyAssignment(
        primary_key=primary,
        leaf_key=leaf,
        leaf_label="Source-facing leaf" if leaf else None,
        source_code_reference="/activity/code",
        source_label_reference="/activity/label",
        source_code=code,
        source_label=label,
        method=method,
        status=status,
        taxonomy_version=TAXONOMY_VERSION,
        crosswalk_version="source-crosswalk-v3",
        ruleset_version="adapter-rules-v2",
        observation_id="observation-1",
        source_record_id="record-1",
        artifact_id="artifact-1",
    )


class TaxonomyContractTests(unittest.TestCase):
    def test_frozen_enums_and_precedence(self):
        self.assertEqual(PRIMARY_KEYS, (
            "animal_keeping_and_production", "slaughter", "processing_and_preparation",
            "research_and_animal_use", "other_regulated_premises", "unclassified",
        ))
        self.assertEqual(MAPPING_METHODS, ("direct", "derived", "candidate"))
        self.assertEqual(MAPPING_STATUSES, (
            "mapped", "partial", "unmapped", "unclassified", "conflicting", "ambiguous",
        ))
        self.assertEqual(DISPLAY_PRECEDENCE, (
            "slaughter", "research_and_animal_use", "animal_keeping_and_production",
            "processing_and_preparation", "other_regulated_premises", "unclassified",
        ))

    def test_multi_primary_display_and_canonical_order_ignore_input_order(self):
        input_rows = [
            row("animal_keeping_and_production", leaf="cattle-rearing", code="P1"),
            row("slaughter", leaf="red-meat", code="S9"),
            row("processing_and_preparation", code="X2"),
        ]
        reordered = list(reversed(input_rows))
        self.assertEqual(canonical_assignments(input_rows), canonical_assignments(reordered))
        self.assertEqual(choose_display_category(input_rows), "slaughter")
        self.assertEqual(primary_categories(input_rows), (
            "animal_keeping_and_production", "processing_and_preparation", "slaughter",
        ))
        self.assertEqual(assignment_set_key(input_rows), assignment_set_key(reordered))
        partial = [row("slaughter", status="partial"), row("unclassified", status="unmapped", code="U")]
        self.assertEqual(primary_categories(partial), ("slaughter", "unclassified"))

    def test_duplicates_rejected_and_identical_projection_key_is_idempotent(self):
        assignment = row("slaughter")
        with self.assertRaisesRegex(TaxonomyContractError, "duplicate"):
            canonical_assignments([assignment, assignment])
        self.assertEqual(assignment_set_key([assignment]), assignment_set_key([assignment]))

    def test_unknown_and_conflicting_values_are_preserved_as_unclassified(self):
        unknown = row("unclassified", status="unmapped", code="UNKNOWN-997", label="Unrecognized source label")
        conflict = row("unclassified", status="conflicting", code="D-4", label="Conflicting source label")
        self.assertEqual(choose_display_category([unknown]), "unclassified")
        self.assertEqual(unknown.source_code, "UNKNOWN-997")
        self.assertEqual(unknown.source_label, "Unrecognized source label")
        self.assertEqual(conflict.source_code, "D-4")
        with self.assertRaisesRegex(TaxonomyContractError, "unresolved"):
            row("slaughter", status="conflicting")
        with self.assertRaisesRegex(TaxonomyContractError, "candidate"):
            row("slaughter", method="candidate", status="mapped")

    def test_lineage_and_versions_must_agree_within_assignment_set(self):
        second = TaxonomyAssignment(**{**row("slaughter").__dict__, "observation_id": "observation-2"})
        with self.assertRaisesRegex(TaxonomyContractError, "lineage"):
            canonical_assignments([row("slaughter"), second])
        self.assertEqual(row("slaughter").taxonomy_version, "uec-taxonomy-v1")
        self.assertEqual(row("slaughter").crosswalk_version, "source-crosswalk-v3")

    def test_versioned_crosswalk_requires_exact_selectors_and_required_version(self):
        valid = {
            "source_id": "dk.smiley",
            "taxonomy_version": TAXONOMY_VERSION,
            "crosswalk_version": "dk-smiley-crosswalk-v1",
            "ruleset_version": "adapter-rules-v4",
            "rules": [{
                "source_codes": ["SLA-01"], "source_labels": [],
                "primary_keys": ["slaughter"], "leaf_key": "red-meat-slaughter",
                "leaf_label": "Red meat slaughter", "method": "direct", "status": "mapped",
            }],
        }
        self.assertIs(validate_crosswalk(valid), valid)
        self.assertEqual(crosswalk_sha256(valid), crosswalk_sha256(json.loads(json.dumps(valid))))
        self.assertEqual(len(crosswalk_sha256(valid)), 64)
        with self.assertRaisesRegex(TaxonomyContractError, "crosswalk_version"):
            validate_crosswalk({key: value for key, value in valid.items() if key != "crosswalk_version"})
        bad_unknown = {**valid, "rules": [{
            "source_codes": ["U"], "source_labels": [], "primary_keys": ["slaughter"],
            "method": "derived", "status": "unmapped",
        }]}
        with self.assertRaisesRegex(TaxonomyContractError, "guesses"):
            validate_crosswalk(bad_unknown)

    def test_database_migration_is_additive_normalized_and_append_only(self):
        migration = (Path(__file__).parents[1] / "migrations" / "055_versioned_taxonomy_assignments.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE uec.taxonomy_crosswalks", migration)
        self.assertIn("CREATE TABLE uec.observation_taxonomy_assignment_sets", migration)
        self.assertIn("CREATE TABLE uec.observation_taxonomy_assignments", migration)
        self.assertIn("UNIQUE (observation_id, taxonomy_version, crosswalk_version, ruleset_version)", migration)
        self.assertIn("REFERENCES uec.observations(observation_id, source_record_id)", migration)
        self.assertIn("REFERENCES uec.source_records(source_record_id, source_id, artifact_id)", migration)
        for field in (
            "primary_key", "leaf_key", "leaf_label", "source_code_reference", "source_label_reference",
            "source_code", "source_label", "mapping_method", "mapping_status",
            "taxonomy_version", "crosswalk_version", "ruleset_version", "artifact_id", "observation_id",
        ):
            self.assertIn(field, migration)
        self.assertIn("taxonomy_assignments_append_only", migration)
        self.assertNotIn("UPDATE uec.observations", migration)
        self.assertNotIn("classification_category =", migration)

    def test_crosswalk_schema_is_machine_readable_and_requires_its_version(self):
        schema = json.loads((Path(__file__).parent / "crosswalk-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["taxonomy_version"]["const"], TAXONOMY_VERSION)
        self.assertIn("crosswalk_version", schema["required"])
        self.assertEqual(schema["properties"]["rules"]["items"]["properties"]["method"]["enum"], list(MAPPING_METHODS))
        self.assertEqual(schema["properties"]["rules"]["items"]["properties"]["status"]["enum"], list(MAPPING_STATUSES))


if __name__ == "__main__":
    unittest.main()
