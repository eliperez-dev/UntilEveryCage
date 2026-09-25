"""Keep the canonical parallel-work contract complete and discoverable."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "docs" / "operations" / "parallel-agent-workflow.md"


class AgentWorkflowDocumentationTests(unittest.TestCase):
    def test_workflow_is_linked_from_both_canonical_indexes(self):
        workflow_link = "parallel-agent-workflow.md"
        self.assertIn(workflow_link, (ROOT / "docs/operations/README.md").read_text(encoding="utf-8"))
        hub = (ROOT / "docs/README.md").read_text(encoding="utf-8")
        self.assertIn("operations/parallel-agent-workflow.md", hub)

    def test_contract_covers_assignment_evidence_and_integration_boundaries(self):
        text = WORKFLOW.read_text(encoding="utf-8").lower()
        for required in (
            "exclusive ownership", "source id", "source_registry.json",
            "source-status.json", "changed paths", "exact commands/results",
            "strict live private e2e", "zero public rows", "disposable private database",
            "standard pipeline", "never", "push or integrate", "privacy approval",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
