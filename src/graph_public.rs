//! Release-scoped, read-only public accountability graph projection.
//!
//! The graph edge table is private evidence. These handlers only return rows
//! whose source-qualified endpoints are themselves present in the selected
//! promoted public release. No raw evidence, source-record identifiers,
//! suppression metadata, or private queue state crosses this boundary.

use crate::{ApiState, v2_error};
use axum::{
    Json,
    extract::{Path, Query, State},
    http::StatusCode,
    response::IntoResponse,
};
use serde::Deserialize;
use serde_json::{Value, json};
use uuid::Uuid;

const MAX_LIMIT: i64 = 100;
const DEFAULT_LIMIT: i64 = 50;
const API_VERSION: &str = "v2-graph-v1";
const DISCLAIMER: &str = "Confidence is a deterministic ruleset estimate, not a measured probability. An inferred connection is not proof of ownership, identity, or supply-chain control.";

#[derive(Debug, Deserialize, Clone)]
pub struct PublicGraphQuery {
    pub profile: Option<String>,
    pub q: Option<String>,
    pub entity_type: Option<String>,
    pub entity_id: Option<Uuid>,
    pub connection_type: Option<String>,
    pub min_confidence: Option<f64>,
    pub max_confidence: Option<f64>,
    pub confidence_band: Option<String>,
    pub include_conflicting: Option<bool>,
    pub source_id: Option<String>,
    pub cursor: Option<Uuid>,
    pub limit: Option<i64>,
    pub direction: Option<String>,
    pub depth: Option<i32>,
}

fn bad(message: &'static str) -> axum::response::Response {
    v2_error(StatusCode::BAD_REQUEST, "invalid_graph_query", message)
}

fn limit(value: Option<i64>) -> Result<i64, &'static str> {
    let value = value.unwrap_or(DEFAULT_LIMIT);
    if (1..=MAX_LIMIT).contains(&value) {
        Ok(value)
    } else {
        Err("limit must be between 1 and 100")
    }
}

fn profile(value: Option<&str>) -> Result<&str, &'static str> {
    let value = value.unwrap_or("official");
    if matches!(value, "official" | "secondary" | "community") {
        Ok(value)
    } else {
        Err("profile is unsupported")
    }
}

fn clean_query(value: Option<String>) -> Result<String, &'static str> {
    let value = value.unwrap_or_default().trim().to_string();
    if value.chars().count() > 120 {
        Err("q must be at most 120 characters")
    } else {
        Ok(value)
    }
}

fn validate_common(query: &PublicGraphQuery) -> Result<(String, i64, String), &'static str> {
    let profile = profile(query.profile.as_deref())?.to_string();
    let limit = limit(query.limit)?;
    let q = clean_query(query.q.clone())?;
    if query.min_confidence.is_some_and(|v| !v.is_finite() || !(0.0..=1.0).contains(&v))
        || query.max_confidence.is_some_and(|v| !v.is_finite() || !(0.0..=1.0).contains(&v))
    {
        return Err("confidence bounds must be between 0 and 1");
    }
    if let (Some(min), Some(max)) = (query.min_confidence, query.max_confidence) {
        if min > max {
            return Err("min_confidence cannot exceed max_confidence");
        }
    }
    if query.connection_type.as_deref().is_some_and(|v| !matches!(v, "exact" | "inferred")) {
        return Err("connection_type must be exact or inferred");
    }
    if query.confidence_band.as_deref().is_some_and(|v| !matches!(v, "exact" | "high" | "medium" | "low")) {
        return Err("confidence_band must be exact, high, medium, or low");
    }
    if query.entity_type.as_deref().is_some_and(|v| !matches!(v, "facility" | "organization")) {
        return Err("entity_type must be facility or organization");
    }
    if query.direction.as_deref().is_some_and(|v| !matches!(v, "in" | "out" | "both")) {
        return Err("direction must be in, out, or both");
    }
    if query.depth.is_some_and(|v| !(1..=2).contains(&v)) {
        return Err("depth must be between 1 and 2");
    }
    Ok((profile, limit, q))
}

fn explanation(value: &str) -> (Value, Value) {
    let parsed = serde_json::from_str::<Value>(value).unwrap_or_else(|_| json!({}));
    let signals = parsed.get("group_contributions").cloned().unwrap_or_else(|| json!({}));
    let contradictions = parsed.get("contradictions").cloned().unwrap_or_else(|| json!([]));
    (signals, contradictions)
}

