import unittest

from pipeline.tests.e2e.fixture import E2EEnvironment


class E2EFixtureLifecycleTests(unittest.TestCase):
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
