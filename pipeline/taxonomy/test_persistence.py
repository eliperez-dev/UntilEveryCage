import unittest

from pipeline.taxonomy.persistence import persist_preview_candidate_assignment_set, persist_uec_assignment_set
from pipeline.taxonomy_crosswalk import crosswalk_document, persistence_assignments, project_observation


class FakeConnection:
    def __init__(self):
        self.statements = []
        self.rows = []
        self.digest = None

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        if "INSERT INTO" in sql and "taxonomy_crosswalks" in sql:
            self.digest = params[5]
        if "SELECT definition_sha256" in sql:
            return FakeCursor((self.digest,))
        if "RETURNING assignment_set_id" in sql:
            return FakeCursor(("assignment-set",))
        if "SELECT assignment_set_id," in sql:
            return FakeCursor(None)
        if "SELECT assignment_ordinal" in sql:
            return FakeCursor(None, all_rows=[])
        if "INSERT INTO" in sql and "assignment_ordinal" in sql and "mapping_status" in sql:
            self.rows.append(params)
        return FakeCursor(None)

    def executemany(self, sql, rows):
        self.rows.extend(rows)


class FakeCursor:
    def __init__(self, row, all_rows=None):
        self.row = row
        self.all_rows = all_rows

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.all_rows if self.all_rows is not None else ([] if self.row is None else [self.row])


class TaxonomyPersistenceTests(unittest.TestCase):
    def test_preview_writer_keeps_preview_ids_in_private_schema(self):
        projected = project_observation({"source_id": "dk.smiley", "normalized": {
            "activity_codes": ["EB.10.10.99"], "activity_descriptions": ["Slaughterhouse"],
        }, "source_values": {"FVST_branchenummer": "EB.10.10.99"}})
        document = crosswalk_document("dk.smiley")
        connection = FakeConnection()
        assignment_set_id = persist_preview_candidate_assignment_set(
            connection, candidate_id="candidate-1", representative_observation_id="preview-observation-1",
            snapshot_sha256="a" * 64, source_id="dk.smiley", document=document,
            assignment_rows=persistence_assignments(projected),
        )
        self.assertEqual(assignment_set_id, "assignment-set")
        self.assertTrue(any("real_preview.taxonomy_crosswalks" in sql for sql, _ in connection.statements))
        self.assertTrue(any("real_preview.candidate_taxonomy_assignment_sets" in sql for sql, _ in connection.statements))
        self.assertTrue(any("real_preview.candidate_taxonomy_assignments" in sql for sql, _ in connection.statements))
        self.assertFalse(any("uec.observation_taxonomy" in sql for sql, _ in connection.statements))
        self.assertEqual(connection.rows[0][2], "slaughter")

    def test_uec_writer_requires_and_uses_uec_lineage(self):
        projected = project_observation({"source_id": "dk.smiley", "normalized": {
            "activity_codes": ["EB.10.10.99"], "activity_descriptions": ["Slaughterhouse"],
        }, "source_values": {"FVST_branchenummer": "EB.10.10.99"}})
        connection = FakeConnection()
        assignment_set_id = persist_uec_assignment_set(
            connection, observation_id="observation-1", source_record_id="record-1", artifact_id="artifact-1",
            document=crosswalk_document("dk.smiley"), assignment_rows=persistence_assignments(projected),
        )
        self.assertEqual(assignment_set_id, "assignment-set")
        self.assertTrue(any("uec.observation_taxonomy_assignment_sets" in sql for sql, _ in connection.statements))
        self.assertEqual(connection.rows[0][2], "slaughter")

    def test_candidate_rows_cannot_be_confirmed(self):
        projection = project_observation({"source_id": "au.npi.facilities", "normalized": {"activities": ["candidate"]}})
        self.assertEqual(projection["taxonomy_mapping_status"], "ambiguous")
        rows = persistence_assignments(projection)
        self.assertTrue(all(row["primary_key"] == "unclassified" for row in rows))
        self.assertTrue(all(row["mapping_method"] == "candidate" for row in rows))
        self.assertTrue(all(row["mapping_status"] == "ambiguous" for row in rows))


if __name__ == "__main__":
    unittest.main()