fn public_edge(row: &tokio_postgres::Row, release_id: &str) -> Value {
    let (signals, contradictions) = explanation(&row.get::<_, String>(15));
    json!({
        "connection_edge_id": row.get::<_, Uuid>(0),
        "from": {"entity_id": row.get::<_, Option<Uuid>>(1), "entity_type": row.get::<_, String>(2), "source_id": row.get::<_, String>(3), "identifier_type": row.get::<_, String>(4), "source_identifier": row.get::<_, String>(5)},
        "to": {"entity_id": row.get::<_, Option<Uuid>>(6), "entity_type": row.get::<_, String>(7), "source_id": row.get::<_, String>(8), "identifier_type": row.get::<_, String>(9), "source_identifier": row.get::<_, String>(10)},
        "relationship_type": row.get::<_, String>(11),
        "connection_type": row.get::<_, String>(12),
        "confidence": row.get::<_, f64>(13),
        "confidence_band": row.get::<_, String>(14),
        "match_method": row.get::<_, String>(16),
        "signals": signals,
        "contradictions": contradictions,
        "provenance": {"source_ids": [row.get::<_, String>(3), row.get::<_, String>(8)], "observed_at": row.get::<_, chrono::DateTime<chrono::Utc>>(17), "release_id": release_id},
        "source_references": [{"source_id": row.get::<_, String>(3)}, {"source_id": row.get::<_, String>(8)}],
        "observed_at": row.get::<_, chrono::DateTime<chrono::Utc>>(17),
        "computed_at": row.get::<_, chrono::DateTime<chrono::Utc>>(18),
        "ruleset": row.get::<_, String>(19),
        "conflicting": row.get::<_, bool>(20),
        "publication_warning": DISCLAIMER,
        "disclaimer": DISCLAIMER,
    })
}

const EDGE_SELECT: &str = "
    SELECT e.connection_edge_id,
           CASE WHEN fi.entity_type = 'facility' THEN fi.facility_id ELSE fi.organization_id END AS from_entity_id,
           e.from_entity_type, e.from_source_id, e.from_identifier_type,
           e.from_source_identifier,
           CASE WHEN ti.entity_type = 'facility' THEN ti.facility_id ELSE ti.organization_id END AS to_entity_id,
           e.to_entity_type, e.to_source_id, e.to_identifier_type,
           e.to_source_identifier, e.relationship_type, e.connection_type,
           e.confidence::double precision,
           CASE WHEN e.confidence_band = 'probable' THEN 'high'
                WHEN e.confidence_band = 'possible' THEN 'medium'
                ELSE e.confidence_band END AS public_confidence_band,
           e.signal_explanation::text, e.match_method,
           e.observed_at, e.computed_at, e.ruleset_version, e.conflicting
    FROM uec.graph_connection_edges e
    JOIN uec.source_entity_identifiers fi
      ON fi.source_id = e.from_source_id AND fi.identifier_type = e.from_identifier_type AND fi.source_identifier = e.from_source_identifier
    JOIN uec.source_entity_identifiers ti
      ON ti.source_id = e.to_source_id AND ti.identifier_type = e.to_identifier_type AND ti.source_identifier = e.to_source_identifier
    WHERE e.suppressed = false
      AND e.storage_state = 'private'
      AND e.publication_status = 'not_eligible'
      AND fi.storage_state = 'released' AND fi.publication_status = 'released' AND fi.privacy_status = 'passed'
      AND ti.storage_state = 'released' AND ti.publication_status = 'released' AND ti.privacy_status = 'passed'
      AND fi.release_id = $1 AND ti.release_id = $1
      AND (
        (fi.entity_type = 'facility' AND EXISTS (SELECT 1 FROM uec.map_facilities_public_discovery_read_model p WHERE p.release_id = $1 AND p.facility_id = fi.facility_id))
        OR (fi.entity_type = 'organization' AND EXISTS (SELECT 1 FROM uec.map_facilities_public_discovery_read_model p JOIN uec.source_entity_identifiers pi ON pi.facility_id = p.facility_id AND pi.entity_type = 'facility' WHERE p.release_id = $1 AND pi.release_id = $1 AND pi.storage_state = 'released' AND pi.publication_status = 'released' AND EXISTS (SELECT 1 FROM uec.graph_connection_edges x WHERE x.suppressed = false AND ((x.from_source_id = e.from_source_id AND x.from_identifier_type = e.from_identifier_type AND x.from_source_identifier = e.from_source_identifier) OR (x.to_source_id = e.from_source_id AND x.to_identifier_type = e.from_identifier_type AND x.to_source_identifier = e.from_source_identifier)))))
      )
      AND (
        (ti.entity_type = 'facility' AND EXISTS (SELECT 1 FROM uec.map_facilities_public_discovery_read_model p WHERE p.release_id = $1 AND p.facility_id = ti.facility_id))
        OR (ti.entity_type = 'organization' AND EXISTS (SELECT 1 FROM uec.map_facilities_public_discovery_read_model p JOIN uec.source_entity_identifiers pi ON pi.facility_id = p.facility_id AND pi.entity_type = 'facility' WHERE p.release_id = $1 AND pi.release_id = $1 AND pi.storage_state = 'released' AND pi.publication_status = 'released' AND EXISTS (SELECT 1 FROM uec.graph_connection_edges x WHERE x.suppressed = false AND ((x.from_source_id = e.to_source_id AND x.from_identifier_type = e.to_identifier_type AND x.from_source_identifier = e.to_source_identifier) OR (x.to_source_id = e.to_source_id AND x.to_identifier_type = e.to_identifier_type AND x.to_source_identifier = e.to_source_identifier)))))
      )";

