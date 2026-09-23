"""Run a unittest suite and reject skips outside the documented allowlist."""

import argparse
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2]))


ALLOWED_SKIP_REASONS = {
    "set UEC_RUN_E2E=1 to run Docker-backed E2E tests",
    "set UEC_RUN_E2E=1",
    "set UEC_RUN_E2E=1 to run Docker-backed worker lifecycle tests",
    "set UEC_RUN_E2E=1 to run Docker-backed D2 E2E tests",
    "set UEC_RUN_E2E=1 and UEC_RUN_CORPUS_RESILIENCE=1 to run the Docker-backed corpus rehearsal",
    "database is older than migration 018; Docker E2E applies the current schema",
    "optional 100k benchmark is opt-in",
    "authorized D6 real private root not configured",
    "set UEC_RUN_D61_REAL=1 after loading an authorized retained handoff",
    "set UEC_RUN_LIVE_BE_FASFC=1 for live refresh or UEC_RUN_LIVE_BE_FASFC_REPLAY=1 for a saved-handoff replay",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-directory", default="pipeline/tests")
    parser.add_argument("--module", action="append", default=[])
    args = parser.parse_args()
    if args.module:
        suite = unittest.TestSuite(
            unittest.defaultTestLoader.loadTestsFromName(module) for module in args.module
        )
    else:
        suite = unittest.defaultTestLoader.discover(args.start_directory)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    unexpected = [(test.id(), reason) for test, reason in result.skipped if reason not in ALLOWED_SKIP_REASONS]
    if unexpected:
        for test_id, reason in unexpected:
            print(f"unexpected skipped test: {test_id}: {reason}", file=sys.stderr)
        return 2
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
