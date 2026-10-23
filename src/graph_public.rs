//! Release-scoped, read-only public accountability graph projection.
//!
//! The graph edge table is private evidence. These handlers only return rows
//! whose source-qualified endpoints are themselves present in the selected
//! promoted public release. Organization labels are joined from the current
//! safe-label view. No raw evidence, source-record identifiers,
//! suppression metadata, or private queue state crosses this boundary.

use crate::{v2_error, ApiState};
use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde::Deserialize;
use serde_json::{json, Value};
use uuid::Uuid;

const MAX_LIMIT: i64 = 100;
const DEFAULT_LIMIT: i64 = 50;
const API_VERSION: &str = "v2-graph-v1";
const DISCLAIMER: &str = "Confidence is a deterministic ruleset estimate, not a measured probability. An inferred connection is not proof of ownership, identity, or supply-chain control.";
const GRAPH_CONNECTION_SELECT: &str = "SELECT edge.connection_edge_id,edge.from_entity_id,edge.from_entity_type,edge.from_source_id,edge.from_identifier_type,edge.to_entity_id,edge.to_entity_type,edge.to_source_id,edge.to_identifier_type,edge.relationship_type,edge.connection_type,edge.confidence,edge.confidence_band,edge.signal_explanation,edge.match_method,edge.observed_at,edge.computed_at,edge.ruleset_version,edge.conflicting,from_label.display_name,to_label.display_name FROM uec.graph_public_connections_current edge LEFT JOIN uec.graph_public_organization_labels_current from_label ON from_label.release_id=edge.release_id AND from_label.organization_id=edge.from_entity_id AND edge.from_entity_type='organization' LEFT JOIN uec.graph_public_organization_labels_current to_label ON to_label.release_id=edge.release_id AND to_label.organization_id=edge.to_entity_id AND edge.to_entity_type='organization' WHERE edge.release_id=$1 AND ($2::text IS NULL OR edge.connection_type=$2) AND ($3::double precision IS NULL OR edge.confidence >= $3) AND ($4::double precision IS NULL OR edge.confidence <= $4) AND ($5::text[] IS NULL OR edge.confidence_band=ANY($5)) AND ($6 OR edge.conflicting=false) AND ($7::text IS NULL OR edge.from_source_id=$7 OR edge.to_source_id=$7) AND ($8::uuid IS NULL OR edge.from_entity_id=$8 OR edge.to_entity_id=$8) AND ($9::uuid IS NULL OR edge.connection_edge_id<$9) ORDER BY edge.connection_edge_id DESC LIMIT $10";
const GRAPH_APHIS_REFERENCE_SELECT: &str = "SELECT evidence_ref_id,source_id,evidence_type,event_date,event_period,observed_at,source_url,match_method FROM uec.graph_public_evidence_references_current WHERE release_id=$1 AND public_entity_id=$2 AND endpoint_source_id='us.aphis' AND ($3::uuid IS NULL OR evidence_ref_id<$3) ORDER BY evidence_ref_id DESC LIMIT $4";

