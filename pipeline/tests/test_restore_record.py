import importlib.util
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT = Path(__file__).parents[1] / "scripts" / "stages" / "restore-record.py"
SPEC = importlib.util.spec_from_file_location("restore_record", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RestoreCommandTests(unittest.TestCase):
    def test_command_inserts_explicit_restore_event(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.transaction.return_value.__enter__.return_value = connection
        record_id = uuid.uuid4()
        with patch.object(MODULE.psycopg, "connect", return_value=connection):
            MODULE.restore("postgresql://test", record_id, "ethics-v1", "maintainer", "reviewed")
        query, params = connection.execute.call_args.args
        self.assertIn("public_access_restored", query)
        self.assertEqual(params[1:], (record_id, "ethics-v1", "maintainer", "reviewed"))


if __name__ == "__main__":
    unittest.main()
