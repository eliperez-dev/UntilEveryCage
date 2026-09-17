import unittest
from pathlib import Path


RUNBOOK = Path(__file__).parents[2] / "docs" / "deployment" / "production-operations.md"


class ProductionOperationsRunbookTests(unittest.TestCase):
    def setUp(self):
        self.text = RUNBOOK.read_text(encoding="utf-8")

    def test_runbook_covers_each_recovery_and_operator_lane(self):
        for heading in (
            "## Configuration preflight",
            "## Deploy a release",
            "## Normal stop and graceful drain",
            "## Rollback",
            "## Backup",
            "## Restore",
            "## Incident response",
            "## Fresh-machine setup",
            "## Diagnostics contract",
        ):
            self.assertIn(heading, self.text)

    def test_runbook_preserves_fail_closed_and_ethics_boundaries(self):
        for required in (
            "UEC_RESTRICTION_LEDGER_PATH",
            "UEC_RESTORED_RESTRICTION_SNAPSHOT_PATH",
            "UEC_RELEASE_MANIFEST_SHA256",
            "Automated acquisition or",
            "not publication authorization",
            "Do not put the exposed",
            "not evidence that the service is hosted",
            "Metrics live only for the",
        ):
            self.assertIn(required, self.text)

    def test_runbook_does_not_present_real_credentials_or_public_backup_commands(self):
        self.assertNotIn("postgresql://username", self.text)
        self.assertNotIn("postgresql://password", self.text)
        self.assertNotIn("password=", self.text.lower())
        self.assertIn("<private-database-url>", self.text)
        self.assertIn("synthetic database", self.text)


if __name__ == "__main__":
    unittest.main()
