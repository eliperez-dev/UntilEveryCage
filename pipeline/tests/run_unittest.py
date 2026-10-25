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
    "set UEC_APHIS_POSTGIS_TEST_DATABASE_URL for the disposable PostGIS gate",
}
ALLOWED_SKIPPED_TESTS = {
    (
        "test_spain_geocoding_profile.SpainGeocodingProfileTests"
        ".test_database_display_bridge_positive_and_negative_cases_rollback",
        "set UEC_SPAIN_REAL_DATA_ACCEPTANCE=true with the assigned private DB URL",
    ),
    (
        "pipeline.tests.test_spain_geocoding_profile.SpainGeocodingProfileTests"
        ".test_database_display_bridge_positive_and_negative_cases_rollback",
        "set UEC_SPAIN_REAL_DATA_ACCEPTANCE=true with the assigned private DB URL",
    ),
    (
        "e2e.test_graph_activation_real_italy.RealItalyGraphActivationTests"
        ".test_handoff_is_derived_from_source_native_operator_assertions",
        "set UEC_RUN_REAL_GRAPH_ACTIVATION=1 for approved local real-data acceptance",
    ),
    (
        "e2e.test_graph_activation_real_italy.RealItalyGraphActivationTests"
        ".test_real_name_collision_controls_do_not_create_identity_merges",
        "set UEC_RUN_REAL_GRAPH_ACTIVATION=1 for approved local real-data acceptance",
    ),
    (
        "e2e.test_graph_activation_real_italy.RealItalyGraphActivationTests"
        ".test_full_normal_materializer_replay_is_separately_opt_in",
        "set UEC_RUN_REAL_GRAPH_ACTIVATION=1 for approved local real-data acceptance",
    ),
    (
        "e2e.test_graph_activation_real_italy.RealItalyGraphActivationTests"
        ".test_full_normal_materializer_replay_is_separately_opt_in",
        "full normal materializer replay is expensive and separately opt-in",
    ),
    (
        "e2e.test_graph_activation_real_italy.RealItalyGraphActivationTests"
        ".test_public_api_redacts_identifiers_and_returns_only_eligible_edges",
        "set UEC_RUN_REAL_GRAPH_ACTIVATION=1 for approved local real-data acceptance",
    ),
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
    unexpected = [
        (test.id(), reason)
        for test, reason in result.skipped
        if reason not in ALLOWED_SKIP_REASONS and (test.id(), reason) not in ALLOWED_SKIPPED_TESTS
    ]
    if unexpected:
        for test_id, reason in unexpected:
            print(f"unexpected skipped test: {test_id}: {reason}", file=sys.stderr)
        return 2
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
