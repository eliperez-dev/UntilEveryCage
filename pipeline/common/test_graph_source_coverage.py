import json
import tempfile
import unittest
from pathlib import Path

from pipeline.common.graph_source_coverage import build_source_graph_coverage


class GraphSourceCoverageTests(unittest.TestCase):
    def test_complete_denominator_marks_missing_runs_not_run(self):
        released_ids = [
            "au.npi.facilities", "au.sa.epa.licensed-activities", "be.locations",
            "br.sif.registered", "ca.ontario.meat-plants", "dk.smiley",
            "es.cat.feed-sandach", "fsa_approved_establishments",
            "fss_approved_establishments", "it.1069-2009", "it.853-2004",
            "nl.nvwa.approved-food", "us.aphis", "us.fsis",
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release_path = root / "release.json"
            release_path.write_text(json.dumps({
                "release_id": "release-2026-10-18",
                "source_ids": released_ids,
                "source_coverage": [{"source_id": item, "row_count": 1} for item in released_ids],
            }), encoding="utf-8")
            graph = root / "some-run" / "candidate-handoff" / "graph-candidates"
            graph.mkdir(parents=True)
            (graph / "manifest.json").write_text(json.dumps({
                "source_ids": ["it.853-2004"], "candidate_rows": 1,
                "facility_identifier_candidates": 1, "organization_identifier_candidates": 0,
                "name_assertion_candidates": 2, "location_role_counts": {"unknown": 1},
                "business_contact_candidates": 0,
            }), encoding="utf-8")
            retained = ["fr.dgal.section-i", "fr.dgal.section-ii", "fr.georisques.icpe.animal",
                        "us.aphis.annual-reports", "us.inspections", "gb.scot.marine.aquaculture"]
            report = build_source_graph_coverage(
                [root], release_manifest_path=release_path, retained_private_source_ids=retained,
            )
            sources = {item["source_id"]: item for item in report["sources"]}
            self.assertEqual(report["release_records"], 14)
            self.assertEqual(sources["it.853-2004"]["graph_status"], "participating")
            self.assertEqual(sources["it.853-2004"]["name_assertion_candidates"], 2)
            self.assertEqual(sources["us.fsis"]["graph_status"], "not-run")
            self.assertEqual(sources["fr.georisques.icpe.animal"]["scope"], "retained-private")
            self.assertEqual(report["privacy"]["private_handoff_values_emitted"], False)


if __name__ == "__main__":
    unittest.main()
