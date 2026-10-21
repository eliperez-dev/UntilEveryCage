//! Release-scoped, read-only public accountability graph projection.
//!
//! The graph edge table is private evidence. These handlers only return rows
//! whose source-qualified endpoints are themselves present in the selected
//! promoted public release. No raw evidence, source-record identifiers,
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
const GRAPH_CONNECTION_PLANNER_SETTING: &str = "SET LOCAL enable_nestloop=off";

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
    let (signals, contradictions) = explanation(&row.get::<_, String>(15));
    let from_identifier_type: String = row.get(4);
    let to_identifier_type: String = row.get(9);
    let from_public_identifier = public_identifier(row.get(1));
    let to_public_identifier = public_identifier(row.get(6));
    json!({
        "connection_edge_id": row.get::<_, Uuid>(0),
        "from": {"entity_id": row.get::<_, Option<Uuid>>(1), "entity_type": row.get::<_, String>(2), "source_id": row.get::<_, String>(3), "identifier_type": from_identifier_type, "source_identifier": from_public_identifier},
        "to": {"entity_id": row.get::<_, Option<Uuid>>(6), "entity_type": row.get::<_, String>(7), "source_id": row.get::<_, String>(8), "identifier_type": to_identifier_type, "source_identifier": to_public_identifier},
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

fn public_identifier(entity_id: Option<Uuid>) -> String {
    entity_id
        .map(|id| format!("entity:{id}"))
        .unwrap_or_else(|| "entity:unavailable".to_string())
}

const EDGE_CTES: &str = "
    record_facility_candidates AS MATERIALIZED (
      SELECT DISTINCT p.source_record_id, p.facility_id
      FROM uec.map_facilities_public_discovery_read_model p
      WHERE p.release_id=$1
    ),
    ambiguous_record_facilities AS MATERIALIZED (
      SELECT source_record_id
      FROM record_facility_candidates
      GROUP BY source_record_id
      HAVING count(*)>1
    ),
    record_facilities AS MATERIALIZED (
      SELECT candidate.source_record_id, candidate.facility_id
      FROM record_facility_candidates candidate
      LEFT JOIN ambiguous_record_facilities ambiguous USING (source_record_id)
      WHERE ambiguous.source_record_id IS NULL
    ),
    release_support_records AS MATERIALIZED (
      SELECT DISTINCT record.source_id, record.source_record_id, record.artifact_id
      FROM record_facilities rf
      JOIN uec.source_records record ON record.source_record_id=rf.source_record_id
      UNION
      SELECT DISTINCT binding.source_id, private_record.source_record_id,
             private_record.artifact_id
      FROM uec.graph_record_release_bindings binding
      JOIN record_facilities rf
        ON rf.source_record_id=binding.canonical_source_record_id
       AND rf.facility_id=binding.facility_id
      JOIN uec.source_records canonical_record
        ON canonical_record.source_record_id=binding.canonical_source_record_id
       AND canonical_record.source_id=binding.source_id
       AND canonical_record.artifact_id=binding.artifact_id
      JOIN uec.source_records private_record
        ON private_record.source_record_id=binding.private_source_record_id
       AND private_record.source_id=binding.source_id
       AND private_record.artifact_id=binding.artifact_id
      WHERE binding.release_id=$1
    ),
    edge_support_refs AS MATERIALIZED (
      SELECT edge.connection_edge_id,
             refs.value->>'source_id' AS source_id,
             refs.value->>'source_record_id' AS source_record_id
      FROM uec.graph_connection_edges edge
      CROSS JOIN LATERAL jsonb_array_elements(edge.supporting_source_refs)
        AS refs(value)
      WHERE edge.suppressed=false AND edge.storage_state='private'
        AND edge.publication_status='not_eligible'
    ),
    eligible_edge_supports AS MATERIALIZED (
      SELECT refs.connection_edge_id
      FROM edge_support_refs refs
      LEFT JOIN release_support_records record
        ON record.source_id=refs.source_id
       AND record.source_record_id::text=refs.source_record_id
      GROUP BY refs.connection_edge_id
      HAVING count(*)=count(record.source_record_id)
    ),
    facility_assertions AS MATERIALIZED (
      SELECT DISTINCT i.source_record_id, i.facility_id
      FROM uec.source_entity_identifiers i
      JOIN record_facilities rf ON rf.source_record_id=i.source_record_id
                               AND rf.facility_id=i.facility_id
      WHERE i.entity_type='facility'
    ),
    endpoint_candidates AS MATERIALIZED (
      SELECT i.source_id, i.identifier_type, i.source_identifier, i.entity_type,
             i.facility_id AS public_entity_id
      FROM uec.source_entity_identifiers i
      JOIN record_facilities rf ON rf.source_record_id=i.source_record_id
      WHERE i.entity_type='facility' AND i.facility_id=rf.facility_id
      UNION ALL
      SELECT i.source_id, i.identifier_type, i.source_identifier, i.entity_type,
             i.organization_id AS public_entity_id
      FROM uec.source_entity_identifiers i
      JOIN record_facilities rf ON rf.source_record_id=i.source_record_id
      JOIN facility_assertions asserted_facility
        ON asserted_facility.source_record_id=i.source_record_id
       AND asserted_facility.facility_id=rf.facility_id
      WHERE i.entity_type='organization'
        AND i.identifier_type IN ('vat','vat_number','italian_vat','p_iva')
        AND i.organization_id IS NOT NULL
    ),
    distinct_endpoint_candidates AS MATERIALIZED (
      SELECT DISTINCT source_id, identifier_type, source_identifier, entity_type, public_entity_id
      FROM endpoint_candidates
    ),
    ambiguous_source_endpoints AS MATERIALIZED (
      SELECT source_id, identifier_type, source_identifier, entity_type
      FROM distinct_endpoint_candidates
      GROUP BY source_id, identifier_type, source_identifier, entity_type
      HAVING count(*)>1
    ),
    eligible_source_endpoints AS MATERIALIZED (
      SELECT candidate.source_id, candidate.identifier_type,
             candidate.source_identifier, candidate.entity_type, candidate.public_entity_id
      FROM distinct_endpoint_candidates candidate
      LEFT JOIN ambiguous_source_endpoints ambiguous
        USING (source_id, identifier_type, source_identifier, entity_type)
      WHERE ambiguous.source_id IS NULL
    ),
    edges AS (
    SELECT e.connection_edge_id,
           fi.public_entity_id AS from_entity_id,
           e.from_entity_type, e.from_source_id, e.from_identifier_type,
           e.from_source_identifier,
           ti.public_entity_id AS to_entity_id,
           e.to_entity_type, e.to_source_id, e.to_identifier_type,
           e.to_source_identifier, e.relationship_type, e.connection_type,
           e.confidence::double precision,
           CASE WHEN e.confidence_band = 'probable' THEN 'high'
                WHEN e.confidence_band = 'possible' THEN 'medium'
                ELSE e.confidence_band END AS public_confidence_band,
           e.signal_explanation::text, e.match_method,
           e.observed_at, e.computed_at, e.ruleset_version, e.conflicting
    FROM uec.graph_connection_edges e
    JOIN eligible_source_endpoints fi
      ON fi.source_id=e.from_source_id AND fi.identifier_type=e.from_identifier_type
     AND fi.source_identifier=e.from_source_identifier AND fi.entity_type=e.from_entity_type
    JOIN eligible_source_endpoints ti
      ON ti.source_id=e.to_source_id AND ti.identifier_type=e.to_identifier_type
     AND ti.source_identifier=e.to_source_identifier AND ti.entity_type=e.to_entity_type
    JOIN eligible_edge_supports support
      ON support.connection_edge_id=e.connection_edge_id
    WHERE e.suppressed = false
      AND e.storage_state = 'private'
      AND e.publication_status = 'not_eligible'
      AND (
        fi.entity_type = 'facility'
        OR (fi.entity_type = 'organization' AND (
              e.connection_type='inferred'
              OR (e.connection_type='exact' AND e.relationship_type='operator')
           ))
      )
      AND (
        ti.entity_type = 'facility'
        OR (ti.entity_type = 'organization' AND (
              e.connection_type='inferred'
              OR (e.connection_type='exact' AND e.relationship_type='operator')
           ))
      ))";

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
    // Planner statistics badly understate the grouped endpoint CTE cardinality
    // (two estimated endpoints versus tens of thousands in the controlled
    // release). A bounded clone diagnostic showed the hash-join plan finishing
    // in 6.3s; keep this setting local to the read-only graph transaction.
    if transaction
        .batch_execute(GRAPH_CONNECTION_PLANNER_SETTING)
        .await
        .is_err()
    {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "public_graph_query_failed",
            "public graph query planning failed",
        );
    }
    let bands = match query.confidence_band.as_deref() {
        Some("high") => Some(vec!["high", "probable"]),
        Some("medium") => Some(vec!["medium", "possible"]),
        Some("low") => Some(vec!["low"]),
        Some("exact") => Some(vec!["exact"]),
        _ => None,
    };
    let include_conflicting = query.include_conflicting.unwrap_or(false);
    let sql = format!("WITH {EDGE_CTES} SELECT * FROM edges WHERE ($2::text IS NULL OR connection_type = $2) AND ($3::double precision IS NULL OR confidence >= $3) AND ($4::double precision IS NULL OR confidence <= $4) AND ($5::text[] IS NULL OR public_confidence_band = ANY($5)) AND ($6 OR conflicting = false) AND ($7::text IS NULL OR from_source_id = $7 OR to_source_id = $7) AND ($8::uuid IS NULL OR from_entity_id = $8 OR to_entity_id = $8) AND ($9::uuid IS NULL OR connection_edge_id < $9) ORDER BY connection_edge_id DESC LIMIT $10");
    let rows = match transaction
        .query(
            &sql,
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
                &limit,
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
            )
        }
    };
    let data: Vec<Value> = rows
        .iter()
        .map(|row| public_edge(row, &release_id))
        .collect();
    let next_cursor = data
        .last()
        .and_then(|row| row.get("connection_edge_id"))
        .cloned();
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
        SELECT entity_id, entity_type, canonical_name, country_code FROM (
          SELECT p.facility_id AS entity_id, 'facility'::text AS entity_type,
                 p.canonical_name, p.country_code
          FROM uec.map_facilities_public_discovery_read_model p WHERE p.release_id=$1
          UNION
          SELECT DISTINCT o.organization_id, 'organization', o.canonical_name, o.country_code
          FROM uec.organizations o
          JOIN uec.source_entity_identifiers i ON i.organization_id=o.organization_id AND i.entity_type='organization'
          WHERE i.identifier_type IN ('vat','vat_number','italian_vat','p_iva')
            AND o.organization_type IN ('company','cooperative') AND i.release_id=$1
            AND i.storage_state='released' AND i.publication_status='released' AND i.privacy_status='passed'
          UNION
          SELECT DISTINCT i.organization_id, 'organization'::text, NULL::text, p.country_code
          FROM uec.graph_connection_edges e
          JOIN uec.source_entity_identifiers i
            ON i.source_id=e.from_source_id AND i.identifier_type=e.from_identifier_type
           AND i.source_identifier=e.from_source_identifier AND i.entity_type='organization'
          JOIN uec.map_facilities_public_discovery_read_model p
            ON p.release_id=$1 AND p.source_record_id=i.source_record_id
          WHERE e.connection_type='exact' AND e.relationship_type='operator'
            AND e.suppressed=false AND e.storage_state='private' AND e.publication_status='not_eligible'
            AND i.identifier_type IN ('vat','vat_number','italian_vat','p_iva')
            AND EXISTS (SELECT 1 FROM uec.source_entity_identifiers facility
                        WHERE facility.source_record_id=i.source_record_id
                          AND facility.entity_type='facility' AND facility.facility_id=p.facility_id)
            AND (SELECT count(DISTINCT candidate.organization_id)
                 FROM uec.source_entity_identifiers candidate
                 WHERE candidate.entity_type='organization' AND candidate.source_id=i.source_id
                   AND candidate.identifier_type=i.identifier_type
                   AND candidate.source_identifier=i.source_identifier)=1
          UNION
          SELECT DISTINCT i.organization_id, 'organization'::text, NULL::text, p.country_code
          FROM uec.graph_connection_edges e
          JOIN uec.source_entity_identifiers i
            ON i.source_id=e.to_source_id AND i.identifier_type=e.to_identifier_type
           AND i.source_identifier=e.to_source_identifier AND i.entity_type='organization'
          JOIN uec.map_facilities_public_discovery_read_model p
            ON p.release_id=$1 AND p.source_record_id=i.source_record_id
          WHERE e.connection_type='exact' AND e.relationship_type='operator'
            AND e.suppressed=false AND e.storage_state='private' AND e.publication_status='not_eligible'
            AND i.identifier_type IN ('vat','vat_number','italian_vat','p_iva')
            AND EXISTS (SELECT 1 FROM uec.source_entity_identifiers facility
                        WHERE facility.source_record_id=i.source_record_id
                          AND facility.entity_type='facility' AND facility.facility_id=p.facility_id)
            AND (SELECT count(DISTINCT candidate.organization_id)
                 FROM uec.source_entity_identifiers candidate
                 WHERE candidate.entity_type='organization' AND candidate.source_id=i.source_id
                   AND candidate.identifier_type=i.identifier_type
                   AND candidate.source_identifier=i.source_identifier)=1
        ) entities
        WHERE ($2 = '' OR canonical_name ILIKE '%' || $2 || '%')
          AND ($3::text IS NULL OR entity_type=$3)
          AND ($4::uuid IS NULL OR entity_id < $4)
        ORDER BY entity_id DESC LIMIT $5
    "#, &[&release_id, &q, &query.entity_type, &query.cursor, &limit]).await { Ok(rows) => rows, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "public_graph_query_failed", "public graph entity search failed") };
    let data: Vec<Value> = rows.iter().map(|row| json!({"entity_id": row.get::<_, Uuid>(0), "entity_type": row.get::<_, String>(1), "display_name": row.get::<_, Option<String>>(2), "country_code": row.get::<_, Option<String>>(3)})).collect();
    let next_cursor = data.last().and_then(|row| row.get("entity_id")).cloned();
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
        assert!(
            EDGE_CTES.contains("i.identifier_type IN ('vat','vat_number','italian_vat','p_iva')")
        );
        assert!(EDGE_CTES.contains("e.connection_type='inferred'"));
        assert!(EDGE_CTES.contains("e.connection_type='exact' AND e.relationship_type='operator'"));
        assert!(!EDGE_CTES.contains("SELECT DISTINCT e.connection_edge_id"));
        assert!(!EDGE_CTES.contains("count(DISTINCT CASE"));
    }

    #[test]
    fn inferred_business_links_require_eligible_nodes_and_versioned_support() {
        assert!(
            EDGE_CTES.contains("i.identifier_type IN ('vat','vat_number','italian_vat','p_iva')")
        );
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
