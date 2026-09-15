import importlib.util
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "stages" / "lift-suppression.py"
SPEC = importlib.util.spec_from_file_location("lift_suppression", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LiftSuppressionTests(unittest.TestCase):
    def test_lift_is_an_append_only_case_event(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.transaction.return_value.__enter__.return_value = connection
        connection.execute.return_value.fetchone.side_effect = [("privacy",)]
        case_id = uuid.uuid4()
        with patch.object(MODULE.psycopg, "connect", return_value=connection):
            MODULE.lift("postgresql://test", case_id, "ethics-v1", "maintainer")
        queries = [call.args[0] for call in connection.execute.call_args_list]
        self.assertTrue(any("event_type, reason_category" in query and "'lifted'" in query for query in queries))
        self.assertTrue(any("public_access_restored" in query for query in queries))
        self.assertFalse(any("UPDATE uec.suppression_cases" in query for query in queries))


if __name__ == "__main__":
    unittest.main()
