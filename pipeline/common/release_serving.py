"""Selected-column export contract for an isolated public serving database.

This deliberately avoids ``pg_dump``: a package contains only a named public
release's read model plus the current gate closure needed to keep it safe.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()


@dataclass(frozen=True)
class ExportSpec:
    relation: str
    columns: tuple[str, ...]
    query: str


def _selected(sql: str) -> str:
    return "WITH selected AS (SELECT unnest($1::text[]) release_id) " + sql


MODEL_COLUMNS = (
    "release_id", "facility_id", "observation_id", "source_record_id", "canonical_name", "country_code", "postal_code", "city", "display_location", "display_precision", "display_label", "geocoding_status", "geocoder_provider", "geocoded_at", "classification_category", "observed_at", "first_observed_at", "provenance_origin_type", "provenance_source_id", "provenance_source_name", "provenance_source_url", "provenance_retrieved_at", "source_rights_status", "geometry_provenance", "public_detail", "public_search_text",
)


def export_specs() -> tuple[ExportSpec, ...]:
    """Explicit safe-column closure. $1 is the selected release-id array."""
    records = "SELECT DISTINCT row.source_record_id FROM uec.public_discovery_read_model_rows row WHERE row.release_id=ANY($1)"
    return (
        ExportSpec("uec.schema_migrations", ("version", "sha256", "applied_at"), "SELECT version,sha256,applied_at FROM uec.schema_migrations"),
        ExportSpec("uec.releases", ("release_id", "created_at", "status", "ruleset_version", "summary", "profile", "test_only"), _selected("SELECT r.release_id,r.created_at,r.status,r.ruleset_version,r.summary,r.profile,r.test_only FROM uec.releases r JOIN selected s USING(release_id)")),
        ExportSpec("uec.release_manifests", ("release_id", "manifest", "manifest_sha256", "created_at"), _selected("SELECT m.release_id,m.manifest,m.manifest_sha256,m.created_at FROM uec.release_manifests m JOIN selected s USING(release_id)")),
        ExportSpec("uec.public_release_history", ("release_id", "profile", "published_at"), _selected("SELECT h.release_id,h.profile,h.published_at FROM uec.public_release_history h JOIN selected s USING(release_id)")),
        ExportSpec("uec.public_discovery_read_models", ("release_id", "manifest_sha256", "content_sha256", "row_count", "built_at"), _selected("SELECT m.release_id,m.manifest_sha256,m.content_sha256,m.row_count,m.built_at FROM uec.public_discovery_read_models m JOIN selected s USING(release_id)")),
        ExportSpec("uec.public_discovery_read_model_rows", MODEL_COLUMNS, _selected("SELECT " + ",".join(MODEL_COLUMNS) + " FROM uec.public_discovery_read_model_rows row JOIN selected s USING(release_id)")),
        ExportSpec("uec.public_suppression_generation", ("singleton", "generation"), "SELECT singleton,generation FROM uec.public_suppression_generation"),
        # Hashes and timestamps stay truthful; payload/location fields are replaced with an explicit derivative marker.
        ExportSpec("uec.raw_artifacts", ("artifact_id", "storage_key", "sha256", "byte_size", "media_type", "retrieved_at", "publication_date", "retention_status"), "WITH records AS (" + records + ") SELECT DISTINCT a.artifact_id,NULL::text,a.sha256,NULL::bigint,a.media_type,a.retrieved_at,a.publication_date,'not_retained' FROM uec.raw_artifacts a JOIN uec.source_records r ON r.artifact_id=a.artifact_id JOIN records USING(source_record_id)"),
        ExportSpec("uec.sources", ("source_id", "country_code", "name", "official_url", "access_method", "cadence", "status", "attribution", "created_at", "origin_type"), "WITH records AS (" + records + ") SELECT DISTINCT s.source_id,s.country_code,s.name,s.official_url,s.access_method,s.cadence,s.status,s.attribution,s.created_at,s.origin_type FROM uec.sources s JOIN uec.source_records r USING(source_id) JOIN records USING(source_record_id)"),
        ExportSpec("uec.source_records", ("source_record_id", "source_id", "source_record_key", "artifact_id", "raw_fields", "parsed_at", "source_state"), "WITH records AS (" + records + ") SELECT r.source_record_id,r.source_id,r.source_record_key,r.artifact_id,jsonb_build_object('serving_package',jsonb_build_object('payload','redacted','reason','raw_source_payload_excluded')),r.parsed_at,r.source_state FROM uec.source_records r JOIN records USING(source_record_id)"),
        ExportSpec("uec.facilities", ("facility_id", "canonical_name", "country_code", "street_address", "postal_code", "city", "location", "created_at"), _selected("SELECT DISTINCT f.facility_id,f.canonical_name,f.country_code,NULL::text,NULL::text,f.city,NULL::geography,f.created_at FROM uec.facilities f JOIN uec.public_discovery_read_model_rows row USING(facility_id) JOIN selected s USING(release_id)")),
        ExportSpec("uec.observations", ("observation_id", "facility_id", "source_record_id", "observed_at", "observation", "classification", "ruleset_id", "rule_id", "classification_category", "classification_review_status", "default_visible", "optional_filter", "coordinate", "coordinate_method", "coordinate_precision", "coordinate_review_status", "first_observed_at"), "WITH records AS (" + records + ") SELECT o.observation_id,o.facility_id,o.source_record_id,o.observed_at,jsonb_build_object('serving_package',jsonb_build_object('payload','redacted')),jsonb_build_object('serving_package',jsonb_build_object('payload','redacted')),o.ruleset_id,o.rule_id,o.classification_category,o.classification_review_status,o.default_visible,NULL::text,NULL::geography,NULL::text,NULL::text,o.coordinate_review_status,o.first_observed_at FROM uec.observations o JOIN records USING(source_record_id)"),
        ExportSpec("uec.facility_source_links", ("facility_id", "source_record_id", "match_method", "review_status", "decided_at"), "WITH records AS (" + records + ") SELECT l.facility_id,l.source_record_id,l.match_method,l.review_status,l.decided_at FROM uec.facility_source_links l JOIN records USING(source_record_id)"),
        ExportSpec("uec.record_access_events", ("access_event_id", "source_record_id", "action", "reason_category", "policy_version", "maintainer", "note", "occurred_at"), "WITH records AS (" + records + ") SELECT e.access_event_id,e.source_record_id,e.action,e.reason_category,e.policy_version,e.maintainer,NULL::text,e.occurred_at FROM uec.record_access_events e JOIN records USING(source_record_id)"),
        ExportSpec("uec.publication_review_events", ("publication_review_event_id", "source_record_id", "factual_review_status", "privacy_screening_status", "maintainer_approval", "publication_eligible", "reviewer_role", "note", "reviewed_at", "release_id"), "WITH records AS (" + records + ") SELECT DISTINCT e.publication_review_event_id,e.source_record_id,e.factual_review_status,e.privacy_screening_status,e.maintainer_approval,e.publication_eligible,e.reviewer_role,NULL::text,e.reviewed_at,e.release_id FROM uec.publication_review_events e JOIN uec.publication_review_release_scopes scope USING(publication_review_event_id) JOIN records USING(source_record_id) WHERE scope.release_id=ANY($1)"),
        ExportSpec("uec.publication_review_release_scopes", ("publication_review_event_id", "release_id"), _selected("SELECT DISTINCT scope.publication_review_event_id,scope.release_id FROM uec.publication_review_release_scopes scope JOIN uec.publication_review_events event USING(publication_review_event_id) JOIN uec.public_discovery_read_model_rows row ON row.source_record_id=event.source_record_id JOIN selected s ON s.release_id=scope.release_id")),
        ExportSpec("uec.facility_lifecycle_events", ("lifecycle_event_id", "facility_id", "status", "effective_at", "source_record_id", "evidence_note", "created_at"), _selected("SELECT DISTINCT e.lifecycle_event_id,e.facility_id,e.status,e.effective_at,e.source_record_id,NULL::text,e.created_at FROM uec.facility_lifecycle_events e JOIN uec.public_discovery_read_model_rows row ON row.facility_id=e.facility_id JOIN selected s USING(release_id)")),
        ExportSpec("uec.taxonomy_crosswalks", ("source_id", "taxonomy_version", "crosswalk_version", "ruleset_version", "definition", "definition_sha256", "created_at"), _selected("SELECT DISTINCT c.source_id,c.taxonomy_version,c.crosswalk_version,c.ruleset_version,c.definition,c.definition_sha256,c.created_at FROM uec.taxonomy_crosswalks c JOIN uec.observation_taxonomy_assignment_sets sets ON sets.source_id=c.source_id AND sets.taxonomy_version=c.taxonomy_version AND sets.crosswalk_version=c.crosswalk_version AND sets.ruleset_version=c.ruleset_version JOIN uec.public_discovery_read_model_rows row ON row.observation_id=sets.observation_id JOIN selected s USING(release_id)")),
        ExportSpec("uec.release_cohort_review_documents", ("release_id", "profile", "ruleset_version", "freeze_sha256", "inventory_sha256", "member_sha256", "member_count", "document_sha256", "reviewer_actor", "reviewer_role", "reviewed_at", "review_method", "review_evidence_reference", "recorded_at"), _selected("SELECT d.release_id,d.profile,d.ruleset_version,d.freeze_sha256,d.inventory_sha256,d.member_sha256,d.member_count,d.document_sha256,d.reviewer_actor,d.reviewer_role,d.reviewed_at,d.review_method,d.review_evidence_reference,d.recorded_at FROM uec.release_cohort_review_documents d JOIN selected s USING(release_id)")),
        ExportSpec("uec.release_cohort_review_scopes", ("release_id", "source_id", "artifact_id", "artifact_sha256", "factual_review_status", "privacy_screening_status", "privacy_method", "privacy_evidence_reference", "maintainer_approval", "publication_eligible", "project_approval_method", "project_approval_evidence_reference", "redistribution_status", "rights_actor", "rights_reference", "rights_decided_at", "classification_interpretation_status", "classification_method", "classification_evidence_reference", "geometry_interpretation_status", "geometry_method", "geometry_evidence_reference", "taxonomy_version", "crosswalk_version", "classification_ruleset_version", "excluded_display_categories", "exclusion_reason_category", "exclusion_policy_reference", "excluded_source_record_ids"), _selected("SELECT DISTINCT s.release_id,s.source_id,s.artifact_id,s.artifact_sha256,s.factual_review_status,s.privacy_screening_status,s.privacy_method,s.privacy_evidence_reference,s.maintainer_approval,s.publication_eligible,s.project_approval_method,s.project_approval_evidence_reference,s.redistribution_status,s.rights_actor,s.rights_reference,s.rights_decided_at,s.classification_interpretation_status,s.classification_method,s.classification_evidence_reference,s.geometry_interpretation_status,s.geometry_method,s.geometry_evidence_reference,s.taxonomy_version,s.crosswalk_version,s.classification_ruleset_version,s.excluded_display_categories,s.exclusion_reason_category,s.exclusion_policy_reference,s.excluded_source_record_ids FROM uec.release_cohort_review_scopes s JOIN selected chosen USING(release_id) JOIN uec.source_records record ON record.source_id=s.source_id AND record.artifact_id=s.artifact_id JOIN uec.public_discovery_read_model_rows row ON row.source_record_id=record.source_record_id AND row.release_id=s.release_id")),
        ExportSpec("uec.observation_taxonomy_assignment_sets", ("assignment_set_id", "observation_id", "source_record_id", "source_id", "artifact_id", "taxonomy_version", "crosswalk_version", "ruleset_version", "display_category", "created_at"), _selected("SELECT DISTINCT sets.assignment_set_id,sets.observation_id,sets.source_record_id,sets.source_id,sets.artifact_id,sets.taxonomy_version,sets.crosswalk_version,sets.ruleset_version,sets.display_category,sets.created_at FROM uec.observation_taxonomy_assignment_sets sets JOIN uec.public_discovery_read_model_rows row USING(observation_id) JOIN selected s USING(release_id)")),
        ExportSpec("uec.observation_taxonomy_assignments", ("assignment_set_id", "assignment_ordinal", "primary_key", "leaf_key", "leaf_label", "source_code_reference", "source_label_reference", "source_code", "source_label", "mapping_method", "mapping_status"), _selected("SELECT DISTINCT a.assignment_set_id,a.assignment_ordinal,a.primary_key,a.leaf_key,a.leaf_label,a.source_code_reference,a.source_label_reference,a.source_code,a.source_label,a.mapping_method,a.mapping_status FROM uec.observation_taxonomy_assignments a JOIN uec.observation_taxonomy_assignment_sets sets USING(assignment_set_id) JOIN uec.public_discovery_read_model_rows row USING(observation_id) JOIN selected s USING(release_id)")),
        ExportSpec("uec.graph_projection_generation", ("singleton", "generation"), "SELECT singleton,generation FROM uec.graph_projection_generation"),
        ExportSpec("uec.graph_public_projection_builds", ("projection_id", "release_id", "projection_version", "edge_generation", "release_manifest_sha256", "suppression_generation", "status", "edge_count", "created_at", "completed_at", "active"), _selected("SELECT b.projection_id,b.release_id,b.projection_version,b.edge_generation,b.release_manifest_sha256,b.suppression_generation,b.status,b.edge_count,b.created_at,b.completed_at,b.active FROM uec.graph_public_projection_builds b JOIN selected s USING(release_id) WHERE b.active AND b.status='completed'")),
        ExportSpec("uec.graph_public_projection_edges", ("projection_id", "release_id", "connection_edge_id", "from_endpoint_id", "from_entity_id", "from_entity_type", "from_source_id", "from_identifier_type", "to_endpoint_id", "to_entity_id", "to_entity_type", "to_source_id", "to_identifier_type", "relationship_type", "connection_type", "confidence", "confidence_band", "signal_explanation", "match_method", "observed_at", "computed_at", "ruleset_version", "conflicting"), _selected("SELECT e.projection_id,e.release_id,e.connection_edge_id,e.from_endpoint_id,e.from_entity_id,e.from_entity_type,e.from_source_id,e.from_identifier_type,e.to_endpoint_id,e.to_entity_id,e.to_entity_type,e.to_source_id,e.to_identifier_type,e.relationship_type,e.connection_type,e.confidence,e.confidence_band,e.signal_explanation,e.match_method,e.observed_at,e.computed_at,e.ruleset_version,e.conflicting FROM uec.graph_public_projection_edges e JOIN uec.graph_public_projection_builds b USING(projection_id,release_id) JOIN selected s USING(release_id) WHERE b.active AND b.status='completed'")),
        ExportSpec("uec.graph_public_projection_edge_supports", ("projection_id", "connection_edge_id", "source_record_id", "source_id", "artifact_id"), _selected("SELECT support.projection_id,support.connection_edge_id,support.source_record_id,support.source_id,support.artifact_id FROM uec.graph_public_projection_edge_supports support JOIN uec.graph_public_projection_builds b USING(projection_id) JOIN selected s ON s.release_id=b.release_id WHERE b.active AND b.status='completed'")),
        ExportSpec("uec.graph_public_projection_endpoints", ("projection_id", "endpoint_id", "public_entity_id", "entity_type", "source_id", "identifier_type"), _selected("SELECT endpoint.projection_id,endpoint.endpoint_id,endpoint.public_entity_id,endpoint.entity_type,endpoint.source_id,endpoint.identifier_type FROM uec.graph_public_projection_endpoints endpoint JOIN uec.graph_public_projection_builds b USING(projection_id) JOIN selected s ON s.release_id=b.release_id WHERE b.active AND b.status='completed'")),
        ExportSpec("uec.graph_public_projection_anchors", ("projection_id", "endpoint_id", "source_record_id", "facility_id"), _selected("SELECT anchor.projection_id,anchor.endpoint_id,anchor.source_record_id,anchor.facility_id FROM uec.graph_public_projection_anchors anchor JOIN uec.graph_public_projection_builds b USING(projection_id) JOIN selected s ON s.release_id=b.release_id WHERE b.active AND b.status='completed'")),
    )


FORBIDDEN_DATA_RELATIONS = ("uec.acquisition_runs", "uec.acquisition_run_artifacts", "uec.geocode_results", "uec.geocode_jobs", "uec.geocode_job_events", "uec.graph_evidence_events", "uec.graph_evidence_links", "uec.graph_connection_edges", "uec.graph_record_release_bindings", "uec.source_entity_identifiers", "uec.graph_ingest_runs", "uec.graph_ingest_items", "uec.graph_edge_materialization_runs", "uec.claim_support")
SERVING_SCHEMA_OMISSIONS = (
    "TRIGGER uec.geocode_results.aaa_aphis_mailing_locality_geoapify_display: private acquisition preview callback",
    "TRIGGER uec.geocode_results.geocode_results_geoapify_preview_display: private geocoder preview callback",
)
# Handler-facing relations only.  The support tables in the export are read by
# security-definer views, never directly by the network role.
API_RELATIONS = (
    "uec.schema_migrations",
    "uec.releases", "uec.release_manifests", "uec.public_release_history",
    "uec.public_discovery_read_models", "uec.public_discovery_read_model_rows",
    "uec.public_suppression_generation", "uec.observation_taxonomy_assignment_sets",
    "uec.observation_taxonomy_assignments", "uec.public_discovery_api_read_model",
    "uec.public_discovery_api_candidate_read_model", "uec.map_facilities_public_discovery_read_model",
    "uec.map_facilities_display_history", "uec.publication_review_release_current",
    "uec.record_access_current", "uec.public_access_restricted", "uec.suppression_case_current",
    "uec.facility_lifecycle_current", "uec.graph_public_connections_current",
)


def package_manifest(*, release_ids: list[str], migration_inventory_sha256: str, table_counts: dict[str, int] | None = None, specs: tuple[ExportSpec, ...] | None = None, payload_files: list[dict[str, Any]] | None = None, schema_artifacts: dict[str, str] | None = None) -> dict[str, Any]:
    if not release_ids or len(release_ids) != len(set(release_ids)):
        raise ValueError("release IDs must be a non-empty unique set")
    if len(migration_inventory_sha256) != 64 or any(c not in "0123456789abcdef" for c in migration_inventory_sha256):
        raise ValueError("migration inventory digest must be lowercase sha256")
    specs = specs or export_specs()
    schema_artifacts = dict(sorted((schema_artifacts or {}).items()))
    if any(len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest) for digest in schema_artifacts.values()):
        raise ValueError("schema artifact digest must be lowercase sha256")
    value = {"schema_version": "uec-serving-package-v5", "package_state": "selected_public_serving_derivative", "release_ids": sorted(release_ids), "migration_inventory_sha256": migration_inventory_sha256, "data_relation_allowlist": [{"relation": s.relation, "columns": list(s.columns)} for s in specs], "data_relation_exclusions": list(FORBIDDEN_DATA_RELATIONS), "redaction_notice": "Source/artifact/observation stand-ins retain only join and provenance metadata and are explicitly marked redacted; raw source, acquisition, geocoder, private graph edges and evidence payloads are absent. The graph is a selected-release normalized opaque-endpoint projection with canonical support references held outside the API grant.", "table_counts": dict(sorted((table_counts or {}).items())), "payload_files": sorted(payload_files or [], key=lambda item: item["name"]), "serving_schema_derivative": {"artifacts_sha256": schema_artifacts, "post_data_omissions": list(SERVING_SCHEMA_OMISSIONS)}}
    value["package_sha256"] = canonical_sha256(value)
    return value


def grant_sql(api_role: str = "uec_api_runtime", release_role: str = "uec_release_operator", migration_role: str = "uec_migrator") -> str:
    for role in (api_role, release_role, migration_role):
        if not role.replace("_", "").isalnum(): raise ValueError("role names must be simple identifiers")
    return "\n".join(("BEGIN;", f"REVOKE ALL ON SCHEMA uec FROM {api_role};", f"REVOKE ALL ON ALL TABLES IN SCHEMA uec FROM {api_role};", f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA uec FROM {api_role};", f"GRANT USAGE ON SCHEMA uec TO {api_role};", f"GRANT SELECT ON {', '.join(API_RELATIONS)} TO {api_role};", f"REVOKE ALL ON SCHEMA uec FROM {release_role};", f"GRANT USAGE ON SCHEMA uec TO {release_role};", f"REVOKE ALL ON SCHEMA uec FROM {migration_role};", f"GRANT USAGE ON SCHEMA uec TO {migration_role};", "COMMIT;", ""))
