import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "stages" / "promote-release.py"
SPEC = importlib.util.spec_from_file_location("promote_release", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleasePromotionTests(unittest.TestCase):
    def test_only_validated_releases_can_be_promoted(self):
        self.assertTrue(MODULE.can_promote("validated"))
        self.assertFalse(MODULE.can_promote("candidate"))
        self.assertFalse(MODULE.can_promote("promoted"))
        self.assertFalse(MODULE.can_promote("rejected"))


if __name__ == "__main__":
    unittest.main()