#[derive(Debug, Deserialize, Clone)]
pub struct PublicGraphQuery {
    pub profile: Option<String>,
    pub release_id: Option<String>,
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

fn page_cursor<T>(
    items: &mut Vec<T>,
    requested_limit: usize,
    cursor: impl Fn(&T) -> Option<Value>,
) -> Option<Value> {
    let has_more = items.len() > requested_limit;
    if has_more {
        items.truncate(requested_limit);
        items.last().and_then(cursor)
    } else {
        None
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
    if query.release_id.as_deref().is_some_and(|value| {
        value.is_empty()
            || value.len() > 160
            || !value
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
    }) {
        return Err("release_id is invalid");
    }
    if query
        .min_confidence
        .is_some_and(|v| !v.is_finite() || !(0.0..=1.0).contains(&v))
        || query
            .max_confidence
            .is_some_and(|v| !v.is_finite() || !(0.0..=1.0).contains(&v))
    {
        return Err("confidence bounds must be between 0 and 1");
    }
    if let (Some(min), Some(max)) = (query.min_confidence, query.max_confidence) {
        if min > max {
            return Err("min_confidence cannot exceed max_confidence");
        }
    }
    if query
        .connection_type
        .as_deref()
        .is_some_and(|v| !matches!(v, "exact" | "inferred"))
    {
        return Err("connection_type must be exact or inferred");
    }
    if query
        .confidence_band
        .as_deref()
        .is_some_and(|v| !matches!(v, "exact" | "high" | "medium" | "low"))
    {
        return Err("confidence_band must be exact, high, medium, or low");
    }
    if query
        .entity_type
        .as_deref()
        .is_some_and(|v| !matches!(v, "facility" | "organization"))
    {
        return Err("entity_type must be facility or organization");
    }
    if query
        .direction
        .as_deref()
        .is_some_and(|v| !matches!(v, "in" | "out" | "both"))
    {
        return Err("direction must be in, out, or both");
    }
    if query.depth.is_some_and(|v| !(1..=2).contains(&v)) {
        return Err("depth must be between 1 and 2");
    }
    Ok((profile, limit, q))
}

fn explanation(value: &str) -> (Value, Value) {
    let parsed = serde_json::from_str::<Value>(value).unwrap_or_else(|_| json!({}));
    let signals = parsed
        .get("group_contributions")
        .and_then(Value::as_object)
        .map(|groups| {
            let mut safe = serde_json::Map::new();
            for (group, value) in groups {
                if [
                    "source",
                    "identity",
                    "location",
                    "contact",
                    "temporal",
                    "contradiction",
                ]
                .contains(&group.as_str())
                    && value
                        .as_f64()
                        .is_some_and(|number| number.is_finite() && number >= 0.0)
                {
                    safe.insert(group.clone(), value.clone());
                }
            }
            Value::Object(safe)
        })
        .unwrap_or_else(|| json!({}));
    let contradictions = parsed
        .get("contradictions")
        .and_then(Value::as_array)
        .map(|rows| {
            Value::Array(
                rows.iter()
                    .map(|row| {
                        let name = row.get("name").and_then(Value::as_str);
                        let Some(name) = name.filter(|name| {
                            [
                                "conflicting_identifier",
                                "conflicting_address",
                                "temporal_conflict",
                            ]
                            .contains(name)
                        }) else {
                            return Value::Null;
                        };
                        let mut safe = serde_json::Map::new();
                        safe.insert("name".to_string(), Value::String(name.to_string()));
                        safe.insert(
                            "group".to_string(),
                            Value::String("contradiction".to_string()),
                        );
                        if let Some(weight) = row
                            .get("weight")
                            .and_then(Value::as_f64)
                            .filter(|weight| weight.is_finite() && (0.0..=1.0).contains(weight))
                        {
                            safe.insert("weight".to_string(), json!(weight));
                        }
                        if let Some(value) = row.get("value").and_then(Value::as_bool) {
                            safe.insert("value".to_string(), Value::Bool(value));
                        }
                        Value::Object(safe)
                    })
                    .filter(|row| !row.is_null())
                    .collect(),
            )
        })
        .unwrap_or_else(|| json!([]));
    (signals, contradictions)
}

fn public_edge(row: &tokio_postgres::Row, release_id: &str) -> Value {
    let (signals, contradictions) = explanation(&row.get::<_, String>(13));
    let from_identifier_type: String = row.get(4);
    let to_identifier_type: String = row.get(8);
    let from_public_identifier = public_identifier(row.get(1));
    let to_public_identifier = public_identifier(row.get(5));
    json!({
        "connection_edge_id": row.get::<_, Uuid>(0),
        "from": {"entity_id": row.get::<_, Uuid>(1), "entity_type": row.get::<_, String>(2), "source_id": row.get::<_, String>(3), "identifier_type": from_identifier_type, "source_identifier": from_public_identifier, "display_name": row.get::<_, Option<String>>(19)},
        "to": {"entity_id": row.get::<_, Uuid>(5), "entity_type": row.get::<_, String>(6), "source_id": row.get::<_, String>(7), "identifier_type": to_identifier_type, "source_identifier": to_public_identifier, "display_name": row.get::<_, Option<String>>(20)},
        "relationship_type": row.get::<_, String>(9),
        "connection_type": row.get::<_, String>(10),
        "confidence": row.get::<_, f64>(11),
        "confidence_band": row.get::<_, String>(12),
        "match_method": row.get::<_, String>(14),
        "signals": signals,
        "contradictions": contradictions,
        "provenance": {"source_ids": [row.get::<_, String>(3), row.get::<_, String>(7)], "observed_at": row.get::<_, chrono::DateTime<chrono::Utc>>(15), "release_id": release_id},
        "source_references": [{"source_id": row.get::<_, String>(3)}, {"source_id": row.get::<_, String>(7)}],
        "observed_at": row.get::<_, chrono::DateTime<chrono::Utc>>(15),
        "computed_at": row.get::<_, chrono::DateTime<chrono::Utc>>(16),
        "ruleset": row.get::<_, String>(17),
        "conflicting": row.get::<_, bool>(18),
        "publication_warning": DISCLAIMER,
        "disclaimer": DISCLAIMER,
    })
}

fn public_identifier(entity_id: Option<Uuid>) -> String {
    entity_id
        .map(|id| format!("entity:{id}"))
        .unwrap_or_else(|| "entity:unavailable".to_string())
}

#[cfg(test)]
const EDGE_CTES: &str = include_str!("../pipeline/sql/graph_public_edge_ctes.sql");

pub async fn connections(
    State(state): State<ApiState>,
    Query(query): Query<PublicGraphQuery>,
) -> impl IntoResponse {
    let (profile, limit, _) = match validate_common(&query) {
        Ok(value) => value,
        Err(message) => return bad(message),
    };
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_not_configured",
            "public graph unavailable",
        );
    };
    let Ok(mut client) = pool.get().await else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_pool_unavailable",
            "public graph unavailable",
        );
    };
    let Ok(transaction) = client
        .build_transaction()
        .isolation_level(tokio_postgres::IsolationLevel::RepeatableRead)
        .read_only(true)
        .start()
        .await
    else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_transaction_unavailable",
            "public graph unavailable",
        );
    };
    let release_row = transaction.query_opt("SELECT r.release_id, r.ruleset_version FROM uec.releases r JOIN uec.public_discovery_read_models model ON model.release_id = r.release_id JOIN uec.release_manifests manifest ON manifest.release_id = r.release_id AND manifest.manifest_sha256 = model.manifest_sha256 LEFT JOIN uec.public_release_history history ON history.release_id=r.release_id AND history.profile=r.profile WHERE r.test_only IS NOT TRUE AND r.profile=$1 AND ($2::text IS NULL OR r.release_id=$2) AND (r.status='promoted' OR ($2::text IS NOT NULL AND history.release_id IS NOT NULL AND r.status='validated')) ORDER BY r.created_at DESC, r.release_id DESC LIMIT 1", &[&profile, &query.release_id]).await;
    let Ok(Some(release_row)) = release_row else {
        return v2_error(
            StatusCode::NOT_FOUND,
            "release_not_found",
            "no promoted eligible public graph release",
        );
    };
    let release_id: String = release_row.get(0);
    let ruleset: String = release_row.get(1);
    let bands = match query.confidence_band.as_deref() {
        Some("high") => Some(vec!["high", "probable"]),
        Some("medium") => Some(vec!["medium", "possible"]),
        Some("low") => Some(vec!["low"]),
        Some("exact") => Some(vec!["exact"]),
        _ => None,
    };
    let include_conflicting = query.include_conflicting.unwrap_or(false);
    let rows = match transaction
        .query(
            GRAPH_CONNECTION_SELECT,
            &[
                &release_id,
                &query.connection_type,
                &query.min_confidence,
                &query.max_confidence,
                &bands,
                &include_conflicting,
                &query.source_id,
                &query.entity_id,
                &query.cursor,
                &(limit + 1),
            ],
        )
        .await
    {
        Ok(rows) => rows,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "public_graph_query_failed",
                "public graph query failed",
            );
        }
    };
    let mut data: Vec<Value> = rows
        .iter()
        .map(|row| public_edge(row, &release_id))
        .collect();
    let next_cursor = page_cursor(&mut data, limit as usize, |row| {
        row.get("connection_edge_id").cloned()
    });
    Json(json!({"api_version": API_VERSION, "data": data, "meta": {"profile": profile, "release_id": release_id, "ruleset_version": ruleset, "limit": limit, "page_max": MAX_LIMIT, "next_cursor": next_cursor, "confidence_kind": "ruleset_estimate_not_probability", "public_projection": true, "suppressed": false, "human_confirmed_state": false, "automatic_merge": false, "claim_transfer": false}})).into_response()
}

