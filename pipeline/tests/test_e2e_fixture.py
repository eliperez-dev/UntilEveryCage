import unittest
import subprocess
from unittest.mock import patch

from pipeline.tests.e2e.fixture import (
    E2EEnvironment,
    MAX_START_ATTEMPTS,
    _RetryableStartupFailure,
    is_retryable_database_failure,
)


class E2EFixtureLifecycleTests(unittest.TestCase):
    def test_retry_classification_only_accepts_transient_database_lifecycle_errors(self):
        self.assertTrue(is_retryable_database_failure("psql: FATAL:  the database system is shutting down"))
        self.assertTrue(is_retryable_database_failure("connection refused"))
        self.assertFalse(is_retryable_database_failure("psql: ERROR:  relation uec.releases does not exist"))
        self.assertFalse(is_retryable_database_failure("psql: ERROR:  syntax error at or near SELECT"))

    def test_retry_rotates_project_and_ports_after_cleanup(self):
        environment = E2EEnvironment()
        old_identity = (environment.project, environment.db_port, environment.api_port)
        try:
            with patch.object(environment, "stop") as cleanup, patch.object(
                environment, "_container_diagnostics", return_value="redacted diagnostics"
            ):
                with patch.object(
                    environment,
                    "_start_once",
                    side_effect=[_RetryableStartupFailure("database system is shutting down"), "started"],
                ):
                    self.assertEqual(environment.start(migration_files=()), "started")
                    cleanup.assert_called_once()
            self.assertNotEqual(old_identity, (environment.project, environment.db_port, environment.api_port))
            self.assertEqual(environment.start_attempts, 2)
        finally:
            environment.build_temp.cleanup()
            environment.build_temp = None

    def test_failed_attempt_cleanup_removes_compose_volume(self):
        environment = E2EEnvironment()
        try:
            with patch("pipeline.tests.e2e.fixture.subprocess.run") as run:
                environment.stop()
                commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(len(commands), 1)
            self.assertIn("down", commands[0])
            self.assertIn("-v", commands[0])
            self.assertIn(environment.project, commands[0])
        finally:
            environment.build_temp = None

    def test_retry_is_bounded(self):
        self.assertEqual(MAX_START_ATTEMPTS, 2)

    def test_deterministic_start_failure_is_not_retried(self):
        environment = E2EEnvironment()
        try:
            failure = subprocess.CalledProcessError(
                3, ["psql"], output="ERROR: relation uec.releases does not exist", stderr=""
            )
            with patch.object(environment, "stop") as cleanup, patch.object(
                environment, "_start_once", side_effect=failure
            ) as start_once:
                with self.assertRaises(subprocess.CalledProcessError):
                    environment.start(migration_files=())
            start_once.assert_called_once()
            cleanup.assert_called_once()
        finally:
            environment.build_temp.cleanup()
            environment.build_temp = None

    def test_retry_recreates_build_temp_after_failed_start_cleanup(self):
        environment = E2EEnvironment()
        original_target = environment.cargo_target_dir
        environment.build_temp.cleanup()
        environment.build_temp = None

        try:
            environment._ensure_build_temp()
            self.assertIsNotNone(environment.build_temp)
            self.assertNotEqual(environment.cargo_target_dir, original_target)
            self.assertTrue(environment.cargo_target_dir.exists())
        finally:
            environment.build_temp.cleanup()
            environment.build_temp = None


if __name__ == "__main__":
    unittest.main()
