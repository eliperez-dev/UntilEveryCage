import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "maintenance" / "repository_hygiene.py"
SPEC = importlib.util.spec_from_file_location("repository_hygiene", SCRIPT)
HYGIENE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(HYGIENE)


class RepositoryHygieneTests(unittest.TestCase):
    def test_runtime_private_and_oversized_generated_paths_are_rejected(self):
        self.assertTrue(HYGIENE.path_policy_errors("target/preview/state.json"))
        self.assertTrue(HYGIENE.path_policy_errors("data/private/candidate.db"))
        matrix = "static/private-review/readiness-matrix.json"
        self.assertTrue(HYGIENE.path_policy_errors(matrix, HYGIENE.MAX_KNOWN_GENERATED_BYTES + 1))
        self.assertEqual(HYGIENE.path_policy_errors("data/reports/small-report.json", 10), [])

    def test_orphan_temporary_markdown_is_found_but_archive_evidence_is_kept(self):
        files = [
            "docs/README.md",
            "docs/temporary-kickoff.md",
            "docs/linked-sprint-plan.md",
            "docs/archive/sprints/sprint01-integration-execution.md",
        ]
        found = HYGIENE.orphan_temporary_docs(files, {"docs/linked-sprint-plan.md"})
        self.assertEqual(found, ["orphan temporary Markdown: docs/temporary-kickoff.md"])

    def test_hub_and_section_index_internal_links_are_validated(self):
        existing = {"docs/README.md", "docs/section/README.md", "docs/guide.md"}
        self.assertEqual(
            HYGIENE.internal_link_errors("docs/README.md", ["guide.md", "https://example.com"], existing),
            [],
        )
        self.assertEqual(
            HYGIENE.internal_link_errors("docs/section/README.md", ["missing.md"], existing),
            ["docs/section/README.md: broken internal link: missing.md"],
        )
        self.assertEqual(
            HYGIENE.internal_link_errors("docs/notes.md", ["missing.md"], existing),
            [],
        )


if __name__ == "__main__":
    unittest.main()
