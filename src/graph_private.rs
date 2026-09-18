use crate::{ApiState, v2_error};
use axum::{
    Json,
    extract::{Path, Query, State},
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
};
use serde::Deserialize;
use serde_json::json;
use uuid::Uuid;

const TOKEN_HEADER: &str = "x-uec-private-graph-token";
const MAX_LIMIT: i64 = 100;

#[derive(Debug, Deserialize)]
pub struct GraphQuery {
    pub q: Option<String>,
    pub relationship_type: Option<String>,
    pub source_id: Option<String>,
    pub state: Option<String>,
    pub min_confidence: Option<f64>,
    pub from: Option<chrono::NaiveDate>,
    pub to: Option<chrono::NaiveDate>,
    pub direction: Option<String>,
    pub depth: Option<i32>,
    pub limit: Option<i64>,
    pub cursor: Option<Uuid>,
}

pub(crate) fn authorized(headers: &HeaderMap) -> bool {
    let Some(expected) = std::env::var("UEC_PRIVATE_GRAPH_TOKEN")
        .ok()
        .filter(|v| !v.is_empty())
    else {
        return false;
    };
    headers
        .get(TOKEN_HEADER)
        .and_then(|v| v.to_str().ok())
        .is_some_and(|v| crate::constant_time_token_matches(&expected, v))
}
fn limit(v: Option<i64>) -> Result<i64, &'static str> {
    let n = v.unwrap_or(50);
    if (1..=MAX_LIMIT).contains(&n) {
        Ok(n)
    } else {
        Err("limit must be between 1 and 100")
    }
}
fn denied() -> axum::response::Response {
    v2_error(
        StatusCode::NOT_FOUND,
        "private_graph_unavailable",
        "private graph unavailable",
    )
}
fn bad(msg: &'static str) -> axum::response::Response {
    v2_error(StatusCode::BAD_REQUEST, "invalid_graph_query", msg)
}

pub async fn entities(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Query(p): Query<GraphQuery>,
) -> impl IntoResponse {
    if !authorized(&headers) {
        return denied();
    }
    let Ok(limit) = limit(p.limit) else {
        return bad("limit must be between 1 and 100");
    };
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_not_configured",
            "private graph database unavailable",
        );
    };
    let Ok(client) = pool.get().await else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_pool_unavailable",
            "private graph database unavailable",
        );
    };
    let q = p.q.unwrap_or_default();
    let rows = match client.query("SELECT entity_id, entity_type, canonical_name, country_code, created_at FROM (SELECT facility_id AS entity_id, 'facility' AS entity_type, canonical_name, country_code, created_at FROM uec.facilities UNION ALL SELECT organization_id, 'organization', canonical_name, country_code, created_at FROM uec.organizations) e WHERE ($1 = '' OR canonical_name ILIKE '%' || $1 || '%') AND ($2::uuid IS NULL OR entity_id > $2) ORDER BY entity_id LIMIT $3", &[&q, &p.cursor, &limit]).await { Ok(v) => v, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "private_graph_query_failed", "private graph query failed") };
    let data: Vec<_> = rows.into_iter().map(|r| json!({"entity_id":r.get::<_,Uuid>(0),"entity_type":r.get::<_,String>(1),"canonical_name":r.get::<_,Option<String>>(2),"country_code":r.get::<_,Option<String>>(3),"created_at":r.get::<_,chrono::DateTime<chrono::Utc>>(4)})).collect();
    Json(json!({"api_version":"private-graph-v1","data":data,"meta":{"private":true,"limit":limit,"next_cursor":data.last().and_then(|v|v["entity_id"].as_str())}})).into_response()
}

