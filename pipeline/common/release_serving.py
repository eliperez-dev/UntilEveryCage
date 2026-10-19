"""Allowlisted serving-package metadata and least-privilege grants.

This is intentionally a relation contract, not a database backup.  A serving
exporter may include only this public release/read-model closure after applying
the normal schema migrations; raw artifacts, raw fields, acquisition payloads,
and geocoder queries/responses are expressly outside the package.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


API_RELATIONS = (
    "uec.public_discovery_api_read_model", "uec.public_discovery_api_candidate_read_model",
    "uec.public_discovery_read_models", "uec.public_discovery_read_model_rows",
    "uec.release_manifests", "uec.public_release_history", "uec.releases",
    "uec.public_suppression_generation", "uec.record_access_current",
    "uec.public_access_restricted", "uec.suppression_case_current",
    "uec.observation_taxonomy_assignment_sets", "uec.observation_taxonomy_assignments",
    "uec.graph_public_relationships", "uec.graph_public_claims",
)

# These are evidence/payload relations which must never be copied into the
# deployable serving package.  Their schema may exist from migrations, but no
# data is exported and the API role receives no grants.
FORBIDDEN_DATA_RELATIONS = (
    "uec.raw_artifacts", "uec.source_records", "uec.acquisition_runs",
    "uec.acquisition_run_artifacts", "uec.geocode_results", "uec.geocode_jobs",
    "uec.geocode_job_events", "uec.organization_relationship_observations",
    "uec.graph_evidence_events", "uec.graph_evidence_links",
)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()


def package_manifest(*, release_ids: list[str], migration_inventory_sha256: str) -> dict[str, Any]:
    if not release_ids or len(release_ids) != len(set(release_ids)):
        raise ValueError("release IDs must be a non-empty unique set")
    if len(migration_inventory_sha256) != 64:
        raise ValueError("migration inventory digest is required")
    manifest = {
        "schema_version": "uec-serving-package-v1",
        "package_state": "local_rehearsal_only",
        "release_ids": sorted(release_ids),
        "migration_inventory_sha256": migration_inventory_sha256,
        "data_relation_allowlist": list(API_RELATIONS),
        "data_relation_exclusions": list(FORBIDDEN_DATA_RELATIONS),
        "derivative_notice": "Serving package contains manifest-bound public read models and live public gates, not source artifacts or original acquisition payloads.",
    }
    manifest["package_sha256"] = canonical_sha256(manifest)
    return manifest


def grant_sql(api_role: str = "uec_api_runtime", release_role: str = "uec_release_operator",
              migration_role: str = "uec_migrator") -> str:
    for role in (api_role, release_role, migration_role):
        if not role.replace("_", "").isalnum():
            raise ValueError("role names must be simple identifiers")
    api_relations = ", ".join(API_RELATIONS)
    # No broad ALL TABLES/DEFAULT PRIVILEGES grant: new relations require an
    # explicit review and package-contract update.
    return "\n".join((
        "BEGIN;",
        f"REVOKE ALL ON SCHEMA uec FROM {api_role};",
        f"REVOKE ALL ON ALL TABLES IN SCHEMA uec FROM {api_role};",
        f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA uec FROM {api_role};",
        f"GRANT USAGE ON SCHEMA uec TO {api_role};",
        f"GRANT SELECT ON {api_relations} TO {api_role};",
        f"REVOKE ALL ON SCHEMA uec FROM {release_role};",
        f"GRANT USAGE ON SCHEMA uec TO {release_role};",
        f"GRANT SELECT, INSERT ON uec.releases, uec.release_members, uec.release_manifests, uec.public_release_history TO {release_role};",
        f"REVOKE ALL ON SCHEMA uec FROM {migration_role};",
        f"GRANT USAGE, CREATE ON SCHEMA uec TO {migration_role};",
        "COMMIT;",
        "",
    ))