pub async fn entities(
    State(state): State<ApiState>,
    Query(query): Query<PublicGraphQuery>,
) -> impl IntoResponse {
    let (profile, limit, q) = match validate_common(&query) {
        Ok(value) => value,
        Err(message) => return bad(message),
    };
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_not_configured",
            "public graph unavailable",
        );
    };
    let Ok(client) = pool.get().await else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_pool_unavailable",
            "public graph unavailable",
        );
    };
    let release_row = client.query_opt("SELECT r.release_id, r.ruleset_version FROM uec.releases r JOIN uec.public_discovery_read_models model ON model.release_id = r.release_id JOIN uec.release_manifests manifest ON manifest.release_id = r.release_id AND manifest.manifest_sha256 = model.manifest_sha256 LEFT JOIN uec.public_release_history history ON history.release_id=r.release_id AND history.profile=r.profile WHERE r.test_only IS NOT TRUE AND r.profile=$1 AND ($2::text IS NULL OR r.release_id=$2) AND (r.status='promoted' OR ($2::text IS NOT NULL AND history.release_id IS NOT NULL AND r.status='validated')) ORDER BY r.created_at DESC, r.release_id DESC LIMIT 1", &[&profile, &query.release_id]).await;
    let Ok(Some(release_row)) = release_row else {
        return v2_error(
            StatusCode::NOT_FOUND,
            "release_not_found",
            "no promoted eligible public graph release",
        );
    };
    let release_id: String = release_row.get(0);
    let ruleset: String = release_row.get(1);
    let rows = match client.query(r#"
        SELECT entity_id,entity_type,display_name,country_code FROM (
          SELECT p.facility_id AS entity_id,'facility'::text AS entity_type,
                 p.canonical_name AS display_name,p.country_code
          FROM uec.map_facilities_public_discovery_read_model p WHERE p.release_id=$1
          UNION
          SELECT labels.organization_id,'organization'::text,labels.display_name,NULL::text
          FROM (
            SELECT DISTINCT ON (release_id,organization_id)
                   release_id,organization_id,display_name
            FROM uec.graph_public_organization_labels_current
            WHERE release_id=$1
            ORDER BY release_id,organization_id,
                     CASE assertion_role WHEN 'legal' THEN 0 WHEN 'business' THEN 1 ELSE 2 END,
                     display_name
          ) labels
        ) entities
        WHERE ($2='' OR display_name ILIKE '%' || $2 || '%')
          AND ($3::text IS NULL OR entity_type=$3)
          AND ($4::uuid IS NULL OR entity_id < $4)
        ORDER BY entity_id DESC LIMIT $5
    "#, &[&release_id, &q, &query.entity_type, &query.cursor, &(limit + 1)]).await { Ok(rows) => rows, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "public_graph_query_failed", "public graph entity search failed") };
    let mut data: Vec<Value> = rows.iter().map(|row| json!({"entity_id": row.get::<_, Uuid>(0), "entity_type": row.get::<_, String>(1), "display_name": row.get::<_, Option<String>>(2), "country_code": row.get::<_, Option<String>>(3)})).collect();
    let next_cursor = page_cursor(&mut data, limit as usize, |row| {
        row.get("entity_id").cloned()
    });
    Json(json!({"api_version": API_VERSION, "data": data, "meta": {"profile": profile, "release_id": release_id, "ruleset_version": ruleset, "limit": limit, "page_max": MAX_LIMIT, "next_cursor": next_cursor, "public_projection": true}})).into_response()
}