pub async fn neighborhood(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Path(entity_id): Path<Uuid>,
    Query(p): Query<GraphQuery>,
) -> impl IntoResponse {
    if !authorized(&headers) {
        return denied();
    }
    let Ok(limit) = limit(p.limit) else {
        return bad("limit must be between 1 and 100");
    };
    let direction = p.direction.as_deref().unwrap_or("both");
    if !["in", "out", "both"].contains(&direction) {
        return bad("direction must be in, out, or both");
    }
    let depth = p.depth.unwrap_or(1).clamp(1, 2);
    if p.relationship_type.as_deref().is_some_and(|v| {
        ![
            "operator",
            "owner",
            "parent",
            "brand",
            "supplier",
            "customer",
            "regulatory_authority_for",
        ]
        .contains(&v)
    }) {
        return bad("unsupported relationship type");
    }
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_not_configured",
            "private graph database unavailable",
        );
    };
    let Ok(client) = pool.get().await else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_pool_unavailable",
            "private graph database unavailable",
        );
    };
    let rows = match client.query("WITH RECURSIVE observations AS (SELECT relationship_observation_id, from_organization_id, target_facility_id, target_organization_id, relationship_type, assertion_status, observed_at, confidence, review_state, storage_state, privacy_status, publication_status, source_id, source_record_id FROM uec.organization_relationship_observations WHERE ($4::text IS NULL OR relationship_type=$4) AND ($5::text IS NULL OR source_id=$5) AND ($6::timestamptz IS NULL OR observed_at >= $6) AND ($7::timestamptz IS NULL OR observed_at < $7)), edges AS (SELECT o.*, 'organization'::text AS from_type, o.from_organization_id AS from_id, CASE WHEN o.target_facility_id IS NOT NULL THEN 'facility'::text ELSE 'organization'::text END AS to_type, COALESCE(o.target_facility_id, o.target_organization_id) AS to_id FROM observations o), seed AS (SELECT 'organization'::text AS node_type, $1::uuid AS node_id, 0 AS hop WHERE EXISTS (SELECT 1 FROM uec.organizations WHERE organization_id=$1) UNION ALL SELECT 'facility'::text, $1::uuid, 0 WHERE EXISTS (SELECT 1 FROM uec.facilities WHERE facility_id=$1)), walk(node_type, node_id, hop) AS (SELECT node_type, node_id, hop FROM seed UNION SELECT CASE WHEN $2 IN ('out','both') THEN e.to_type ELSE e.from_type END, CASE WHEN $2 IN ('out','both') THEN e.to_id ELSE e.from_id END, w.hop + 1 FROM walk w JOIN edges e ON (($2 IN ('out','both') AND e.from_type=w.node_type AND e.from_id=w.node_id) OR ($2 IN ('in','both') AND e.to_type=w.node_type AND e.to_id=w.node_id)) WHERE w.hop < $3), matched AS (SELECT DISTINCT e.relationship_observation_id FROM edges e JOIN walk w ON w.hop < $3 AND (($2 IN ('out','both') AND e.from_type=w.node_type AND e.from_id=w.node_id) OR ($2 IN ('in','both') AND e.to_type=w.node_type AND e.to_id=w.node_id))) SELECT o.relationship_observation_id, o.from_organization_id, o.target_facility_id, o.target_organization_id, o.relationship_type, o.assertion_status, o.observed_at, o.confidence, o.review_state, o.storage_state, o.privacy_status, o.publication_status, o.source_id, o.source_record_id FROM observations o JOIN matched m USING (relationship_observation_id) ORDER BY o.observed_at DESC, o.relationship_observation_id DESC LIMIT $8", &[&entity_id, &direction, &depth, &p.relationship_type, &p.source_id, &p.from.map(|d| d.and_hms_opt(0,0,0).unwrap().and_utc()), &p.to.map(|d| d.and_hms_opt(0,0,0).unwrap().and_utc()), &limit]).await { Ok(v) => v, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "private_graph_query_failed", "private graph query failed") };
    let data: Vec<_> = rows.into_iter().map(|r| json!({"relationship_observation_id":r.get::<_,Uuid>(0),"from_organization_id":r.get::<_,Option<Uuid>>(1),"target_facility_id":r.get::<_,Option<Uuid>>(2),"target_organization_id":r.get::<_,Option<Uuid>>(3),"relationship_type":r.get::<_,Option<String>>(4),"assertion_status":r.get::<_,String>(5),"observed_at":r.get::<_,chrono::DateTime<chrono::Utc>>(6),"confidence":r.get::<_,Option<f64>>(7),"review_state":r.get::<_,String>(8),"storage_state":r.get::<_,String>(9),"privacy_status":r.get::<_,String>(10),"publication_status":r.get::<_,String>(11),"source_id":r.get::<_,String>(12),"source_record_id":r.get::<_,Uuid>(13)})).collect();
    Json(json!({"api_version":"private-graph-v1","data":data,"meta":{"private":true,"entity_id":entity_id,"limit":limit,"direction":direction,"depth":depth,"bounded":true}})).into_response()
}

