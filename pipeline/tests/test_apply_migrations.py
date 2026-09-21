import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "maintenance" / "apply-migrations.py"
SPEC = importlib.util.spec_from_file_location("apply_migrations", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Cursor:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class Transaction:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        self.connection.transaction_depth += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.connection.transaction_events.append((self.connection.transaction_depth, exc_type is not None))
        self.connection.transaction_depth -= 1
        return False


class Connection:
    def __init__(self):
        self.ledger = {}
        self.transaction_depth = 0
        self.transaction_events = []
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def transaction(self):
        return Transaction(self)

    def execute(self, query, params=None):
        self.executed.append((query, params, self.transaction_depth))
        compact = " ".join(query.split())
        if compact.startswith("SELECT sha256 FROM uec.schema_migrations"):
            return Cursor(self.ledger.get(params[0]))
        if compact.startswith("INSERT INTO uec.schema_migrations"):
            self.ledger[params[0]] = (params[1],)
            return Cursor()
        if "FAIL_MIGRATION" in query:
            raise RuntimeError("synthetic migration failure")
        return Cursor()


class MigrationRunnerTests(unittest.TestCase):
    def test_existing_020_migrations_use_distinct_full_stem_identities(self):
        migration_dir = Path(__file__).parents[1] / "migrations"

        files = MODULE.migration_files(migration_dir)
        names = [path.name for path in files]
        stems = [path.stem for path in files]

        first = "020_release_manifests.sql"
        second = "020_suppression_aware_v2_history.sql"
        self.assertIn(first, names)
        self.assertIn(second, names)
        self.assertNotEqual(Path(first).stem, Path(second).stem)
        self.assertLess(stems.index(Path(first).stem), stems.index(Path(second).stem))

    def test_failed_migration_is_not_recorded_and_retry_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "001_first.sql").write_text("SELECT 1;\n", encoding="utf-8")
            failing = root / "002_second.sql"
            failing.write_text("-- FAIL_MIGRATION\nSELECT 2;\n", encoding="utf-8")
            connection = Connection()
            with patch.object(MODULE.psycopg, "connect", return_value=connection):
                with self.assertRaisesRegex(RuntimeError, "synthetic migration failure"):
                    MODULE.apply("postgresql://test", root)
            self.assertIn("001_first", connection.ledger)
            self.assertNotIn("002_second", connection.ledger)
            self.assertIn((1, True), connection.transaction_events)

            failing.write_text("SELECT 2;\n", encoding="utf-8")
            with patch.object(MODULE.psycopg, "connect", return_value=connection):
                self.assertEqual(MODULE.apply("postgresql://test", root), ["002_second"])
            self.assertIn("002_second", connection.ledger)

    def test_changed_applied_migration_checksum_fails_before_sql_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            migration = root / "001_first.sql"
            migration.write_text("SELECT 1;\n", encoding="utf-8")
            connection = Connection()
            connection.ledger["001_first"] = ("0" * 64,)
            with patch.object(MODULE.psycopg, "connect", return_value=connection):
                with self.assertRaisesRegex(ValueError, "checksum changed"):
                    MODULE.apply("postgresql://test", root)
            self.assertFalse(any("SELECT 1;" in query for query, _, _ in connection.executed))


if __name__ == "__main__":
    unittest.main()
