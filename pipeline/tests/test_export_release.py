import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "stages" / "export-release.py"
SPEC = importlib.util.spec_from_file_location("export_release", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleaseExportContractTests(unittest.TestCase):
    def test_export_query_repeats_publication_and_suppression_gates(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for gate in ("release.status='promoted'", "release.test_only IS NOT TRUE", "release.profile=%s", "review.publication_eligible=true", "review.privacy_screening_status='passed'", "public_access_restricted"):
            self.assertIn(gate, source)
        self.assertIn("REPEATABLE READ", source)

    def test_missing_attribution_is_not_called_cleared(self):
        self.assertEqual(MODULE._rights(None), "unknown")
        self.assertEqual(MODULE._rights(""), "unknown")
        self.assertEqual(MODULE._rights("Attribution required"), "attribution_required")


if __name__ == "__main__":
    unittest.main()