pub async fn queue(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Path(kind): Path<String>,
    Query(p): Query<GraphQuery>,
) -> impl IntoResponse {
    if !authorized(&headers) {
        return denied();
    }
    let Ok(limit) = limit(p.limit) else {
        return bad("limit must be between 1 and 100");
    };
    if ![
        "contradictions",
        "unresolved-identities",
        "quarantine",
        "claims",
        "rejected-candidates",
        "suppression",
        "statistics",
    ]
    .contains(&kind.as_str())
    {
        return v2_error(
            StatusCode::NOT_FOUND,
            "private_graph_unavailable",
            "private graph unavailable",
        );
    }
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_not_configured",
            "private graph database unavailable",
        );
    };
    let Ok(client) = pool.get().await else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_pool_unavailable",
            "private graph database unavailable",
        );
    };
    let sql = match kind.as_str() {
        "contradictions" => {
            "SELECT claim_id::text, facility_id::text, organization_id::text, claim_domain, claim_kind, observed_at::text, confidence::text, review_state, privacy_status, publication_status FROM uec.claim_current c WHERE c.review_state IN ('disputed','review_required') ORDER BY observed_at DESC, claim_id DESC LIMIT $1"
        }
        "unresolved-identities" => {
            "SELECT crosswalk_id::text, left_identifier_id::text, right_identifier_id::text, assertion_status, confidence::text, observed_at::text, source_id, source_record_id::text, review_state, privacy_status, publication_status FROM uec.source_entity_crosswalks WHERE assertion_status IN ('candidate','review_required','disputed') ORDER BY observed_at DESC, crosswalk_id DESC LIMIT $1"
        }
        "quarantine" => {
            "SELECT source_record_id::text, source_id, source_state, received_at::text FROM uec.source_records WHERE source_state IN ('quarantined','rejected') ORDER BY received_at DESC, source_record_id DESC LIMIT $1"
        }
        "claims" => {
            "SELECT c.claim_id::text, c.source_id, c.claim_domain, c.claim_kind, c.value_state, c.unknown_reason, c.observed_at::text, c.confidence::text, c.review_state, c.storage_state, c.privacy_status, c.publication_status, COUNT(s.claim_support_id)::text AS support_count, COUNT(s.claim_support_id) FILTER (WHERE s.support_role = 'contradicting')::text AS contradicting_support_count FROM uec.claim_current c LEFT JOIN uec.claim_support s ON s.claim_id = c.claim_id GROUP BY c.claim_id, c.source_id, c.claim_domain, c.claim_kind, c.value_state, c.unknown_reason, c.observed_at, c.confidence, c.review_state, c.storage_state, c.privacy_status, c.publication_status ORDER BY c.observed_at DESC, c.claim_id DESC LIMIT $1"
        }
        "rejected-candidates" => {
            "SELECT crosswalk_id::text, source_id, source_record_id::text, assertion_status, confidence::text, observed_at::text, review_state, privacy_status, publication_status FROM uec.source_entity_crosswalks WHERE assertion_status = 'rejected' OR review_state = 'rejected' ORDER BY observed_at DESC, crosswalk_id DESC LIMIT $1"
        }
        "suppression" => {
            "SELECT cases.case_id::text, cases.status, current_case.event_type, current_case.reason_category, current_case.policy_version, current_case.occurred_at::text FROM uec.suppression_cases cases JOIN uec.suppression_case_current current_case ON current_case.case_id = cases.case_id ORDER BY current_case.occurred_at DESC, cases.case_id DESC LIMIT $1"
        }
        _ => {
            "SELECT metric, value::text FROM (SELECT 'claims' AS metric, count(*)::bigint AS value FROM uec.claims UNION ALL SELECT 'relationships', count(*) FROM uec.organization_relationship_observations UNION ALL SELECT 'quarantined_records', count(*) FROM uec.source_records WHERE source_state IN ('quarantined','rejected') UNION ALL SELECT 'suppression_cases', count(*) FROM uec.suppression_cases) metrics ORDER BY metric LIMIT $1"
        }
    };
    let rows = match client.query(sql, &[&limit]).await {
        Ok(v) => v,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "private_graph_query_failed",
                "private graph query failed",
            );
        }
    };
    let data: Vec<_> = rows
        .into_iter()
        .map(|r| {
            (0..r.len())
                .map(|i| {
                    r.try_get::<_, String>(i)
                        .or_else(|_| r.try_get::<_, i64>(i).map(|v| v.to_string()))
                        .unwrap_or_default()
                })
                .collect::<Vec<_>>()
        })
        .collect();
    Json(json!({"api_version":"private-graph-v1","data":data,"meta":{"private":true,"queue":kind,"limit":limit}})).into_response()
}
