import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class SourceRightsMigrationContractTests(unittest.TestCase):
    def test_reserved_migration_is_append_only_and_exactly_scoped(self):
        migration = (ROOT / "migrations" / "041_source_rights_decisions.sql").read_text(encoding="utf-8").lower()
        for token in (
            "source_rights_decisions",
            "source_id",
            "profile",
            "release_id",
            "artifact_id",
            "artifact_sha256",
            "redistribution_status",
            "decision_actor",
            "decision_reference",
            "append_only",
            "validate_source_rights_decision",
        ):
            self.assertIn(token, migration)
        self.assertIn("before update or delete", migration)
        self.assertIn("release_profile is distinct from new.profile", migration)
        self.assertIn("artifact_digest is distinct from new.artifact_sha256", migration)
        self.assertNotIn("attribution", migration.split("create table", 1)[1].split("create index", 1)[0])

    def test_contract_documents_acquisition_and_authorization_boundaries(self):
        docs = (ROOT.parents[0] / "docs" / "architecture" / "source-rights-decisions.md").read_text(encoding="utf-8")
        self.assertIn("Acquisition permission is a separate", docs)
        self.assertIn("does not establish that the actor was authorized", docs)
        self.assertIn("ongoing revocation or expiry", docs)

    def test_all_four_boundaries_use_the_shared_gate(self):
        paths = (
            ROOT / "scripts" / "stages" / "validate-release.py",
            ROOT / "scripts" / "stages" / "promote-release.py",
            ROOT / "scripts" / "stages" / "export-release.py",
            ROOT / "scripts" / "maintenance" / "build_public_discovery_read_model.py",
        )
        for path in paths:
            source = path.read_text(encoding="utf-8")
            self.assertIn("source_rights", source, path.name)
            self.assertIn("release_id", source, path.name)


if __name__ == "__main__":
    unittest.main()
