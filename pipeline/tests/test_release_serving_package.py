from __future__ import annotations
import unittest
from pipeline.common import release_serving as serving

class ReleaseServingPackageTests(unittest.TestCase):
    def test_manifest_is_allowlisted_and_excludes_payload_relations(self):
        manifest = serving.package_manifest(release_ids=["v0-public", "v1-public"], migration_inventory_sha256="a" * 64)
        encoded = str(manifest)
        self.assertEqual(manifest["package_state"], "local_rehearsal_only")
        self.assertIn("uec.public_discovery_api_read_model", manifest["data_relation_allowlist"])
        self.assertNotIn("uec.raw_artifacts", manifest["data_relation_allowlist"])
        self.assertIn("uec.raw_artifacts", manifest["data_relation_exclusions"])
        self.assertNotIn("password", encoded.casefold())

    def test_api_role_is_explicitly_read_only(self):
        sql = serving.grant_sql()
        self.assertIn("REVOKE ALL ON ALL TABLES", sql)
        self.assertIn("GRANT SELECT ON", sql)
        self.assertNotIn("GRANT ALL", sql)
        self.assertNotIn("DEFAULT PRIVILEGES", sql)

if __name__ == "__main__": unittest.main()