pub async fn neighborhood(
    State(state): State<ApiState>,
    Path(entity_id): Path<Uuid>,
    Query(mut query): Query<PublicGraphQuery>,
) -> impl IntoResponse {
    query.entity_id = Some(entity_id);
    query.direction = Some(query.direction.unwrap_or_else(|| "both".to_string()));
    query.depth = Some(query.depth.unwrap_or(1));
    connections(State(state), Query(query))
        .await
        .into_response()
}

/// Return only typed APHIS references that entered a safe selected-release
/// projection. The view applies selected-release review, rights, membership,
/// and restriction gates; this handler never reads private event payloads.
pub async fn evidence_references(
    State(state): State<ApiState>,
    Path(entity_id): Path<Uuid>,
    Query(query): Query<PublicGraphQuery>,
) -> impl IntoResponse {
    let (profile, limit, _) = match validate_common(&query) {
        Ok(value) => value,
        Err(message) => return bad(message),
    };
    let Some(pool) = state.database else {
        return v2_error(StatusCode::SERVICE_UNAVAILABLE, "database_not_configured", "public graph unavailable");
    };
    let Ok(mut client) = pool.get().await else {
        return v2_error(StatusCode::SERVICE_UNAVAILABLE, "database_pool_unavailable", "public graph unavailable");
    };
    let Ok(transaction) = client.build_transaction()
        .isolation_level(tokio_postgres::IsolationLevel::RepeatableRead)
        .read_only(true).start().await else {
        return v2_error(StatusCode::SERVICE_UNAVAILABLE, "database_transaction_unavailable", "public graph unavailable");
    };
    let release_row = transaction.query_opt(
        "SELECT r.release_id,r.ruleset_version FROM uec.releases r JOIN uec.public_discovery_read_models model ON model.release_id=r.release_id JOIN uec.release_manifests manifest ON manifest.release_id=r.release_id AND manifest.manifest_sha256=model.manifest_sha256 LEFT JOIN uec.public_release_history history ON history.release_id=r.release_id AND history.profile=r.profile WHERE r.test_only IS NOT TRUE AND r.profile=$1 AND ($2::text IS NULL OR r.release_id=$2) AND (r.status='promoted' OR ($2::text IS NOT NULL AND history.release_id IS NOT NULL AND r.status='validated')) ORDER BY r.created_at DESC,r.release_id DESC LIMIT 1",
        &[&profile, &query.release_id],
    ).await;
    let Ok(Some(release_row)) = release_row else {
        return v2_error(StatusCode::NOT_FOUND, "release_not_found", "no promoted eligible public graph release");
    };
    let release_id: String = release_row.get(0);
    let ruleset: String = release_row.get(1);
    let rows = match transaction.query(
        GRAPH_APHIS_REFERENCE_SELECT,
        &[&release_id, &entity_id, &query.cursor, &(limit + 1)],
    ).await {
        Ok(rows) => rows,
        Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "public_graph_query_failed", "public evidence references unavailable"),
    };
    let mut data: Vec<Value> = rows.iter().map(|row| json!({
        "reference_id": row.get::<_, Uuid>(0),
        "source_id": row.get::<_, String>(1),
        "evidence_type": row.get::<_, String>(2),
        "event_date": row.get::<_, Option<chrono::NaiveDate>>(3).map(|value| value.to_string()),
        "event_period": row.get::<_, Option<String>>(4),
        "observed_at": row.get::<_, chrono::DateTime<chrono::Utc>>(5),
        "source_url": row.get::<_, String>(6),
        "match_method": row.get::<_, String>(7),
    })).collect();
    let next_cursor = page_cursor(&mut data, limit as usize, |row| row.get("reference_id").cloned());
    Json(json!({"api_version": API_VERSION, "data": data, "meta": {
        "profile": profile, "release_id": release_id, "ruleset_version": ruleset,
        "limit": limit, "page_max": MAX_LIMIT, "next_cursor": next_cursor,
        "public_projection": true,
    }})).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn public_validation_is_bounded_and_explicit() {
        assert!(validate_common(&PublicGraphQuery {
            limit: Some(101),
            ..Default::default()
        })
        .is_err());
        assert!(validate_common(&PublicGraphQuery {
            confidence_band: Some("medium".into()),
            ..Default::default()
        })
        .is_ok());
        assert!(validate_common(&PublicGraphQuery {
            q: Some("x".repeat(121)),
            ..Default::default()
        })
        .is_err());
    }

    #[test]
    fn connection_pages_only_expose_cursor_when_lookahead_exists() {
        for (page, expected_count, expected_cursor) in [
            (
                vec![
                    json!({"connection_edge_id": "a"}),
                    json!({"connection_edge_id": "b"}),
                ],
                2,
                None,
            ),
            (
                vec![
                    json!({"connection_edge_id": "a"}),
                    json!({"connection_edge_id": "b"}),
                    json!({"connection_edge_id": "c"}),
                ],
                2,
                Some("b"),
            ),
            (Vec::new(), 0, None),
        ] {
            let mut page = page;
            let cursor = page_cursor(&mut page, 2, |row| row.get("connection_edge_id").cloned());
            assert_eq!(page.len(), expected_count);
            assert_eq!(cursor, expected_cursor.map(|value| json!(value)));
        }
    }

    #[test]
    fn entity_pages_only_expose_cursor_when_lookahead_exists() {
        for (page, expected_count, expected_cursor) in [
            (
                vec![json!({"entity_id": "a"}), json!({"entity_id": "b"})],
                2,
                None,
            ),
            (
                vec![
                    json!({"entity_id": "a"}),
                    json!({"entity_id": "b"}),
                    json!({"entity_id": "c"}),
                ],
                2,
                Some("b"),
            ),
            (Vec::new(), 0, None),
        ] {
            let mut page = page;
            let cursor = page_cursor(&mut page, 2, |row| row.get("entity_id").cloned());
            assert_eq!(page.len(), expected_count);
            assert_eq!(cursor, expected_cursor.map(|value| json!(value)));
        }
    }

    #[test]
    fn endpoint_identifier_is_an_opaque_canonical_id_token() {
        let id = Uuid::parse_str("00112233-4455-6677-8899-aabbccddeeff").unwrap();
        assert_eq!(public_identifier(Some(id)), format!("entity:{id}"));
        assert_eq!(public_identifier(None), "entity:unavailable");
    }

    #[test]
    fn edge_projection_precomputes_unique_release_endpoints_once() {
        assert!(EDGE_CTES.contains("record_facilities AS MATERIALIZED"));
        assert!(EDGE_CTES.contains("eligible_source_endpoints AS MATERIALIZED"));
        assert!(EDGE_CTES.contains("release_support_records AS MATERIALIZED"));
        assert!(EDGE_CTES.contains("eligible_edge_supports AS MATERIALIZED"));
        assert!(EDGE_CTES.contains("binding.release_id=$1"));
        assert!(EDGE_CTES.contains("canonical_record.artifact_id=binding.artifact_id"));
        assert!(EDGE_CTES.contains("private_record.artifact_id=binding.artifact_id"));
        assert!(EDGE_CTES.contains("HAVING count(*)=count(record.source_record_id)"));
        assert!(EDGE_CTES.contains("ambiguous_record_facilities AS MATERIALIZED"));
        assert!(EDGE_CTES.contains("ambiguous_source_endpoints AS MATERIALIZED"));
        assert!(EDGE_CTES.contains("HAVING count(*)>1"));
        assert!(EDGE_CTES.contains("LEFT JOIN ambiguous_source_endpoints"));
        assert!(EDGE_CTES.contains("LEFT JOIN ambiguous_record_facilities"));
        assert!(EDGE_CTES.contains("AND asserted_facility.facility_id=rf.facility_id"));
        assert!(EDGE_CTES.contains("graph_source_name_assertions"));
        assert!(EDGE_CTES.contains("business_registration"));
        assert!(!EDGE_CTES.contains("operator-name'"));
        assert!(EDGE_CTES.contains("e.connection_type='inferred'"));
        assert!(EDGE_CTES.contains("e.connection_type='exact' AND e.relationship_type='operator'"));
        assert!(!EDGE_CTES.contains("SELECT DISTINCT e.connection_edge_id"));
        assert!(!EDGE_CTES.contains("count(DISTINCT CASE"));
    }

    #[test]
    fn inferred_business_links_require_eligible_nodes_and_versioned_support() {
        assert!(EDGE_CTES.contains("graph_source_name_assertions"));
        assert!(EDGE_CTES.contains("business_id"));
        assert!(EDGE_CTES.contains("asserted_facility.source_record_id=i.source_record_id"));
        assert!(EDGE_CTES.contains("asserted_facility.facility_id=rf.facility_id"));
        assert!(EDGE_CTES.contains("e.connection_type='inferred'"));
        assert!(EDGE_CTES.contains("e.connection_type='exact' AND e.relationship_type='operator'"));
        assert!(EDGE_CTES.contains("JOIN eligible_edge_supports support"));
        assert!(EDGE_CTES.contains("HAVING count(*)=count(record.source_record_id)"));
        assert!(!EDGE_CTES.contains("fiscal_code"));
        assert!(!EDGE_CTES.contains("codice_fiscale"));
    }

    #[test]
    fn api_reads_indexed_projection_and_entities_follow_same_endpoint_policy() {
        assert!(GRAPH_CONNECTION_SELECT.contains("FROM uec.graph_public_connections_current"));
        assert!(GRAPH_CONNECTION_SELECT.contains("graph_public_organization_labels_current"));
        assert!(!GRAPH_CONNECTION_SELECT.contains("graph_connection_edges"));
        assert!(!GRAPH_CONNECTION_SELECT.contains("source_entity_identifiers"));
        assert!(GRAPH_CONNECTION_SELECT.contains("from_label.display_name,to_label.display_name"));
        assert!(GRAPH_CONNECTION_SELECT.contains("ORDER BY edge.connection_edge_id DESC LIMIT $10"));
        let entity_query = include_str!("../pipeline/migrations/077_graph_release_projection.sql");
        assert!(entity_query.contains("CREATE VIEW uec.graph_public_connections_current"));
        assert!(entity_query.contains("graph_public_projection_endpoint_anchors"));
        let evidence_migration = include_str!("../pipeline/migrations/080_graph_public_evidence_references.sql");
        assert!(evidence_migration.contains("graph_public_organization_endpoints_current"));
        assert!(evidence_migration.contains("DISTINCT ON (eligible.release_id,eligible.organization_id)"));
        assert!(evidence_migration.contains("b.projection_version='graph-release-projection-v3'"));
        assert!(evidence_migration.contains("b.suppression_generation=suppression.generation"));
        let api_entity_query = include_str!("../src/graph_public.rs");
        assert!(api_entity_query.contains("SELECT DISTINCT ON (release_id,organization_id)"));
    }

    #[test]
    fn public_explanation_drops_private_signal_details() {
        let (signals, contradictions) = explanation(
            r#"{"group_contributions":{"identity":1.0,"private-token":0.12,"contact":"personal"},"contradictions":[{"name":"conflicting_identifier","group":"contradiction","weight":0.24,"value":true,"details":{"identifier":"private-token"}},{"name":"private-token","group":"private-token","weight":0.99,"value":true}] }"#,
        );
        assert_eq!(signals["identity"], 1.0);
        assert!(signals.get("private-token").is_none());
        assert!(signals.get("contact").is_none());
        assert_eq!(contradictions[0]["name"], "conflicting_identifier");
        assert!(contradictions[0].get("details").is_none());
        assert!(!contradictions.to_string().contains("private-token"));
    }

    impl Default for PublicGraphQuery {
        fn default() -> Self {
            Self {
                profile: None,
                release_id: None,
                q: None,
                entity_type: None,
                entity_id: None,
                connection_type: None,
                min_confidence: None,
                max_confidence: None,
                confidence_band: None,
                include_conflicting: None,
                source_id: None,
                cursor: None,
                limit: None,
                direction: None,
                depth: None,
            }
        }
    }
}
