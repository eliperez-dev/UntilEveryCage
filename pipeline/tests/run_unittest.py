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
    # This acceptance needs the approved retained Spain cohort, not CI fixtures.
    (
        "test_spain_municipality_geocoding_postgis.SpainMunicipalityGeocodingPostGISTests"
        ".test_bridge_acceptance_and_rejection_cases_rollback",
        "set UEC_SPAIN_MUNICIPALITY_REAL_ACCEPTANCE=true and assigned UEC_DATABASE_URL",
    ),
    (
        "pipeline.tests.test_spain_municipality_geocoding_postgis.SpainMunicipalityGeocodingPostGISTests"
        ".test_bridge_acceptance_and_rejection_cases_rollback",
        "set UEC_SPAIN_MUNICIPALITY_REAL_ACCEPTANCE=true and assigned UEC_DATABASE_URL",
    ),
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
        "sources.germany.test_geocoding.GermanyPrivateGeocodingTests"
        ".test_database_display_bridge_positive_and_negative_cases_rollback",
        "set UEC_GERMANY_REAL_DATA_ACCEPTANCE=true with the assigned private DB URL",
    ),
    (
        "pipeline.sources.germany.test_geocoding.GermanyPrivateGeocodingTests"
        ".test_database_display_bridge_positive_and_negative_cases_rollback",
        "set UEC_GERMANY_REAL_DATA_ACCEPTANCE=true with the assigned private DB URL",
    ),
    (
        "test_enrichment_reconciliation_view.EnrichmentReconciliationViewTests"
        ".test_database_view_reconciles_displays_and_terminal_events_with_rollback",
        "set UEC_ENRICHMENT_RECONCILIATION_REAL_DATA_ACCEPTANCE=true with assigned private DB URL",
    ),
    (
        "pipeline.tests.test_enrichment_reconciliation_view.EnrichmentReconciliationViewTests"
        ".test_database_view_reconciles_displays_and_terminal_events_with_rollback",
        "set UEC_ENRICHMENT_RECONCILIATION_REAL_DATA_ACCEPTANCE=true with assigned private DB URL",
    ),
    (
        "test_germany_candidate_cache_alignment.GermanyCandidateCacheAlignmentTests"
        ".test_database_cache_repair_is_current_audited_and_rollback_safe",
        "set UEC_GERMANY_CACHE_ALIGNMENT_REAL_ACCEPTANCE=true with assigned private DB URL",
    ),
    (
        "pipeline.tests.test_germany_candidate_cache_alignment.GermanyCandidateCacheAlignmentTests"
        ".test_database_cache_repair_is_current_audited_and_rollback_safe",
        "set UEC_GERMANY_CACHE_ALIGNMENT_REAL_ACCEPTANCE=true with assigned private DB URL",
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

# These checks use the approved retained v0 copy, which CI does not contain.
# Keep the exemption scoped to these test IDs, not a reusable skip reason.
ALLOWED_SKIPPED_TESTS.update(
    (
        f"{prefix}test_locationiq_postgis.LocationIqPostgisTests.{method}",
        "assigned disposable real-data database required",
    )
    for prefix in ("", "pipeline.tests.")
    for method in (
        "test_approved_v0_identity_and_counts_are_unchanged",
        "test_both_provider_profiles_coexist_without_changing_default",
        "test_database_rechecks_address_components_and_rejects_bad_points",
        "test_real_unmapped_batch_can_be_staged_without_provider_calls_or_persistent_writes",
    )
)
ALLOWED_SKIPPED_TESTS.update(
    (
        f"{prefix}test_locationiq_postgis.LocationIqPostgisTests."
        "test_real_unmapped_batch_can_be_staged_without_provider_calls_or_persistent_writes",
        "primary allowance is not exhausted",
    )
    for prefix in ("", "pipeline.tests.")
)

# The retained-response proof needs the same approved local V0 copy and has
# been run there. CI has no retained provider responses; exempt these exact
# test IDs only, without accepting this skip reason for other tests.
ALLOWED_SKIPPED_TESTS.update(
    (
        f"{prefix}test_germany_retained_reconciliation_postgis.RetainedGermanyPostgisTests.{method}",
        "assigned disposable real-data database required",
    )
    for prefix in ("", "pipeline.tests.")
    for method in (
        "test_independent_sql_street_rule_matches_python",
        "test_real_replay_is_mapped_idempotent_and_does_not_rewrite_parent_results",
    )
)

# Account history acceptance requires the assigned real-data copy.
ALLOWED_SKIPPED_TESTS.update(
    (f"{prefix}test_geocode_accounts_postgis.GeocodeAccountPostgisTests."
     "test_account_history_quota_rate_and_duplicate_guards_rollback",
     "assigned disposable real-data database required")
    for prefix in ("", "pipeline.tests.")
)

# These six acceptance cases require the approved disposable V0 copy. Their
# exact local run is mandatory; public CI contains only synthetic fixtures.
# Do not add the reason globally: an unrelated/new skip must still fail CI.
ALLOWED_SKIPPED_TESTS.update(
    (
        f"{prefix}e2e.test_secure_community.SecureRelayAcceptance.{method}",
        "assigned disposable v0 URL required",
    )
    for prefix in ("", "pipeline.tests.")
    for method in (
        "test_all_kinds_ciphertext_only_isolated_and_idempotent",
        "test_invalid_plaintext_fields_size_expiry_and_legacy",
        "test_proposed_runtime_grants_cannot_read_source_or_rewrite_evidence",
        "test_replies_status_removal_and_bounded_history",
        "test_secure_and_legacy_share_daily_admission_cap",
        "test_v0_unchanged_and_evidence_updates_forbidden",
    )
)


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