pub async fn connections(State(state): State<ApiState>, Query(query): Query<PublicGraphQuery>) -> impl IntoResponse {
    let (profile, limit, _) = match validate_common(&query) { Ok(value) => value, Err(message) => return bad(message) };
    let Some(pool) = state.database else { return v2_error(StatusCode::SERVICE_UNAVAILABLE, "database_not_configured", "public graph unavailable"); };
    let Ok(mut client) = pool.get().await else { return v2_error(StatusCode::SERVICE_UNAVAILABLE, "database_pool_unavailable", "public graph unavailable"); };
    let Ok(transaction) = client.build_transaction().isolation_level(tokio_postgres::IsolationLevel::RepeatableRead).read_only(true).start().await else { return v2_error(StatusCode::SERVICE_UNAVAILABLE, "database_transaction_unavailable", "public graph unavailable"); };
    let release_row = transaction.query_opt("SELECT r.release_id, r.ruleset_version FROM uec.releases r JOIN uec.public_discovery_read_models model ON model.release_id = r.release_id JOIN uec.release_manifests manifest ON manifest.release_id = r.release_id AND manifest.manifest_sha256 = model.manifest_sha256 WHERE r.status = 'promoted' AND r.test_only IS NOT TRUE AND r.profile = $1 ORDER BY r.created_at DESC, r.release_id DESC LIMIT 1", &[&profile]).await;
    let Ok(Some(release_row)) = release_row else { return v2_error(StatusCode::NOT_FOUND, "release_not_found", "no promoted eligible public graph release"); };
    let release_id: String = release_row.get(0);
    let ruleset: String = release_row.get(1);
    let bands = match query.confidence_band.as_deref() { Some("high") => Some(vec!["high", "probable"]), Some("medium") => Some(vec!["medium", "possible"]), Some("low") => Some(vec!["low"]), Some("exact") => Some(vec!["exact"]), _ => None };
    let include_conflicting = query.include_conflicting.unwrap_or(false);
    let sql = format!("WITH edges AS ({EDGE_SELECT}) SELECT * FROM edges WHERE ($2::text IS NULL OR connection_type = $2) AND ($3::double precision IS NULL OR confidence >= $3) AND ($4::double precision IS NULL OR confidence <= $4) AND ($5::text[] IS NULL OR public_confidence_band = ANY($5)) AND ($6 OR conflicting = false) AND ($7::text IS NULL OR from_source_id = $7 OR to_source_id = $7) AND ($8::uuid IS NULL OR from_entity_id = $8 OR to_entity_id = $8) AND ($9::uuid IS NULL OR connection_edge_id < $9) ORDER BY connection_edge_id DESC LIMIT $10");
    let rows = match transaction.query(&sql, &[&release_id, &query.connection_type, &query.min_confidence, &query.max_confidence, &bands, &include_conflicting, &query.source_id, &query.entity_id, &query.cursor, &limit]).await { Ok(rows) => rows, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "public_graph_query_failed", "public graph query failed") };
    let data: Vec<Value> = rows.iter().map(|row| public_edge(row, &release_id)).collect();
    let next_cursor = data.last().and_then(|row| row.get("connection_edge_id")).cloned();
    Json(json!({"api_version": API_VERSION, "data": data, "meta": {"profile": profile, "release_id": release_id, "ruleset_version": ruleset, "limit": limit, "page_max": MAX_LIMIT, "next_cursor": next_cursor, "confidence_kind": "ruleset_estimate_not_probability", "public_projection": true, "suppressed": false, "human_confirmed_state": false, "automatic_merge": false, "claim_transfer": false}})).into_response()
}

