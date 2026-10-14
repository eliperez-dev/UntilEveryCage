import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "stages" / "activate-aphis-mailing-locality-geoapify.py"
SPEC = importlib.util.spec_from_file_location("aphis_locality_activation", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AphisMailingLocalityActivationTests(unittest.TestCase):
    def test_query_is_state_scoped_and_does_not_reuse_different_states(self):
        self.assertNotEqual(MODULE.locality_query("Exampletown", "TX"), MODULE.locality_query("Exampletown", "CA"))

    def test_invalid_state_is_rejected_before_any_database_work(self):
        with self.assertRaises(ValueError):
            MODULE.locality_query("Exampletown", "ZZ")


if __name__ == "__main__":
    unittest.main()