pub async fn entities(State(state): State<ApiState>, Query(query): Query<PublicGraphQuery>) -> impl IntoResponse {
    let (profile, limit, q) = match validate_common(&query) { Ok(value) => value, Err(message) => return bad(message) };
    let Some(pool) = state.database else { return v2_error(StatusCode::SERVICE_UNAVAILABLE, "database_not_configured", "public graph unavailable"); };
    let Ok(client) = pool.get().await else { return v2_error(StatusCode::SERVICE_UNAVAILABLE, "database_pool_unavailable", "public graph unavailable"); };
    let release_row = client.query_opt("SELECT r.release_id, r.ruleset_version FROM uec.releases r JOIN uec.public_discovery_read_models model ON model.release_id = r.release_id JOIN uec.release_manifests manifest ON manifest.release_id = r.release_id AND manifest.manifest_sha256 = model.manifest_sha256 WHERE r.status = 'promoted' AND r.test_only IS NOT TRUE AND r.profile = $1 ORDER BY r.created_at DESC, r.release_id DESC LIMIT 1", &[&profile]).await;
    let Ok(Some(release_row)) = release_row else { return v2_error(StatusCode::NOT_FOUND, "release_not_found", "no promoted eligible public graph release"); };
    let release_id: String = release_row.get(0);
    let ruleset: String = release_row.get(1);
    let rows = match client.query("SELECT entity_id, entity_type, canonical_name, country_code FROM (SELECT p.facility_id AS entity_id, 'facility'::text AS entity_type, p.canonical_name, p.country_code FROM uec.map_facilities_public_discovery_read_model p WHERE p.release_id = $1 UNION SELECT o.organization_id, 'organization', o.canonical_name, o.country_code FROM uec.organizations o JOIN uec.source_entity_identifiers i ON i.organization_id = o.organization_id AND i.entity_type = 'organization' WHERE i.release_id = $1 AND i.storage_state = 'released' AND i.publication_status = 'released' AND i.privacy_status = 'passed') entities WHERE ($2 = '' OR canonical_name ILIKE '%' || $2 || '%') AND ($3::text IS NULL OR entity_type = $3) AND ($4::uuid IS NULL OR entity_id < $4) ORDER BY entity_id DESC LIMIT $5", &[&release_id, &q, &query.entity_type, &query.cursor, &limit]).await { Ok(rows) => rows, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "public_graph_query_failed", "public graph entity search failed") };
    let data: Vec<Value> = rows.iter().map(|row| json!({"entity_id": row.get::<_, Uuid>(0), "entity_type": row.get::<_, String>(1), "display_name": row.get::<_, Option<String>>(2), "country_code": row.get::<_, Option<String>>(3)})).collect();
    let next_cursor = data.last().and_then(|row| row.get("entity_id")).cloned();
    Json(json!({"api_version": API_VERSION, "data": data, "meta": {"profile": profile, "release_id": release_id, "ruleset_version": ruleset, "limit": limit, "page_max": MAX_LIMIT, "next_cursor": next_cursor, "public_projection": true}})).into_response()
}

pub async fn neighborhood(State(state): State<ApiState>, Path(entity_id): Path<Uuid>, Query(mut query): Query<PublicGraphQuery>) -> impl IntoResponse {
    query.entity_id = Some(entity_id);
    query.direction = Some(query.direction.unwrap_or_else(|| "both".to_string()));
    query.depth = Some(query.depth.unwrap_or(1));
    connections(State(state), Query(query)).await.into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn public_validation_is_bounded_and_explicit() {
        assert!(validate_common(&PublicGraphQuery { limit: Some(101), ..Default::default() }).is_err());
        assert!(validate_common(&PublicGraphQuery { confidence_band: Some("medium".into()), ..Default::default() }).is_ok());
        assert!(validate_common(&PublicGraphQuery { q: Some("x".repeat(121)), ..Default::default() }).is_err());
    }

    impl Default for PublicGraphQuery {
        fn default() -> Self { Self { profile: None, q: None, entity_type: None, entity_id: None, connection_type: None, min_confidence: None, max_confidence: None, confidence_band: None, include_conflicting: None, source_id: None, cursor: None, limit: None, direction: None, depth: None } }
    }
}
