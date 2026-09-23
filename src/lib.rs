// Until Every Cage is Empty
// Copyright (C) 2025 Eli Perez
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program. If not, see <https://www.gnu.org/licenses/>.

// Contact the developer directly at untileverycageproject@protonmail.com
use axum::extract::{Path, Query, State};
use axum::http::{HeaderMap, HeaderValue};
use axum::{
    Json,
    http::{Response, StatusCode},
    response::IntoResponse,
};
use deadpool_postgres::Pool;
use include_dir::{Dir, include_dir};
use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::error::Error;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;

pub mod graph_private;
pub mod graph_public;

pub fn v2_error(
    status: StatusCode,
    code: &'static str,
    message: &'static str,
) -> Response<axum::body::Body> {
    (
        status,
        Json(json!({"api_version":"v2", "error": {"code": code, "message": message}})),
    )
        .into_response()
}

#[derive(Debug, Deserialize)]
pub struct PrivateGraphSearchParams {
    pub q: Option<String>,
    pub limit: Option<i64>,
}

/// Private evidence-only graph search. This is intentionally not a public projection.
pub async fn get_private_graph_search_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Query(params): Query<PrivateGraphSearchParams>,
) -> impl IntoResponse {
    if !graph_private::authorized(&headers) {
        return v2_error(
            StatusCode::NOT_FOUND,
            "private_graph_unavailable",
            "private graph unavailable",
        );
    }
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "private_graph_unavailable",
            "private graph database unavailable",
        );
    };
    let q = params.q.unwrap_or_default().trim().to_string();
    let limit = params.limit.unwrap_or(25).clamp(1, 100);
    let client = match pool.get().await {
        Ok(c) => c,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "private_graph_unavailable",
                "private graph database unavailable",
            );
        }
    };
    let rows = match client.query("SELECT entity_type, entity_id, display_name, source_id, source_identifier, observed_at FROM (SELECT 'facility' AS entity_type, f.facility_id AS entity_id, COALESCE(f.canonical_name, '[unnamed facility]') AS display_name, sei.source_id, sei.source_identifier, sei.observed_at FROM uec.facilities f LEFT JOIN uec.source_entity_identifiers sei ON sei.facility_id=f.facility_id UNION ALL SELECT 'organization', o.organization_id, COALESCE(o.canonical_name, '[unnamed organization]'), sei.source_id, sei.source_identifier, sei.observed_at FROM uec.organizations o LEFT JOIN uec.source_entity_identifiers sei ON sei.organization_id=o.organization_id) entities WHERE ($1='' OR display_name ILIKE '%' || $1 || '%' OR source_identifier ILIKE '%' || $1 || '%') ORDER BY display_name, observed_at DESC NULLS LAST, entity_id, entity_type LIMIT $2", &[&q, &limit]).await { Ok(r) => r, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "private_graph_query_failed", "private graph search failed") };
    let data: Vec<Value> = rows.into_iter().map(|r| json!({"entity_type":r.get::<_,String>(0),"entity_id":r.get::<_,uuid::Uuid>(1),"display_name":r.get::<_,String>(2),"source_id":r.get::<_,Option<String>>(3),"source_identifier":r.get::<_,Option<String>>(4),"observed_at":r.get::<_,Option<chrono::DateTime<chrono::Utc>>>(5),"review_state":"unknown","privacy_status":"unknown","publication_status":"unknown"})).collect();
    Json(json!({"api_version":"private-graph-v1","data":data,"meta":{"scope":"private_evidence_only","bounded":true,"public_projection":false}})).into_response()
}

#[derive(Debug, Deserialize)]
pub struct PrivateGraphTraverseParams {
    pub entity_type: String,
    pub entity_id: uuid::Uuid,
    pub direction: Option<String>,
    pub depth: Option<i32>,
}

pub async fn get_private_graph_traverse_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Query(params): Query<PrivateGraphTraverseParams>,
) -> impl IntoResponse {
    if !graph_private::authorized(&headers) {
        return v2_error(
            StatusCode::NOT_FOUND,
            "private_graph_unavailable",
            "private graph unavailable",
        );
    }
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "private_graph_unavailable",
            "private graph database unavailable",
        );
    };
    let depth = params.depth.unwrap_or(1).clamp(1, 2);
    let direction = params.direction.as_deref().unwrap_or("both");
    if !matches!(params.entity_type.as_str(), "organization" | "facility")
        || !matches!(direction, "in" | "out" | "both")
    {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_traversal",
            "entity type, direction, or depth is invalid",
        );
    }
    let client = match pool.get().await {
        Ok(c) => c,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "private_graph_unavailable",
                "private graph database unavailable",
            );
        }
    };
    let rows = match client.query("WITH RECURSIVE observations AS (SELECT relationship_observation_id, source_id, source_record_id, from_organization_id, target_facility_id, target_organization_id, relationship_type, assertion_status, unknown_reason, valid_from, valid_to, observed_at, confidence::double precision AS confidence, review_state, storage_state, privacy_status, publication_status FROM uec.organization_relationship_observations), edges AS (SELECT o.*, 'organization'::text AS from_type, o.from_organization_id AS from_id, CASE WHEN o.target_facility_id IS NOT NULL THEN 'facility'::text ELSE 'organization'::text END AS to_type, COALESCE(o.target_facility_id, o.target_organization_id) AS to_id FROM observations o), directions(step_direction) AS (SELECT 'out'::text WHERE $3 IN ('out','both') UNION ALL SELECT 'in'::text WHERE $3 IN ('in','both')), walk(node_type, node_id, hop) AS (SELECT $1::text, $2::uuid, 0 UNION SELECT CASE WHEN d.step_direction='out' THEN e.to_type ELSE e.from_type END, CASE WHEN d.step_direction='out' THEN e.to_id ELSE e.from_id END, w.hop + 1 FROM walk w JOIN directions d ON true JOIN edges e ON ((d.step_direction='out' AND e.from_type=w.node_type AND e.from_id=w.node_id) OR (d.step_direction='in' AND e.to_type=w.node_type AND e.to_id=w.node_id)) WHERE w.hop < $4), matched AS (SELECT DISTINCT e.relationship_observation_id FROM edges e JOIN walk w ON w.hop < $4 AND (($3 IN ('out','both') AND e.from_type=w.node_type AND e.from_id=w.node_id) OR ($3 IN ('in','both') AND e.to_type=w.node_type AND e.to_id=w.node_id))) SELECT o.relationship_observation_id, o.source_id, o.source_record_id, o.from_organization_id, o.target_facility_id, o.target_organization_id, o.relationship_type, o.assertion_status, o.unknown_reason, o.valid_from, o.valid_to, o.observed_at, o.confidence, o.review_state, o.storage_state, o.privacy_status, o.publication_status FROM observations o JOIN matched m USING (relationship_observation_id) ORDER BY o.observed_at DESC, o.relationship_observation_id DESC LIMIT 200", &[&params.entity_type, &params.entity_id, &direction, &depth]).await { Ok(r) => r, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "private_graph_query_failed", "private graph traversal failed") };
    let data: Vec<Value> = rows.into_iter().map(|r| json!({"relationship_observation_id":r.get::<_,uuid::Uuid>(0),"source_id":r.get::<_,String>(1),"source_record_id":r.get::<_,uuid::Uuid>(2),"from_organization_id":r.get::<_,Option<uuid::Uuid>>(3),"target_facility_id":r.get::<_,Option<uuid::Uuid>>(4),"target_organization_id":r.get::<_,Option<uuid::Uuid>>(5),"relationship_type":r.get::<_,Option<String>>(6),"assertion_status":r.get::<_,String>(7),"unknown_reason":r.get::<_,Option<String>>(8),"valid_from":r.get::<_,Option<chrono::NaiveDate>>(9),"valid_to":r.get::<_,Option<chrono::NaiveDate>>(10),"observed_at":r.get::<_,chrono::DateTime<chrono::Utc>>(11),"confidence":r.get::<_,Option<f64>>(12),"review_state":r.get::<_,String>(13),"storage_state":r.get::<_,String>(14),"privacy_status":r.get::<_,String>(15),"publication_status":r.get::<_,String>(16)})).collect();
    Json(json!({"api_version":"private-graph-v1","data":data,"meta":{"scope":"private_evidence_only","bounded":true,"depth":depth,"direction":direction,"contradictions_preserved":true,"public_projection":false}})).into_response()
}

fn canonical_json(value: &Value) -> String {
    match value {
        Value::Object(map) => {
            let mut keys: Vec<_> = map.keys().collect();
            keys.sort();
            format!(
                "{{{}}}",
                keys.into_iter()
                    .map(|k| format!(
                        "{}:{}",
                        serde_json::to_string(k).unwrap(),
                        canonical_json(&map[k])
                    ))
                    .collect::<Vec<_>>()
                    .join(",")
            )
        }
        Value::Array(items) => format!(
            "[{}]",
            items
                .iter()
                .map(canonical_json)
                .collect::<Vec<_>>()
                .join(",")
        ),
        _ => value.to_string(),
    }
}

pub async fn get_v2_release_manifest_handler(
    State(state): State<ApiState>,
    Query(params): Query<ProfileParams>,
) -> impl IntoResponse {
    let profile = params.profile.as_deref().unwrap_or("official");
    if !["official", "secondary", "community"].contains(&profile) {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_profile",
            "profile is unsupported",
        );
    }
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_not_configured",
            "V2 database is not configured",
        );
    };
    let client = match pool.get().await {
        Ok(c) => c,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "database_pool_unavailable",
                "database pool unavailable",
            );
        }
    };
    let row = match client.query_opt("SELECT r.release_id, r.profile, m.manifest::text, m.manifest_sha256 FROM uec.releases r JOIN uec.release_manifests m ON m.release_id=r.release_id WHERE r.status='promoted' AND r.test_only IS NOT TRUE AND r.profile=$1 ORDER BY r.created_at DESC, r.release_id DESC LIMIT 1", &[&profile]).await {
        Ok(row) => row, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "release_manifest_unavailable", "release manifest unavailable")
    };
    let Some(row) = row else {
        return v2_error(
            StatusCode::NOT_FOUND,
            "release_not_found",
            "no promoted eligible release",
        );
    };
    let manifest_text: String = row.get(2);
    let manifest: Value = match serde_json::from_str(&manifest_text) {
        Ok(value) => value,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "release_manifest_invalid",
                "release manifest integrity check failed",
            );
        }
    };
    let digest: String = row.get(3);
    let actual = format!("{:x}", Sha256::digest(canonical_json(&manifest).as_bytes()));
    if actual != digest {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "release_manifest_invalid",
            "release manifest integrity check failed",
        );
    }
    Json(json!({"api_version":"v2", "data": {"release_id": row.get::<_,String>(0), "profile": row.get::<_,String>(1), "manifest": manifest, "manifest_sha256": digest}})).into_response()
}

#[derive(Serialize)]
struct V2ExportRow {
    facility_id: uuid::Uuid,
    canonical_name: Option<String>,
    country_code: String,
    city: Option<String>,
    category: String,
    display_precision: String,
    factual_review_status: String,
    privacy_screening_status: String,
    project_approval: String,
    reviewer_role: Option<String>,
    source_type: String,
    provenance_source_id: String,
    provenance_source_name: String,
    provenance_source_url: String,
    provenance_retrieved_at: chrono::DateTime<chrono::Utc>,
    source_rights_status: String,
    release_id: String,
    release_profile: String,
    profile_notice: String,
    publication_warning: Option<String>,
    manifest_sha256: String,
}

const UNREVIEWED_COMMUNITY_WARNING: &str =
    "Unreviewed community claim — not verified by Until Every Cage";
const COMMUNITY_EXPORT_NOTICE: &str = "Opt-in community profile: privacy-screened claims may be factually unreviewed and are not necessarily project-approved.";

fn export_profile_notice(profile: &str) -> &'static str {
    if profile == "community" {
        COMMUNITY_EXPORT_NOTICE
    } else {
        "Curated release profile: rows require project approval and privacy screening."
    }
}

fn export_publication_warning(profile: &str, factual_review_status: &str) -> Option<String> {
    (profile == "community" && factual_review_status == "unreviewed")
        .then(|| UNREVIEWED_COMMUNITY_WARNING.to_string())
}

fn csv_safe_option(value: Option<String>) -> Option<String> {
    value.map(csv_safe_value)
}

pub async fn get_v2_locations_export_handler(
    State(state): State<ApiState>,
    Query(params): Query<ProfileParams>,
) -> impl IntoResponse {
    let profile = params.profile.as_deref().unwrap_or("official");
    if !["official", "secondary", "community"].contains(&profile) {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_profile",
            "profile is unsupported",
        );
    }
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_not_configured",
            "V2 database is not configured",
        );
    };
    let mut client = match pool.get().await {
        Ok(c) => c,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "database_pool_unavailable",
                "database pool unavailable",
            );
        }
    };
    let transaction = match client
        .build_transaction()
        .isolation_level(tokio_postgres::IsolationLevel::RepeatableRead)
        .read_only(true)
        .start()
        .await
    {
        Ok(transaction) => transaction,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "database_transaction_unavailable",
                "V2 database transaction unavailable",
            );
        }
    };
    let release = match transaction.query_opt("SELECT r.release_id, m.manifest_sha256, (model.release_id IS NOT NULL AND manifest.release_id IS NOT NULL) FROM uec.releases r LEFT JOIN uec.public_discovery_read_models model ON model.release_id=r.release_id LEFT JOIN uec.release_manifests manifest ON manifest.release_id=r.release_id AND manifest.manifest_sha256=model.manifest_sha256 LEFT JOIN uec.release_manifests m ON m.release_id=r.release_id WHERE r.status='promoted' AND r.test_only IS NOT TRUE AND r.profile=$1 ORDER BY r.created_at DESC, r.release_id DESC LIMIT 1", &[&profile]).await {
        Ok(row) => row, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "release_query_failed", "release query failed")
    };
    let Some(release) = release else {
        return v2_error(
            StatusCode::NOT_FOUND,
            "release_not_found",
            "no promoted eligible release",
        );
    };
    let release_id: String = release.get(0);
    let manifest_sha256: String = release.get(1);
    if !release.get::<_, bool>(2) {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "read_model_unavailable",
            "public discovery read model is missing or stale",
        );
    }
    let rows = match transaction.query("SELECT h.facility_id, h.canonical_name, h.country_code, h.city, h.classification_category, h.display_precision, h.factual_review_status, h.privacy_screening_status, h.maintainer_approval, h.reviewer_role, h.provenance_origin_type, h.provenance_source_id, h.provenance_source_name, h.provenance_source_url, h.provenance_retrieved_at, h.source_rights_status, h.release_id FROM uec.map_facilities_public_discovery_read_model h WHERE h.release_id=$1 ORDER BY h.facility_id LIMIT 1001", &[&release_id]).await {
        Ok(rows) => rows, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "export_query_failed", "public export unavailable")
    };
    if rows.len() > 1000 {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "export_too_large",
            "export exceeds the bounded limit",
        );
    }
    let mut writer = csv::Writer::from_writer(Vec::new());
    for row in rows {
        let factual_review_status: String = row.get(6);
        if writer
            .serialize(V2ExportRow {
                facility_id: row.get(0),
                canonical_name: csv_safe_option(row.get(1)),
                country_code: csv_safe_value(row.get(2)),
                city: csv_safe_option(row.get(3)),
                category: csv_safe_value(row.get(4)),
                display_precision: csv_safe_value(row.get(5)),
                factual_review_status: csv_safe_value(factual_review_status.clone()),
                privacy_screening_status: csv_safe_value(row.get(7)),
                project_approval: csv_safe_value(row.get(8)),
                reviewer_role: csv_safe_option(row.get(9)),
                source_type: csv_safe_value(row.get(10)),
                provenance_source_id: csv_safe_value(row.get(11)),
                provenance_source_name: csv_safe_value(row.get(12)),
                provenance_source_url: csv_safe_value(row.get(13)),
                provenance_retrieved_at: row.get(14),
                source_rights_status: csv_safe_value(row.get(15)),
                release_id: csv_safe_value(row.get(16)),
                release_profile: csv_safe_value(profile.to_string()),
                profile_notice: csv_safe_value(export_profile_notice(profile).to_string()),
                publication_warning: csv_safe_option(export_publication_warning(
                    profile,
                    &factual_review_status,
                )),
                manifest_sha256: csv_safe_value(manifest_sha256.clone()),
            })
            .is_err()
        {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "export_encoding_failed",
                "public export unavailable",
            );
        }
    }
    let body = match writer.into_inner() {
        Ok(body) => body,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "export_encoding_failed",
                "public export unavailable",
            );
        }
    };
    if transaction.commit().await.is_err() {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_transaction_failed",
            "V2 database transaction failed",
        );
    }
    Response::builder()
        .status(StatusCode::OK)
        .header("content-type", "text/csv; charset=utf-8")
        .header(
            "content-disposition",
            format!("attachment; filename=uec-v2-{profile}-locations.csv"),
        )
        .header("x-uec-release-id", release_id)
        .header("x-uec-export-profile", profile)
        .header("x-uec-manifest-sha256", manifest_sha256)
        .header("x-uec-data-product-version", "uec-public-data-product-v1")
        .header("x-uec-schema-version", "uec-location-projection-v1")
        .body(axum::body::Body::from(body))
        .unwrap()
        .into_response()
}

#[derive(Clone)]
pub struct ApiState {
    pub database: Option<Pool>,
    pub dev_preview_token: Option<String>,
    pub dev_test_release_id: Option<String>,
    pub dev_test_release_token: Option<String>,
}

#[derive(Deserialize)]
pub struct RealPreviewPageParams {
    pub cursor: Option<uuid::Uuid>,
    pub limit: Option<i64>,
    pub q: Option<String>,
}

#[derive(Deserialize)]
pub struct RealPreviewViewportParams {
    pub west: f64,
    pub south: f64,
    pub east: f64,
    pub north: f64,
    pub cursor: Option<uuid::Uuid>,
    pub limit: Option<i64>,
}

fn real_preview_response(status: StatusCode, body: Value) -> Response<axum::body::Body> {
    let mut response = (status, Json(body)).into_response();
    response.headers_mut().insert(
        axum::http::header::CACHE_CONTROL,
        HeaderValue::from_static("no-store"),
    );
    response
}

fn real_preview_error(
    status: StatusCode,
    code: &'static str,
    message: &'static str,
) -> Response<axum::body::Body> {
    real_preview_response(
        status,
        json!({"api_version":"real-preview-v1","error":{"code":code,"message":message}}),
    )
}

fn real_preview_authorized(
    state: &ApiState,
    headers: &HeaderMap,
) -> Result<(), Response<axum::body::Body>> {
    let Some(expected) = state.dev_preview_token.as_deref() else {
        return Err(real_preview_error(
            StatusCode::NOT_FOUND,
            "preview_unavailable",
            "private preview unavailable",
        ));
    };
    if expected.len() < 32 {
        return Err(real_preview_error(
            StatusCode::NOT_FOUND,
            "preview_unavailable",
            "private preview unavailable",
        ));
    }
    if !preview_request_is_local(headers) {
        return Err(real_preview_error(
            StatusCode::FORBIDDEN,
            "loopback_required",
            "private preview requires loopback host and origin",
        ));
    }
    let Some(provided) = headers
        .get(DEV_PREVIEW_TOKEN_HEADER)
        .and_then(|value| value.to_str().ok())
    else {
        return Err(real_preview_error(
            StatusCode::UNAUTHORIZED,
            "authentication_required",
            "private preview authentication required",
        ));
    };
    if !constant_time_token_matches(expected, provided) {
        return Err(real_preview_error(
            StatusCode::UNAUTHORIZED,
            "authentication_failed",
            "private preview authentication failed",
        ));
    }
    Ok(())
}

fn real_preview_unavailable() -> Response<axum::body::Body> {
    real_preview_error(
        StatusCode::SERVICE_UNAVAILABLE,
        "preview_unavailable",
        "private preview data unavailable",
    )
}

fn real_preview_candidate(row: &tokio_postgres::Row) -> Value {
    let kind: String = row.get("location_class");
    json!({
        "candidate_id": row.get::<_, uuid::Uuid>("candidate_id"),
        "source_id": row.get::<_, String>("source_id"),
        "location_class": kind,
        "display_precision": if kind == "numeric_source_coordinate" {
            match row.get::<_, Option<String>>("coordinate_precision").as_deref() {
                Some("numeric" | "exact" | "source_numeric" | "source_coordinates" | "facility_coordinate") => "source_numeric_pending_review",
                Some("source-provided") => "approximate_source_provided_pending_review",
                _ => "approximate_source_precision_unknown_pending_review",
            }
        } else { "city_postal_coarse" },
        "country_code": row.get::<_, Option<String>>("country_code"),
        "city": row.get::<_, Option<String>>("city"),
        "postal_code": row.get::<_, Option<String>>("postal_code"),
        "latitude": row.get::<_, Option<f64>>("latitude"),
        "longitude": row.get::<_, Option<f64>>("longitude"),
        "coordinate_precision": row.get::<_, Option<String>>("coordinate_precision"),
        "coordinate_review_status": if kind == "numeric_source_coordinate" { "pending_human_privacy_review" } else { "coarse_non_point" },
        "factual_review_status": "not_reviewed",
        "privacy_screening_status": "pending",
        "project_approval": false,
        "publication_status": "not_published",
        "preview_label": "Private real V2 candidate — not project-approved or published"
    })
}

pub async fn get_real_preview_list_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Query(params): Query<RealPreviewPageParams>,
) -> Response<axum::body::Body> {
    if let Err(response) = real_preview_authorized(&state, &headers) {
        return response;
    }
    let limit = params.limit.unwrap_or(100);
    if !(1..=200).contains(&limit) {
        return real_preview_error(
            StatusCode::BAD_REQUEST,
            "invalid_limit",
            "limit must be between 1 and 200",
        );
    }
    let Some(pool) = state.database else {
        return real_preview_unavailable();
    };
    let Ok(client) = pool.get().await else {
        return real_preview_unavailable();
    };
    let cursor = params.cursor;
    let query = params
        .q
        .unwrap_or_default()
        .trim()
        .chars()
        .take(100)
        .collect::<String>();
    let rows = match client.query(
        "SELECT candidate_id,source_id,location_class,country_code,city,postal_code,latitude,longitude,coordinate_precision FROM real_preview.candidates WHERE ($1::uuid IS NULL OR candidate_id > $1) AND ($2='' OR city ILIKE '%' || $2 || '%' OR postal_code ILIKE '%' || $2 || '%') ORDER BY candidate_id LIMIT $3",
        &[&cursor, &query, &limit],
    ).await { Ok(rows) => rows, Err(_) => return real_preview_unavailable() };
    let data: Vec<Value> = rows.iter().map(real_preview_candidate).collect();
    let next = rows
        .last()
        .map(|row| row.get::<_, uuid::Uuid>("candidate_id"));
    real_preview_response(
        StatusCode::OK,
        json!({"api_version":"real-preview-v1","data":data,"meta":{"bounded":true,"next_cursor":next,"private_preview":true}}),
    )
}

pub async fn get_real_preview_viewport_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Query(params): Query<RealPreviewViewportParams>,
) -> Response<axum::body::Body> {
    if let Err(response) = real_preview_authorized(&state, &headers) {
        return response;
    }
    let limit = params.limit.unwrap_or(300);
    if !(1..=500).contains(&limit)
        || ![params.west, params.south, params.east, params.north]
            .iter()
            .all(|v| v.is_finite())
        || params.west < -180.0
        || params.east > 180.0
        || params.south < -90.0
        || params.north > 90.0
        || params.west >= params.east
        || params.south >= params.north
    {
        return real_preview_error(
            StatusCode::BAD_REQUEST,
            "invalid_viewport",
            "viewport bounds or limit are invalid",
        );
    }
    let Some(pool) = state.database else {
        return real_preview_unavailable();
    };
    let Ok(client) = pool.get().await else {
        return real_preview_unavailable();
    };
    let rows = match client.query(
        "SELECT candidate_id,source_id,location_class,country_code,city,postal_code,latitude,longitude,coordinate_precision FROM real_preview.candidates WHERE location_class='numeric_source_coordinate' AND longitude BETWEEN $1 AND $3 AND latitude BETWEEN $2 AND $4 AND ($5::uuid IS NULL OR candidate_id > $5) ORDER BY candidate_id LIMIT $6",
        &[&params.west,&params.south,&params.east,&params.north,&params.cursor,&limit],
    ).await { Ok(rows) => rows, Err(_) => return real_preview_unavailable() };
    let data: Vec<Value> = rows.iter().map(real_preview_candidate).collect();
    let next = rows
        .last()
        .map(|row| row.get::<_, uuid::Uuid>("candidate_id"));
    real_preview_response(
        StatusCode::OK,
        json!({"api_version":"real-preview-v1","data":data,"meta":{"bounded":true,"next_cursor":next,"private_preview":true}}),
    )
}

pub async fn get_real_preview_detail_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Path(id): Path<uuid::Uuid>,
) -> Response<axum::body::Body> {
    if let Err(response) = real_preview_authorized(&state, &headers) {
        return response;
    }
    let Some(pool) = state.database else {
        return real_preview_unavailable();
    };
    let Ok(client) = pool.get().await else {
        return real_preview_unavailable();
    };
    let row = match client.query_opt("SELECT candidate_id,source_id,location_class,country_code,city,postal_code,latitude,longitude,coordinate_precision FROM real_preview.candidates WHERE candidate_id=$1", &[&id]).await { Ok(row) => row, Err(_) => return real_preview_unavailable() };
    match row {
        Some(row) => real_preview_response(
            StatusCode::OK,
            json!({"api_version":"real-preview-v1","data":real_preview_candidate(&row)}),
        ),
        None => real_preview_error(
            StatusCode::NOT_FOUND,
            "candidate_not_found",
            "candidate unavailable",
        ),
    }
}

pub async fn get_real_preview_facets_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
) -> Response<axum::body::Body> {
    if let Err(response) = real_preview_authorized(&state, &headers) {
        return response;
    }
    let Some(pool) = state.database else {
        return real_preview_unavailable();
    };
    let Ok(client) = pool.get().await else {
        return real_preview_unavailable();
    };
    let rows = match client.query("SELECT source_id,location_class,count(*)::bigint FROM real_preview.candidates GROUP BY source_id,location_class ORDER BY source_id,location_class", &[]).await { Ok(rows) => rows, Err(_) => return real_preview_unavailable() };
    let data: Vec<Value> = rows.iter().map(|row| json!({"source_id":row.get::<_,String>(0),"location_class":row.get::<_,String>(1),"count":row.get::<_,i64>(2)})).collect();
    real_preview_response(
        StatusCode::OK,
        json!({"api_version":"real-preview-v1","data":data,"meta":{"private_preview":true}}),
    )
}

pub async fn get_real_preview_counts_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
) -> Response<axum::body::Body> {
    if let Err(response) = real_preview_authorized(&state, &headers) {
        return response;
    }
    let Some(pool) = state.database else {
        return real_preview_unavailable();
    };
    let Ok(client) = pool.get().await else {
        return real_preview_unavailable();
    };
    let row = match client.query_one("SELECT count(*)::bigint,count(*) FILTER (WHERE location_class='numeric_source_coordinate')::bigint,count(*) FILTER (WHERE location_class='city_postal')::bigint FROM real_preview.candidates", &[]).await { Ok(row) => row, Err(_) => return real_preview_unavailable() };
    real_preview_response(
        StatusCode::OK,
        json!({"api_version":"real-preview-v1","data":{"facility_candidate_count":row.get::<_,i64>(0),"numeric_coordinate_count":row.get::<_,i64>(1),"city_postal_count":row.get::<_,i64>(2)},"meta":{"private_preview":true}}),
    )
}

const DEV_PREVIEW_TOKEN_HEADER: &str = "x-uec-dev-preview-token";

fn test_release_auth(headers: &HeaderMap, state: &ApiState) -> bool {
    let (Some(release_id), Some(expected)) =
        (&state.dev_test_release_id, &state.dev_test_release_token)
    else {
        return false;
    };
    preview_request_is_local(headers)
        && headers
            .get(DEV_PREVIEW_TOKEN_HEADER)
            .and_then(|v| v.to_str().ok())
            .is_some_and(|v| constant_time_token_matches(expected, v))
        && !release_id.is_empty()
}

fn test_release_meta(release_id: &str, profile: &str) -> serde_json::Value {
    json!({"api_version":"dev-test-v1","environment":"test-only","test_only":true,"private_preview":true,"release_status":"candidate","release_id":release_id,"profile":profile,"coverage_scope":"test_release_public_shaped_rows","count_semantics":"Rows are disposable candidate facilities, not project-approved or published counts.","preview_label":"Disposable test release — not project-approved or published"})
}

fn csv_safe_value(value: String) -> String {
    if value.starts_with(['=', '+', '-', '@']) {
        format!("'{}", value)
    } else {
        value
    }
}

pub async fn get_dev_test_release_locations_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Query(params): Query<V2LocationParams>,
) -> impl IntoResponse {
    if !test_release_auth(&headers, &state) {
        return v2_error(
            StatusCode::NOT_FOUND,
            "test_release_unavailable",
            "test release unavailable",
        );
    }
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_not_configured",
            "test release database unavailable",
        );
    };
    let profile = params.profile.as_deref().unwrap_or("official");
    let Some(release_id) = state.dev_test_release_id.as_deref() else {
        return v2_error(
            StatusCode::NOT_FOUND,
            "test_release_unavailable",
            "test release unavailable",
        );
    };
    let client = match pool.get().await {
        Ok(c) => c,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "database_pool_unavailable",
                "database pool unavailable",
            );
        }
    };
    let limit = params
        .limit
        .as_deref()
        .unwrap_or("100")
        .parse::<i64>()
        .ok()
        .filter(|v| (1..=1000).contains(v))
        .unwrap_or(0);
    if limit == 0 {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_limit",
            "limit must be between 1 and 1000",
        );
    }
    if params.cursor.is_some() && params.offset.is_some() {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "cursor_offset_conflict",
            "cursor and offset cannot be combined",
        );
    }
    let cursor = match params.cursor.as_deref() {
        Some(value) => match value.parse::<uuid::Uuid>() {
            Ok(value) => Some(value),
            Err(_) => {
                return v2_error(
                    StatusCode::BAD_REQUEST,
                    "invalid_cursor",
                    "cursor must be a facility UUID",
                );
            }
        },
        None => None,
    };
    let query_limit = limit + 1;
    let mut rows = match client.query(r#"SELECT f.facility_id,f.canonical_name,f.country_code,f.city,o.classification_category,
        CASE WHEN o.coordinate_review_status='approved' AND g.result IS NOT NULL THEN 'exact' ELSE 'unmapped' END,
        CASE WHEN o.coordinate_review_status='approved' AND g.result IS NOT NULL THEN ST_Y(g.result::geometry) ELSE NULL END,
        CASE WHEN o.coordinate_review_status='approved' AND g.result IS NOT NULL THEN ST_X(g.result::geometry) ELSE NULL END,
        review.factual_review_status,review.privacy_screening_status,review.maintainer_approval,review.reviewer_role,
        source.origin_type, source.source_id, source.name, source.official_url, r.ruleset_version, artifact.retrieved_at
        FROM uec.release_members member JOIN uec.releases r ON r.release_id=member.release_id
        JOIN uec.observations o ON o.observation_id=member.observation_id JOIN uec.facilities f ON f.facility_id=member.facility_id
        JOIN uec.source_records record ON record.source_record_id=o.source_record_id JOIN uec.sources source ON source.source_id=record.source_id
        JOIN uec.raw_artifacts artifact ON artifact.artifact_id=record.artifact_id
        LEFT JOIN uec.publication_review_release_current review ON review.source_record_id=o.source_record_id AND review.release_id=member.release_id
        LEFT JOIN LATERAL (SELECT result FROM uec.geocode_results WHERE source_record_id=o.source_record_id AND status='accepted' AND result IS NOT NULL ORDER BY queried_at DESC,geocode_result_id DESC LIMIT 1) g ON true
        WHERE r.release_id=$1 AND r.status='candidate' AND r.test_only=true AND record.source_state NOT IN ('rejected','superseded')
          AND COALESCE(review.privacy_screening_status,'pending') <> 'failed' AND COALESCE(review.factual_review_status,'unreviewed') <> 'rejected'
          AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted WHERE restricted.source_record_id=o.source_record_id)
          AND ($2::text IS NULL OR f.country_code=$2) AND ($3::text IS NULL OR o.classification_category=$3)
          AND ($4::uuid IS NULL OR f.facility_id > $4)
        ORDER BY f.facility_id LIMIT $5"#, &[&release_id,&params.country_code,&params.category,&cursor,&query_limit]).await {
        Ok(rows)=>rows, Err(_)=>return v2_error(StatusCode::SERVICE_UNAVAILABLE,"test_release_query_failed","test release unavailable")
    };
    let has_next = rows.len() > limit as usize;
    if has_next {
        rows.truncate(limit as usize);
    }
    let data = rows.into_iter().map(|row| json!({"facility_id":row.get::<_,uuid::Uuid>(0),"canonical_name":row.get::<_,Option<String>>(1),"country_code":row.get::<_,String>(2),"city":row.get::<_,Option<String>>(3),"category":row.get::<_,String>(4),"publication_profile":profile,"factual_review_status":row.get::<_,Option<String>>(8).unwrap_or("unreviewed".into()),"privacy_screening_status":row.get::<_,Option<String>>(9).unwrap_or("pending".into()),"project_approval":"not-approved","reviewer_role":row.get::<_,Option<String>>(11),"publication_warning":"Disposable test release — not project-approved or published","display_precision":row.get::<_,String>(5),"latitude":row.get::<_,Option<f64>>(6),"longitude":row.get::<_,Option<f64>>(7),"first_observed_at":null,"last_observed_at":null,"observation_count":null,"lifecycle_status":"status_unknown","source_type":row.get::<_,String>(12),"release_id":release_id,"release_ruleset_version":row.get::<_,String>(16),"provenance_source_id":row.get::<_,String>(13),"provenance_source_name":row.get::<_,String>(14),"provenance_source_url":row.get::<_,String>(15),"provenance_retrieved_at":row.get::<_,chrono::DateTime<chrono::Utc>>(17)})).collect::<Vec<_>>();
    let mut meta = test_release_meta(release_id, profile);
    meta["result_count"] = json!(data.len());
    meta["next_cursor"] = json!(if has_next {
        data.last().and_then(|row| row.get("facility_id")).cloned()
    } else {
        None::<serde_json::Value>
    });
    Json(json!({"data":data,"meta":meta})).into_response()
}

pub async fn get_dev_test_release_location_detail_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Path(facility_id): Path<uuid::Uuid>,
    Query(params): Query<ProfileParams>,
) -> impl IntoResponse {
    let profile = params.profile.as_deref().unwrap_or("official");
    if !test_release_auth(&headers, &state) {
        return v2_error(
            StatusCode::NOT_FOUND,
            "test_release_unavailable",
            "test release unavailable",
        );
    }
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_not_configured",
            "test release database unavailable",
        );
    };
    let Some(release_id) = state.dev_test_release_id.as_deref() else {
        return v2_error(
            StatusCode::NOT_FOUND,
            "test_release_unavailable",
            "test release unavailable",
        );
    };
    let client = match pool.get().await {
        Ok(c) => c,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "database_pool_unavailable",
                "database pool unavailable",
            );
        }
    };
    let row=match client.query_opt("SELECT f.facility_id,f.canonical_name,f.country_code,f.city,o.classification_category,COALESCE(review.factual_review_status,'unreviewed'),COALESCE(review.privacy_screening_status,'pending'),o.coordinate_review_status,source.origin_type,source.source_id,source.name,source.official_url,artifact.retrieved_at,r.ruleset_version,CASE WHEN o.coordinate_review_status='approved' AND g.result IS NOT NULL THEN 'exact' ELSE 'unmapped' END,CASE WHEN o.coordinate_review_status='approved' AND g.result IS NOT NULL THEN ST_Y(g.result::geometry) ELSE NULL END,CASE WHEN o.coordinate_review_status='approved' AND g.result IS NOT NULL THEN ST_X(g.result::geometry) ELSE NULL END FROM uec.release_members m JOIN uec.releases r ON r.release_id=m.release_id JOIN uec.observations o ON o.observation_id=m.observation_id JOIN uec.facilities f ON f.facility_id=m.facility_id JOIN uec.source_records sr ON sr.source_record_id=o.source_record_id JOIN uec.sources source ON source.source_id=sr.source_id JOIN uec.raw_artifacts artifact ON artifact.artifact_id=sr.artifact_id LEFT JOIN uec.publication_review_release_current review ON review.source_record_id=o.source_record_id AND review.release_id=m.release_id LEFT JOIN LATERAL (SELECT result FROM uec.geocode_results WHERE source_record_id=o.source_record_id AND status='accepted' AND result IS NOT NULL ORDER BY queried_at DESC LIMIT 1) g ON true WHERE r.release_id=$1 AND r.status='candidate' AND r.test_only=true AND f.facility_id=$2 AND sr.source_state NOT IN ('rejected','superseded') AND COALESCE(review.privacy_screening_status,'pending') <> 'failed' AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted x WHERE x.source_record_id=o.source_record_id)", &[&release_id,&facility_id]).await {Ok(r)=>r,Err(_)=>return v2_error(StatusCode::SERVICE_UNAVAILABLE,"test_release_query_failed","test release unavailable")};
    let Some(row) = row else {
        return v2_error(
            StatusCode::NOT_FOUND,
            "location_not_found",
            "test release location not found",
        );
    };
    let item = json!({"facility_id":row.get::<_,uuid::Uuid>(0),"canonical_name":row.get::<_,Option<String>>(1),"country_code":row.get::<_,String>(2),"city":row.get::<_,Option<String>>(3),"category":row.get::<_,String>(4),"publication_profile":profile,"factual_review_status":row.get::<_,String>(5),"privacy_screening_status":row.get::<_,String>(6),"project_approval":"not-approved","publication_warning":"Disposable test release — not project-approved or published","display_precision":row.get::<_,String>(14),"latitude":row.get::<_,Option<f64>>(15),"longitude":row.get::<_,Option<f64>>(16),"release_id":release_id,"release_ruleset_version":row.get::<_,String>(13),"provenance_source_id":row.get::<_,String>(9),"provenance_source_name":row.get::<_,String>(10),"provenance_source_url":row.get::<_,String>(11),"provenance_retrieved_at":row.get::<_,chrono::DateTime<chrono::Utc>>(12)});
    let mut meta = test_release_meta(release_id, profile);
    meta["result_count"] = json!(1);
    Json(json!({"data":item,"meta":meta})).into_response()
}

pub async fn get_dev_test_release_facets_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Query(params): Query<V2LocationParams>,
) -> impl IntoResponse {
    if !test_release_auth(&headers, &state) {
        return v2_error(
            StatusCode::NOT_FOUND,
            "test_release_unavailable",
            "test release unavailable",
        );
    }
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_not_configured",
            "test release database unavailable",
        );
    };
    let Some(release_id) = state.dev_test_release_id.as_deref() else {
        return v2_error(
            StatusCode::NOT_FOUND,
            "test_release_unavailable",
            "test release unavailable",
        );
    };
    let client = match pool.get().await {
        Ok(c) => c,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "database_pool_unavailable",
                "database pool unavailable",
            );
        }
    };
    let rows=match client.query("SELECT f.country_code,o.classification_category,CASE WHEN o.coordinate_review_status='approved' AND g.result IS NOT NULL THEN 'exact' ELSE 'unmapped' END,source.origin_type FROM uec.release_members m JOIN uec.releases r ON r.release_id=m.release_id JOIN uec.observations o ON o.observation_id=m.observation_id JOIN uec.facilities f ON f.facility_id=m.facility_id JOIN uec.source_records sr ON sr.source_record_id=o.source_record_id JOIN uec.sources source ON source.source_id=sr.source_id LEFT JOIN LATERAL (SELECT result FROM uec.geocode_results WHERE source_record_id=o.source_record_id AND status='accepted' AND result IS NOT NULL ORDER BY queried_at DESC LIMIT 1) g ON true LEFT JOIN uec.publication_review_release_current review ON review.source_record_id=o.source_record_id AND review.release_id=m.release_id WHERE r.release_id=$1 AND r.status='candidate' AND r.test_only=true AND sr.source_state NOT IN ('rejected','superseded') AND COALESCE(review.privacy_screening_status,'pending')<>'failed' AND COALESCE(review.factual_review_status,'unreviewed')<>'rejected' AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted x WHERE x.source_record_id=o.source_record_id)", &[&release_id]).await {Ok(r)=>r,Err(_)=>return v2_error(StatusCode::SERVICE_UNAVAILABLE,"test_release_query_failed","test release unavailable")};
    let mut dims = serde_json::Map::new();
    for (name, values) in [
        (
            "country_code",
            rows.iter()
                .map(|r| r.get::<_, String>(0))
                .collect::<Vec<_>>(),
        ),
        (
            "category",
            rows.iter().map(|r| r.get::<_, String>(1)).collect(),
        ),
        (
            "display_precision",
            rows.iter().map(|r| r.get::<_, String>(2)).collect(),
        ),
        (
            "source_type",
            rows.iter().map(|r| r.get::<_, String>(3)).collect(),
        ),
    ] {
        let mut counts = std::collections::BTreeMap::new();
        for v in values {
            *counts.entry(v).or_insert(0usize) += 1;
        }
        dims.insert(
            name.into(),
            json!(
                counts
                    .into_iter()
                    .map(|(value, count)| json!({"value":value,"count":count}))
                    .collect::<Vec<_>>()
            ),
        );
    }
    let mut meta = test_release_meta(release_id, params.profile.as_deref().unwrap_or("official"));
    meta["result_count"] = json!(rows.len());
    Json(json!({"data":null,"meta":meta,"dimensions":dims})).into_response()
}

pub async fn get_dev_test_release_export_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Query(params): Query<ProfileParams>,
) -> impl IntoResponse {
    if !test_release_auth(&headers, &state) {
        return v2_error(
            StatusCode::NOT_FOUND,
            "test_release_unavailable",
            "test release unavailable",
        );
    }
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_not_configured",
            "test release database unavailable",
        );
    };
    let Some(release_id) = state.dev_test_release_id.as_deref() else {
        return v2_error(
            StatusCode::NOT_FOUND,
            "test_release_unavailable",
            "test release unavailable",
        );
    };
    let profile = params.profile.as_deref().unwrap_or("official");
    let client = match pool.get().await {
        Ok(c) => c,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "database_pool_unavailable",
                "test release database unavailable",
            );
        }
    };
    let rows=match client.query("SELECT f.facility_id,f.canonical_name,f.country_code,f.city,o.classification_category,source.origin_type,source.source_id,source.name,source.official_url,artifact.retrieved_at FROM uec.release_members m JOIN uec.releases r ON r.release_id=m.release_id JOIN uec.observations o ON o.observation_id=m.observation_id JOIN uec.facilities f ON f.facility_id=m.facility_id JOIN uec.source_records sr ON sr.source_record_id=o.source_record_id JOIN uec.sources source ON source.source_id=sr.source_id JOIN uec.raw_artifacts artifact ON artifact.artifact_id=sr.artifact_id LEFT JOIN uec.publication_review_release_current review ON review.source_record_id=o.source_record_id AND review.release_id=m.release_id WHERE r.release_id=$1 AND r.status='candidate' AND r.test_only=true AND sr.source_state NOT IN ('rejected','superseded') AND COALESCE(review.privacy_screening_status,'pending')<>'failed' AND COALESCE(review.factual_review_status,'unreviewed')<>'rejected' AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted x WHERE x.source_record_id=o.source_record_id) ORDER BY f.facility_id LIMIT 1001", &[&release_id]).await {Ok(r)=>r,Err(_)=>return v2_error(StatusCode::SERVICE_UNAVAILABLE,"test_release_query_failed","test release unavailable")};
    if rows.len() > 1000 {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "export_too_large",
            "test export exceeds bounded limit",
        );
    }
    let mut writer = csv::Writer::from_writer(Vec::new());
    let _ = writer.write_record([
        "facility_id",
        "canonical_name",
        "country_code",
        "city",
        "category",
        "source_type",
        "provenance_source_id",
        "provenance_source_name",
        "provenance_source_url",
        "provenance_retrieved_at",
        "test_only",
        "environment",
        "release_status",
        "project_approval",
    ]);
    for row in rows {
        let _ = writer.write_record([
            row.get::<_, uuid::Uuid>(0).to_string(),
            csv_safe_value(row.get::<_, Option<String>>(1).unwrap_or_default()),
            csv_safe_value(row.get::<_, String>(2)),
            csv_safe_value(row.get::<_, Option<String>>(3).unwrap_or_default()),
            csv_safe_value(row.get::<_, String>(4)),
            csv_safe_value(row.get::<_, String>(5)),
            csv_safe_value(row.get::<_, String>(6)),
            csv_safe_value(row.get::<_, String>(7)),
            csv_safe_value(row.get::<_, String>(8)),
            csv_safe_value(row.get::<_, chrono::DateTime<chrono::Utc>>(9).to_rfc3339()),
            "true".into(),
            "test-only".into(),
            "candidate".into(),
            "not-approved".into(),
        ]);
    }
    let body = match writer.into_inner() {
        Ok(v) => v,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "export_encoding_failed",
                "test export unavailable",
            );
        }
    };
    Response::builder()
        .status(StatusCode::OK)
        .header("content-type", "text/csv; charset=utf-8")
        .header(
            "content-disposition",
            format!("attachment; filename=uec-test-only-{profile}-locations.csv"),
        )
        .header("x-uec-test-release", "true")
        .header("x-uec-release-id", release_id)
        .body(axum::body::Body::from(body))
        .unwrap()
        .into_response()
}

pub(crate) fn constant_time_token_matches(expected: &str, provided: &str) -> bool {
    let mut difference = expected.len() ^ provided.len();
    for (left, right) in expected.bytes().zip(provided.bytes()) {
        difference |= usize::from(left ^ right);
    }
    difference == 0
}

fn is_loopback_host(value: &str) -> bool {
    let Ok(uri) = format!("http://{value}").parse::<axum::http::Uri>() else {
        return false;
    };
    let Some(host) = uri.host() else { return false };
    host == "localhost"
        || host
            .parse::<std::net::IpAddr>()
            .is_ok_and(|ip| ip.is_loopback())
}

fn preview_request_is_local(headers: &HeaderMap) -> bool {
    let Some(host) = headers
        .get(axum::http::header::HOST)
        .and_then(|value| value.to_str().ok())
    else {
        return false;
    };
    if !is_loopback_host(host) {
        return false;
    }
    headers
        .get(axum::http::header::ORIGIN)
        .map(|origin| {
            origin
                .to_str()
                .ok()
                .and_then(|value| value.parse::<axum::http::Uri>().ok())
                .and_then(|uri| uri.host().map(str::to_owned))
                .is_some_and(|host| is_loopback_host(&host))
        })
        .unwrap_or(true)
}

#[derive(Deserialize)]
pub struct DevPreviewParams {
    pub limit: Option<String>,
}

/// Candidate preview is deliberately separate from `/api/v2`: it is a local
/// operator tool, not a release/profile or project-approval mechanism.
pub async fn get_dev_candidate_preview_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Query(params): Query<DevPreviewParams>,
) -> impl IntoResponse {
    let Some(expected_token) = state.dev_preview_token.as_deref() else {
        return v2_error(
            StatusCode::NOT_FOUND,
            "dev_preview_unavailable",
            "candidate preview unavailable",
        );
    };
    if !preview_request_is_local(&headers) {
        return v2_error(
            StatusCode::FORBIDDEN,
            "dev_preview_origin_rejected",
            "candidate preview requires loopback host and origin",
        );
    }
    let Some(provided_token) = headers
        .get(DEV_PREVIEW_TOKEN_HEADER)
        .and_then(|value| value.to_str().ok())
    else {
        return v2_error(
            StatusCode::UNAUTHORIZED,
            "dev_preview_auth_required",
            "candidate preview requires operator authentication",
        );
    };
    if !constant_time_token_matches(expected_token, provided_token) {
        return v2_error(
            StatusCode::UNAUTHORIZED,
            "dev_preview_auth_failed",
            "candidate preview authentication failed",
        );
    }
    let limit = match params.limit.as_deref().unwrap_or("100").parse::<i64>() {
        Ok(value) if (1..=1000).contains(&value) => value,
        _ => {
            return v2_error(
                StatusCode::BAD_REQUEST,
                "invalid_limit",
                "limit must be between 1 and 1000",
            );
        }
    };
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_not_configured",
            "candidate preview database is not configured",
        );
    };
    let client = match pool.get().await {
        Ok(client) => client,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "database_pool_unavailable",
                "candidate preview database unavailable",
            );
        }
    };
    let rows = match client.query(r#"
        SELECT r.release_id, r.status, o.source_record_id, o.facility_id,
               f.canonical_name, f.country_code, f.city, o.classification_category,
               o.coordinate_precision, o.coordinate_review_status,
               ST_Y(g.result::geometry), ST_X(g.result::geometry),
               source.origin_type, source.source_id, source.name, source.official_url,
               artifact.retrieved_at, review.factual_review_status,
               review.privacy_screening_status, review.maintainer_approval
        FROM uec.release_members member
        JOIN uec.releases r ON r.release_id = member.release_id
        JOIN uec.observations o ON o.observation_id = member.observation_id
        JOIN uec.facilities f ON f.facility_id = member.facility_id
        JOIN uec.source_records record ON record.source_record_id = o.source_record_id
        JOIN uec.sources source ON source.source_id = record.source_id
        JOIN uec.raw_artifacts artifact ON artifact.artifact_id = record.artifact_id
        JOIN uec.publication_review_release_current review
          ON review.source_record_id = o.source_record_id AND review.release_id = member.release_id
        JOIN LATERAL (
            SELECT result FROM uec.geocode_results
            WHERE source_record_id = o.source_record_id AND status = 'accepted' AND result IS NOT NULL
            ORDER BY queried_at DESC, geocode_result_id DESC LIMIT 1
        ) g ON true
        WHERE r.status = 'candidate'
          AND member.default_visible = true
          AND record.source_state NOT IN ('rejected', 'superseded')
          AND review.privacy_screening_status = 'passed'
          AND review.factual_review_status <> 'rejected'
          -- An accepted geocoder result is not itself permission to expose a
          -- precise point; candidate preview requires explicit coordinate review.
          AND o.coordinate_review_status = 'approved'
          AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted WHERE restricted.source_record_id = o.source_record_id)
        ORDER BY r.release_id, o.facility_id
        LIMIT $1
    "#, &[&limit]).await {
        Ok(rows) => rows,
        Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "dev_preview_query_failed", "candidate preview unavailable"),
    };
    let data = rows
        .into_iter()
        .map(|row| {
            json!({
                "candidate_id": row.get::<_, uuid::Uuid>(2),
                "source_record_id": row.get::<_, uuid::Uuid>(2),
                "facility_id": row.get::<_, uuid::Uuid>(3),
                "canonical_name": row.get::<_, Option<String>>(4),
                "country_code": row.get::<_, String>(5),
                "city": row.get::<_, Option<String>>(6),
                "category": row.get::<_, String>(7),
                "display_precision": "exact",
                "latitude": row.get::<_, Option<f64>>(10),
                "longitude": row.get::<_, Option<f64>>(11),
                "coordinate_precision": row.get::<_, Option<String>>(8),
                "coordinate_review_status": row.get::<_, Option<String>>(9),
                "source_type": row.get::<_, String>(12),
                "provenance_source_id": row.get::<_, String>(13),
                "provenance_source_name": row.get::<_, String>(14),
                "provenance_source_url": row.get::<_, String>(15),
                "provenance_retrieved_at": row.get::<_, chrono::DateTime<chrono::Utc>>(16),
                "factual_review_status": row.get::<_, String>(17),
                "privacy_screening_status": row.get::<_, String>(18),
                "project_approval": false,
                "maintainer_approval": row.get::<_, String>(19),
                "suppression_state": "not_currently_restricted",
                "release_id": row.get::<_, String>(0),
                "release_status": row.get::<_, String>(1),
                "preview_label": "Private development candidate — not project-approved or published"
            })
        })
        .collect::<Vec<_>>();
    Json(json!({"api_version":"dev-preview-v1", "data":data, "meta":{"test_only":true,"private_preview":true,"profile":null,"coverage_scope":"candidate_release_only","next_cursor":null}})).into_response()
}

mod location;
use crate::location::*;

pub use location::Location;

const DATA_DIR: Dir = include_dir!("./static_data");

static CACHED_LOCATIONS: Lazy<Result<Vec<LocationResponse>, String>> =
    Lazy::new(|| parse_all_locations().map_err(|e| e.to_string()));

static CACHED_APHIS: Lazy<Result<Vec<AphisReport>, String>> =
    Lazy::new(|| parse_aphis_reports().map_err(|e| e.to_string()));

static CACHED_INSPECTION: Lazy<Result<Vec<InspectionReport>, String>> =
    Lazy::new(|| parse_inspection_reports().map_err(|e| e.to_string()));

pub async fn get_locations_handler(Query(params): Query<LocationParams>) -> impl IntoResponse {
    match CACHED_LOCATIONS.as_ref() {
        Ok(all_locations) => {
            let filtered = if let Some(country) = params.country_code {
                all_locations
                    .iter()
                    .filter(|loc| loc.country == country)
                    .cloned()
                    .collect()
            } else {
                all_locations.clone()
            };
            Json(filtered).into_response()
        }
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Failed to read location data: {}", e),
        )
            .into_response(),
    }
}

const V2_CATEGORIES: &[&str] = &[
    "slaughter",
    "fish_processing",
    "logistics_and_storage",
    "retail_and_prepared_food",
];
const V2_COUNTRIES: &[&str] = &["DK"];
const V2_SOURCE_TYPES: &[&str] = &["official", "secondary", "user_submitted"];
const V2_PROFILES: &[&str] = &["official", "secondary", "community"];
const V2_PRECISIONS: &[&str] = &["exact", "city", "unmapped"];
const V2_LIFECYCLES: &[&str] = &[
    "active_observed",
    "explicitly_closed",
    "not_seen_recently",
    "status_unknown",
];

pub async fn get_v2_filter_metadata_handler() -> impl IntoResponse {
    Json(json!({"api_version":"v2", "contract_version":"v1", "dimensions": {
        "country_code":{"values":V2_COUNTRIES}, "region":{"values":[],"source":"release_facets"}, "category":{"values":V2_CATEGORIES},
        "source_type":{"values":V2_SOURCE_TYPES}, "profile":{"values":V2_PROFILES,"default":"official"},
        "display_precision":{"values":V2_PRECISIONS}, "lifecycle_status":{"values":V2_LIFECYCLES}
    }, "spatial":{"bbox":["min_lon","min_lat","max_lon","max_lat"],"radius":["latitude","longitude","radius_km"]}, "search":{"parameter":"q","fields":["canonical_name","city","country_code","category","source_name"]}, "pagination":{"limit_max":1000,"cursor":"facility_id"}, "privacy":"Filters operate only on eligible records in the selected promoted release; filters never override suppression or publication review."})).into_response()
}

pub async fn get_v2_facets_handler(
    State(state): State<ApiState>,
    Query(params): Query<V2LocationParams>,
) -> impl IntoResponse {
    let profile = params.profile.as_deref().unwrap_or("official");
    if !V2_PROFILES.contains(&profile) {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_profile",
            "profile is unsupported",
        );
    }
    if params
        .category
        .as_deref()
        .is_some_and(|v| !V2_CATEGORIES.contains(&v))
        || params
            .source_type
            .as_deref()
            .is_some_and(|v| !V2_SOURCE_TYPES.contains(&v))
        || params
            .display_precision
            .as_deref()
            .is_some_and(|v| !V2_PRECISIONS.contains(&v))
        || params
            .lifecycle_status
            .as_deref()
            .is_some_and(|v| !V2_LIFECYCLES.contains(&v))
        || params
            .country_code
            .as_deref()
            .is_some_and(|v| v.len() != 2 || !v.chars().all(|c| c.is_ascii_uppercase()))
        || params
            .region
            .as_deref()
            .is_some_and(|v| v.trim().is_empty() || v.len() > 120)
    {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_filter",
            "filter is invalid",
        );
    }
    let Some(pool) = state.database else {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_not_configured",
            "V2 database is not configured",
        );
    };
    let mut client = match pool.get().await {
        Ok(c) => c,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "database_pool_unavailable",
                "database pool unavailable",
            );
        }
    };
    let transaction = match client
        .build_transaction()
        .isolation_level(tokio_postgres::IsolationLevel::RepeatableRead)
        .read_only(true)
        .start()
        .await
    {
        Ok(transaction) => transaction,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "database_transaction_unavailable",
                "V2 database transaction unavailable",
            );
        }
    };
    let release = match transaction.query_opt("SELECT r.release_id, r.ruleset_version, r.created_at, (model.release_id IS NOT NULL AND manifest.release_id IS NOT NULL) FROM uec.releases r LEFT JOIN uec.public_discovery_read_models model ON model.release_id=r.release_id LEFT JOIN uec.release_manifests manifest ON manifest.release_id=r.release_id AND manifest.manifest_sha256=model.manifest_sha256 WHERE r.status='promoted' AND r.test_only IS NOT TRUE AND r.profile=$1 ORDER BY r.created_at DESC, r.release_id DESC LIMIT 1", &[&profile]).await { Ok(row) => row, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "release_query_failed", "release query failed") };
    let Some(release) = release else {
        return v2_error(
            StatusCode::NOT_FOUND,
            "release_not_found",
            "no promoted eligible release",
        );
    };
    let release_id: String = release.get(0);
    let ruleset_version: String = release.get(1);
    let release_created_at: chrono::DateTime<chrono::Utc> = release.get(2);
    if !release.get::<_, bool>(3) {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "read_model_unavailable",
            "public discovery read model is missing or stale",
        );
    }
    let rows = match transaction.query("SELECT country_code, classification_category, display_precision, lifecycle_status, provenance_origin_type, city, count(*)::bigint FROM (SELECT DISTINCT ON (facility_id) facility_id, country_code, classification_category, display_precision, lifecycle_status, provenance_origin_type, city FROM uec.map_facilities_public_discovery_read_model WHERE release_id=$1 AND ($2::text IS NULL OR country_code=$2) AND ($3::text IS NULL OR classification_category=$3) AND ($4::text IS NULL OR provenance_origin_type=$4) AND ($5::text IS NULL OR display_precision=$5) AND ($6::text IS NULL OR lifecycle_status=$6) AND ($7::text IS NULL OR city=$7) ORDER BY facility_id, observation_id) public_facilities GROUP BY country_code, classification_category, display_precision, lifecycle_status, provenance_origin_type, city", &[&release_id, &params.country_code, &params.category, &params.source_type, &params.display_precision, &params.lifecycle_status, &params.region]).await { Ok(rows) => rows, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "facets_query_failed", "public facets unavailable") };
    let mut dimensions = serde_json::Map::new();
    for (name, column) in [
        ("country_code", 0),
        ("category", 1),
        ("display_precision", 2),
        ("lifecycle_status", 3),
        ("source_type", 4),
        ("region", 5),
    ] {
        let mut counts = std::collections::BTreeMap::<String, usize>::new();
        for row in &rows {
            let value = if column == 5 {
                row.get::<_, Option<String>>(column)
            } else {
                Some(row.get::<_, String>(column))
            };
            if let Some(value) = value {
                *counts.entry(value).or_default() += row.get::<_, i64>(6) as usize;
            }
        }
        dimensions.insert(
            name.into(),
            json!(
                counts
                    .into_iter()
                    .take(20)
                    .map(|(value, count)| json!({"value":value,"count":count}))
                    .collect::<Vec<_>>()
            ),
        );
    }
    if transaction.commit().await.is_err() {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "database_transaction_failed",
            "V2 database transaction failed",
        );
    }
    Json(json!({"api_version":"v2", "meta":{"profile":profile,"release_id":release_id,"ruleset_version":ruleset_version,"release_created_at":release_created_at,"coverage_scope":"selected_promoted_release_public_facilities","count_semantics":"Counts are eligible public facility projection rows after current suppression; they are not story-wide or animal counts.","filters":{"country_code":params.country_code,"region":params.region,"category":params.category,"source_type":params.source_type,"display_precision":params.display_precision,"lifecycle_status":params.lifecycle_status}}, "dimensions":dimensions})).into_response()
}

#[derive(Deserialize)]
pub struct V2LocationParams {
    pub country_code: Option<String>,
    pub region: Option<String>,
    pub category: Option<String>,
    pub source_type: Option<String>,
    pub profile: Option<String>,
    pub display_precision: Option<String>,
    pub lifecycle_status: Option<String>,
    pub q: Option<String>,
    pub min_lon: Option<String>,
    pub min_lat: Option<String>,
    pub max_lon: Option<String>,
    pub max_lat: Option<String>,
    pub radius_km: Option<String>,
    pub latitude: Option<String>,
    pub longitude: Option<String>,
    pub limit: Option<String>,
    pub offset: Option<String>,
    pub cursor: Option<String>,
}

#[derive(Serialize)]
pub struct V2Location {
    pub facility_id: uuid::Uuid,
    pub canonical_name: Option<String>,
    pub country_code: String,
    pub city: Option<String>,
    pub category: String,
    pub publication_profile: String,
    pub factual_review_status: String,
    pub privacy_screening_status: String,
    pub project_approval: String,
    pub reviewer_role: Option<String>,
    pub publication_warning: Option<String>,
    pub display_precision: String,
    pub latitude: Option<f64>,
    pub longitude: Option<f64>,
    pub first_observed_at: Option<chrono::DateTime<chrono::Utc>>,
    pub last_observed_at: Option<chrono::DateTime<chrono::Utc>>,
    pub observation_count: Option<i32>,
    pub lifecycle_status: String,
    pub source_type: String,
    pub source_rights_status: String,
    pub provenance_source: Option<String>,
    pub release_id: String,
    pub release_ruleset_version: String,
    pub provenance_source_id: String,
    pub provenance_source_name: String,
    pub provenance_source_url: String,
    pub provenance_retrieved_at: chrono::DateTime<chrono::Utc>,
}

pub async fn get_v2_locations_handler(
    State(state): State<ApiState>,
    Query(params): Query<V2LocationParams>,
) -> impl IntoResponse {
    if params
        .profile
        .as_deref()
        .is_some_and(|v| !V2_PROFILES.contains(&v))
    {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_profile",
            "profile is unsupported",
        );
    }
    if params
        .display_precision
        .as_deref()
        .is_some_and(|v| !V2_PRECISIONS.contains(&v))
    {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_display_precision",
            "display_precision is unsupported",
        );
    }
    if params
        .lifecycle_status
        .as_deref()
        .is_some_and(|v| !V2_LIFECYCLES.contains(&v))
    {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_lifecycle_status",
            "lifecycle_status is unsupported",
        );
    }
    if params
        .category
        .as_deref()
        .is_some_and(|v| !V2_CATEGORIES.contains(&v))
        || params
            .country_code
            .as_deref()
            .is_some_and(|v| v.len() != 2 || !v.chars().all(|c| c.is_ascii_uppercase()))
    {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_filter",
            "filter is invalid",
        );
    }
    if params
        .source_type
        .as_deref()
        .is_some_and(|v| !V2_SOURCE_TYPES.contains(&v))
    {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_source_type",
            "source_type is unsupported",
        );
    }
    if params
        .region
        .as_deref()
        .is_some_and(|v| v.trim().is_empty() || v.len() > 120)
        || params
            .q
            .as_deref()
            .is_some_and(|v| v.trim().is_empty() || v.len() > 120)
    {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_filter",
            "region and q must be non-empty and at most 120 characters",
        );
    }
    let search_text = params.q.as_deref().map(|value| {
        value
            .trim()
            .replace('\\', "\\\\")
            .replace('%', "\\%")
            .replace('_', "\\_")
    });
    let parse_coordinate = |value: &Option<String>, name: &'static str, min: f64, max: f64| {
        value
            .as_deref()
            .map(str::parse::<f64>)
            .transpose()
            .map_err(|_| (name, "must be a number"))
            .and_then(|value| {
                if value.is_some_and(|number| !number.is_finite() || number < min || number > max) {
                    Err((name, "is outside the supported range"))
                } else {
                    Ok(value)
                }
            })
    };
    let min_lon = match parse_coordinate(&params.min_lon, "min_lon", -180.0, 180.0) {
        Ok(v) => v,
        Err((_, message)) => {
            return v2_error(StatusCode::BAD_REQUEST, "invalid_spatial_query", message);
        }
    };
    let min_lat = match parse_coordinate(&params.min_lat, "min_lat", -90.0, 90.0) {
        Ok(v) => v,
        Err((_, message)) => {
            return v2_error(StatusCode::BAD_REQUEST, "invalid_spatial_query", message);
        }
    };
    let max_lon = match parse_coordinate(&params.max_lon, "max_lon", -180.0, 180.0) {
        Ok(v) => v,
        Err((_, message)) => {
            return v2_error(StatusCode::BAD_REQUEST, "invalid_spatial_query", message);
        }
    };
    let max_lat = match parse_coordinate(&params.max_lat, "max_lat", -90.0, 90.0) {
        Ok(v) => v,
        Err((_, message)) => {
            return v2_error(StatusCode::BAD_REQUEST, "invalid_spatial_query", message);
        }
    };
    let radius_km = match parse_coordinate(&params.radius_km, "radius_km", 0.001, 5000.0) {
        Ok(v) => v,
        Err((_, message)) => {
            return v2_error(StatusCode::BAD_REQUEST, "invalid_spatial_query", message);
        }
    };
    let latitude = match parse_coordinate(&params.latitude, "latitude", -90.0, 90.0) {
        Ok(v) => v,
        Err((_, message)) => {
            return v2_error(StatusCode::BAD_REQUEST, "invalid_spatial_query", message);
        }
    };
    let longitude = match parse_coordinate(&params.longitude, "longitude", -180.0, 180.0) {
        Ok(v) => v,
        Err((_, message)) => {
            return v2_error(StatusCode::BAD_REQUEST, "invalid_spatial_query", message);
        }
    };
    let bbox_values = [min_lon, min_lat, max_lon, max_lat];
    let bbox_present = bbox_values.iter().any(Option::is_some);
    if bbox_present && bbox_values.iter().any(Option::is_none) {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_spatial_query",
            "bounding box requires min_lon, min_lat, max_lon, and max_lat",
        );
    }
    if bbox_present && !(min_lon.unwrap() < max_lon.unwrap() && min_lat.unwrap() < max_lat.unwrap())
    {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_spatial_query",
            "bounding box minimums must be less than maximums",
        );
    }
    let radius_present = radius_km.is_some() || latitude.is_some() || longitude.is_some();
    if radius_present && (radius_km.is_none() || latitude.is_none() || longitude.is_none()) {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_spatial_query",
            "radius queries require radius_km, latitude, and longitude",
        );
    }
    if bbox_present && radius_present {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_spatial_query",
            "bounding box and radius cannot be combined",
        );
    }
    if params
        .profile
        .as_deref()
        .is_some_and(|v| !V2_PROFILES.contains(&v))
    {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_profile",
            "profile is unsupported",
        );
    }
    let limit = match params.limit.as_deref().map(str::parse::<i64>).transpose() {
        Ok(value) => value.unwrap_or(100).clamp(1, 1000),
        Err(_) => {
            return v2_error(
                StatusCode::BAD_REQUEST,
                "invalid_limit",
                "limit must be an integer",
            );
        }
    };
    let offset = match params.offset.as_deref().map(str::parse::<i64>).transpose() {
        Ok(value) => value.unwrap_or(0).clamp(0, 1_000_000),
        Err(_) => {
            return v2_error(
                StatusCode::BAD_REQUEST,
                "invalid_offset",
                "offset must be an integer",
            );
        }
    };
    if params.cursor.is_some() && params.offset.is_some() {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_pagination",
            "cursor and offset cannot be combined",
        );
    }
    let cursor = match params
        .cursor
        .as_deref()
        .map(uuid::Uuid::parse_str)
        .transpose()
    {
        Ok(cursor) => cursor,
        Err(_) => {
            return v2_error(
                StatusCode::BAD_REQUEST,
                "invalid_cursor",
                "cursor must be a facility UUID",
            );
        }
    };
    let effective_offset = if cursor.is_some() { 0 } else { offset };
    let mut client = match state.database.as_ref() {
        Some(pool) => match pool.get().await {
            Ok(client) => client,
            Err(_) => {
                return v2_error(
                    StatusCode::SERVICE_UNAVAILABLE,
                    "database_pool_unavailable",
                    "database pool unavailable",
                );
            }
        },
        None => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "database_not_configured",
                "V2 database is not configured",
            );
        }
    };
    let transaction = match client
        .build_transaction()
        .isolation_level(tokio_postgres::IsolationLevel::RepeatableRead)
        .read_only(true)
        .start()
        .await
    {
        Ok(transaction) => transaction,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "database_transaction_unavailable",
                "V2 database transaction unavailable",
            );
        }
    };
    let requested_profile = params.profile.as_deref().unwrap_or("official");
    let release = transaction.query_opt("SELECT r.release_id, r.ruleset_version, r.created_at, r.profile, (model.release_id IS NOT NULL AND manifest.release_id IS NOT NULL) FROM uec.releases r LEFT JOIN uec.public_discovery_read_models model ON model.release_id=r.release_id LEFT JOIN uec.release_manifests manifest ON manifest.release_id=r.release_id AND manifest.manifest_sha256=model.manifest_sha256 WHERE r.status = 'promoted' AND r.test_only IS NOT TRUE AND r.profile = $1 ORDER BY r.created_at DESC, r.release_id DESC LIMIT 1", &[&requested_profile]).await;
    let release = match release {
        Ok(release) => release,
        Err(_) => {
            return v2_error(
                StatusCode::INTERNAL_SERVER_ERROR,
                "release_query_failed",
                "V2 release query failed",
            );
        }
    };
    let Some(release) = release else {
        let _ = transaction.commit().await;
        return Json(serde_json::json!({"data": [], "api_version": "v2", "meta": {"release_id": null, "profile": requested_profile, "coverage_note": "No promoted release is currently available."}})).into_response();
    };
    let promoted_release_id: String = release.get(0);
    let promoted_ruleset: String = release.get(1);
    let promoted_created_at: chrono::DateTime<chrono::Utc> = release.get(2);
    let promoted_profile: String = release.get(3);
    if !release.get::<_, bool>(4) {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "read_model_unavailable",
            "public discovery read model is missing or stale",
        );
    }
    let query_limit = limit + 1;
    let rows = match transaction.query(r#"
        SELECT DISTINCT ON (history.facility_id) history.facility_id, history.canonical_name, history.country_code, history.city, history.classification_category, history.display_precision,
               history.factual_review_status, history.privacy_screening_status, history.maintainer_approval, history.reviewer_role,
               ST_Y(history.display_location::geometry), ST_X(history.display_location::geometry),
               history.first_observed_at, history.last_observed_at, history.observation_count, history.lifecycle_status,
               history.provenance_origin_type, history.release_id, history.release_ruleset_version,
               history.provenance_source_id, history.provenance_source_name, history.provenance_source_url, history.provenance_retrieved_at,
               history.source_rights_status
        FROM uec.map_facilities_public_discovery_read_model AS history
        WHERE history.release_id = $1
          AND ($2::uuid IS NULL OR history.facility_id > $2)
          AND ($3::text IS NULL OR history.country_code = $3)
          AND ($4::text IS NULL OR history.city = $4)
          AND ($5::text IS NULL OR history.classification_category = $5)
          AND ($6::text IS NULL OR history.display_precision = $6)
          AND ($7::text IS NULL OR history.lifecycle_status = $7)
          AND ($8::text IS NULL OR history.provenance_origin_type = $8)
          AND ($9::text IS NULL OR lower(coalesce(history.canonical_name, '') || ' ' || coalesce(history.city, '') || ' ' || history.country_code || ' ' || history.classification_category || ' ' || coalesce(history.provenance_source_name, '')) LIKE '%' || lower($9) || '%' ESCAPE '\')
          AND ($10::double precision IS NULL OR (history.display_location && ST_MakeEnvelope($10, $11, $12, $13, 4326)::geography AND ST_Intersects(history.display_location::geometry, ST_MakeEnvelope($10, $11, $12, $13, 4326))))
          AND ($14::double precision IS NULL OR ST_DWithin(history.display_location, ST_SetSRID(ST_Point($15, $16), 4326)::geography, $14 * 1000))
        ORDER BY history.facility_id, history.observation_id LIMIT $17 OFFSET $18
    "#, &[&promoted_release_id, &cursor, &params.country_code, &params.region, &params.category, &params.display_precision, &params.lifecycle_status, &params.source_type, &search_text, &min_lon, &min_lat, &max_lon, &max_lat, &radius_km, &longitude, &latitude, &query_limit, &effective_offset]).await {
        Ok(rows) => rows,
        Err(_) => return v2_error(StatusCode::INTERNAL_SERVER_ERROR, "location_query_failed", "V2 location query failed"),
    };
    let has_next = rows.len() as i64 > limit;
    let data = rows
        .into_iter()
        .take(limit as usize)
        .map(|row| V2Location {
            facility_id: row.get(0),
            canonical_name: row.get(1),
            country_code: row.get(2),
            city: row.get(3),
            category: row.get(4),
            factual_review_status: row.get(6),
            privacy_screening_status: row.get(7),
            project_approval: row.get(8),
            reviewer_role: row.get(9),
            publication_warning: if promoted_profile == "community"
                && row.get::<_, String>(6) == "unreviewed"
            {
                Some(UNREVIEWED_COMMUNITY_WARNING.into())
            } else {
                None
            },
            publication_profile: promoted_profile.clone(),
            display_precision: row.get(5),
            latitude: row.get(10),
            longitude: row.get(11),
            first_observed_at: row.get(12),
            last_observed_at: row.get(13),
            observation_count: row.get(14),
            lifecycle_status: row.get(15),
            source_type: row.get(16),
            source_rights_status: row.get(23),
            release_id: row.get(17),
            release_ruleset_version: row.get(18),
            provenance_source_id: row.get(19),
            provenance_source: row.get(20),
            provenance_source_name: row.get(20),
            provenance_source_url: row.get(21),
            provenance_retrieved_at: row.get(22),
        })
        .collect::<Vec<_>>();
    let next_cursor = if has_next {
        data.last().map(|row| row.facility_id.to_string())
    } else {
        None
    };
    let metadata = serde_json::json!({
        "release_id": promoted_release_id,
        "ruleset_version": promoted_ruleset,
        "data_product_version": "uec-public-data-product-v1",
        "schema_version": "uec-location-projection-v1",
        "release_created_at": promoted_created_at,
        "profile": promoted_profile,
        "next_cursor": next_cursor,
        "coverage_note": "Results are eligible public facility projection rows from the selected promoted release after current suppression; they are not story-wide or animal counts.",
        "coverage_scope": "selected_promoted_release_public_facilities",
        "count_semantics": "Each row represents a public facility projection, not an animal count.",
        "query": {"q": params.q, "filters": {"country_code": params.country_code, "region": params.region, "category": params.category, "source_type": params.source_type, "display_precision": params.display_precision, "lifecycle_status": params.lifecycle_status}}
    });
    if transaction.commit().await.is_err() {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            "V2 database transaction failed",
        )
            .into_response();
    }
    Json(serde_json::json!({"data": data, "api_version": "v2", "meta": metadata})).into_response()
}

pub async fn get_v2_location_detail_handler(
    State(state): State<ApiState>,
    Path(facility_id): Path<uuid::Uuid>,
    Query(params): Query<ProfileParams>,
) -> impl IntoResponse {
    let mut client = match state.database.as_ref() {
        Some(pool) => match pool.get().await {
            Ok(client) => client,
            Err(_) => {
                return v2_error(
                    StatusCode::SERVICE_UNAVAILABLE,
                    "database_pool_unavailable",
                    "database pool unavailable",
                );
            }
        },
        None => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "database_not_configured",
                "V2 database is not configured",
            );
        }
    };
    let transaction = match client
        .build_transaction()
        .isolation_level(tokio_postgres::IsolationLevel::RepeatableRead)
        .read_only(true)
        .start()
        .await
    {
        Ok(transaction) => transaction,
        Err(_) => {
            return v2_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "database_transaction_unavailable",
                "V2 database transaction unavailable",
            );
        }
    };
    let requested_profile = params.profile.as_deref().unwrap_or("official");
    if !["official", "secondary", "community"].contains(&requested_profile) {
        return v2_error(
            StatusCode::BAD_REQUEST,
            "invalid_profile",
            "profile is unsupported",
        );
    }
    let release = match transaction.query_opt("SELECT r.release_id, r.ruleset_version, r.created_at, r.profile, (model.release_id IS NOT NULL AND manifest.release_id IS NOT NULL) FROM uec.releases r LEFT JOIN uec.public_discovery_read_models model ON model.release_id=r.release_id LEFT JOIN uec.release_manifests manifest ON manifest.release_id=r.release_id AND manifest.manifest_sha256=model.manifest_sha256 WHERE r.status = 'promoted' AND r.test_only IS NOT TRUE AND r.profile = $1 ORDER BY r.created_at DESC, r.release_id DESC LIMIT 1", &[&requested_profile]).await {
        Ok(release) => release,
        Err(_) => return v2_error(StatusCode::INTERNAL_SERVER_ERROR, "release_query_failed", "V2 release query failed"),
    };
    let Some(release) = release else {
        let _ = transaction.commit().await;
        return v2_error(
            StatusCode::NOT_FOUND,
            "location_not_found",
            "location not found",
        );
    };
    let release_id: String = release.get(0);
    let ruleset: String = release.get(1);
    let created_at: chrono::DateTime<chrono::Utc> = release.get(2);
    let profile: String = release.get(3);
    if !release.get::<_, bool>(4) {
        return v2_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "read_model_unavailable",
            "public discovery read model is missing or stale",
        );
    }
    let row = match transaction.query_opt(r#"
        SELECT history.facility_id, history.canonical_name, history.country_code, history.city, history.classification_category, history.display_precision,
               history.factual_review_status, history.privacy_screening_status, history.maintainer_approval, history.reviewer_role,
               ST_Y(history.display_location::geometry), ST_X(history.display_location::geometry),
               history.first_observed_at, history.last_observed_at, history.observation_count, history.lifecycle_status,
               history.provenance_origin_type, history.release_id, history.release_ruleset_version,
               history.provenance_source_id, history.provenance_source_name, history.provenance_source_url, history.provenance_retrieved_at,
               history.source_rights_status
        FROM uec.map_facilities_public_discovery_read_model AS history
         WHERE history.facility_id = $1 AND history.release_id = $2
         ORDER BY history.observation_id
         LIMIT 1
    "#, &[&facility_id, &release_id]).await {
        Ok(row) => row,
        Err(_) => return v2_error(StatusCode::INTERNAL_SERVER_ERROR, "location_query_failed", "V2 location query failed"),
    };
    let Some(row) = row else {
        let _ = transaction.commit().await;
        return v2_error(
            StatusCode::NOT_FOUND,
            "location_not_found",
            "location not found",
        );
    };
    let item = V2Location {
        facility_id: row.get(0),
        canonical_name: row.get(1),
        country_code: row.get(2),
        city: row.get(3),
        category: row.get(4),
        factual_review_status: row.get(6),
        privacy_screening_status: row.get(7),
        project_approval: row.get(8),
        reviewer_role: row.get(9),
        publication_warning: if profile == "community" && row.get::<_, String>(6) == "unreviewed" {
            Some(UNREVIEWED_COMMUNITY_WARNING.into())
        } else {
            None
        },
        publication_profile: profile.clone(),
        display_precision: row.get(5),
        latitude: row.get(10),
        longitude: row.get(11),
        first_observed_at: row.get(12),
        last_observed_at: row.get(13),
        observation_count: row.get(14),
        lifecycle_status: row.get(15),
        source_type: row.get(16),
        source_rights_status: row.get(23),
        release_id: row.get(17),
        release_ruleset_version: row.get(18),
        provenance_source_id: row.get(19),
        provenance_source: row.get(20),
        provenance_source_name: row.get(20),
        provenance_source_url: row.get(21),
        provenance_retrieved_at: row.get(22),
    };
    if transaction.commit().await.is_err() {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            "V2 database transaction failed",
        )
            .into_response();
    }
    Json(serde_json::json!({"data": item, "api_version": "v2", "meta": {"release_id": release_id, "ruleset_version": ruleset, "data_product_version": "uec-public-data-product-v1", "schema_version": "uec-location-projection-v1", "release_created_at": created_at, "profile": profile, "coverage_scope": "selected_promoted_release_public_facilities", "count_semantics": "This record is a public facility projection, not an animal count."}})).into_response()
}

#[derive(Deserialize)]
pub struct ProfileParams {
    pub profile: Option<String>,
}

#[cfg(test)]
mod v2_api_tests {
    use super::*;
    use axum::{
        Router,
        body::Body,
        http::{Request, StatusCode},
    };
    use tokio_postgres::NoTls;
    use tower::ServiceExt;

    async fn test_state() -> ApiState {
        let mut config = deadpool_postgres::Config::new();
        config.url = Some(std::env::var("UEC_DATABASE_URL").unwrap_or_else(|_| {
            "postgresql://uec:uec-local-development-only@localhost:5433/uec".into()
        }));
        ApiState {
            database: Some(
                config
                    .create_pool(Some(deadpool_postgres::Runtime::Tokio1), NoTls)
                    .unwrap(),
            ),
            dev_preview_token: None,
            dev_test_release_id: None,
            dev_test_release_token: None,
        }
    }

    #[test]
    fn versioned_contract_lists_supported_profiles_and_error_shape() {
        let contract: serde_json::Value =
            serde_json::from_str(include_str!("../docs/api/v2-contract.json")).unwrap();
        assert_eq!(contract["version"], "v2");
        assert_eq!(contract["profiles"].as_array().unwrap().len(), 3);
        assert_eq!(contract["error"]["shape"]["api_version"], "v2");
        assert_eq!(
            contract["endpoints"]["GET /api/v2/discovery/facets"]["success"]["meta"]["coverage_scope"],
            "selected_promoted_release_public_facilities"
        );
        assert!(contract["endpoints"]["GET /api/v2/discovery/facets"]["success"]["meta"]["count_semantics"]
            .as_str().unwrap().contains("not story-wide"));
    }

    #[test]
    fn test_csv_escapes_formula_prefixes_without_mutating_evidence() {
        for value in ["=SUM(A1)", "+cmd", "-cmd", "@cmd"] {
            assert_eq!(csv_safe_value(value.to_string()), format!("'{}", value));
        }
        assert_eq!(csv_safe_value("Facility".into()), "Facility");
    }

    #[test]
    fn candidate_preview_rejects_non_loopback_host_and_origin() {
        let mut local = HeaderMap::new();
        local.insert("host", "127.0.0.1:8000".parse().unwrap());
        assert!(preview_request_is_local(&local));
        local.insert("origin", "https://localhost:3000".parse().unwrap());
        assert!(preview_request_is_local(&local));
        local.insert("origin", "https://attacker.example".parse().unwrap());
        assert!(!preview_request_is_local(&local));
        local.insert("host", "preview.example:8000".parse().unwrap());
        local.remove("origin");
        assert!(!preview_request_is_local(&local));
    }

    #[tokio::test]
    async fn real_preview_requires_local_ephemeral_credential_and_disables_cache() {
        let route = Router::new()
            .route(
                "/dev/real-preview/counts",
                axum::routing::get(get_real_preview_counts_handler),
            )
            .with_state(ApiState {
                database: None,
                dev_preview_token: Some("local-test-token-with-at-least-32-characters".into()),
                dev_test_release_id: None,
                dev_test_release_token: None,
            });
        let response = route
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/dev/real-preview/counts")
                    .header("host", "127.0.0.1:8000")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(response.headers().get("cache-control").unwrap(), "no-store");

        let response = route
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/dev/real-preview/counts")
                    .header("host", "127.0.0.1:8000")
                    .header("x-uec-dev-preview-token", "wrong")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);

        let response = route
            .oneshot(
                Request::builder()
                    .uri("/dev/real-preview/counts")
                    .header("host", "preview.example:8000")
                    .header(
                        "x-uec-dev-preview-token",
                        "local-test-token-with-at-least-32-characters",
                    )
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn real_preview_rejects_unbounded_inputs_before_database_access() {
        let state = ApiState {
            database: None,
            dev_preview_token: Some("local-test-token-with-at-least-32-characters".into()),
            dev_test_release_id: None,
            dev_test_release_token: None,
        };
        let response = Router::new()
            .route("/dev/real-preview/viewport", axum::routing::get(get_real_preview_viewport_handler))
            .with_state(state)
            .oneshot(Request::builder().uri("/dev/real-preview/viewport?west=-180&south=-90&east=180&north=90&limit=501")
                .header("host", "127.0.0.1:8000").header("x-uec-dev-preview-token", "local-test-token-with-at-least-32-characters")
                .body(Body::empty()).unwrap()).await.unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(response.headers().get("cache-control").unwrap(), "no-store");
    }

    #[tokio::test]
    async fn filter_metadata_is_versioned_and_allowlisted() {
        let response = get_v2_filter_metadata_handler().await.into_response();
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(V2_CATEGORIES.len(), 4);
        assert!(!V2_COUNTRIES.contains(&"ZZ"));
    }

    #[tokio::test]
    async fn discovery_rejects_incomplete_or_conflicting_spatial_queries() {
        let state = ApiState {
            database: None,
            dev_preview_token: None,
            dev_test_release_id: None,
            dev_test_release_token: None,
        };
        for uri in [
            "/api/v2/locations?min_lon=8&min_lat=54&max_lon=13",
            "/api/v2/locations?latitude=56&longitude=10",
            "/api/v2/locations?min_lon=8&min_lat=54&max_lon=13&max_lat=58&latitude=56&longitude=10&radius_km=10",
        ] {
            let response = Router::new()
                .route(
                    "/api/v2/locations",
                    axum::routing::get(get_v2_locations_handler),
                )
                .with_state(state.clone())
                .oneshot(Request::builder().uri(uri).body(Body::empty()).unwrap())
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "{uri}");
        }
    }

    #[tokio::test]
    async fn list_rejects_an_unsupported_profile_before_database_access() {
        let state = ApiState {
            database: None,
            dev_preview_token: None,
            dev_test_release_id: None,
            dev_test_release_token: None,
        };
        let response = Router::new()
            .route(
                "/api/v2/locations",
                axum::routing::get(get_v2_locations_handler),
            )
            .with_state(state)
            .oneshot(
                Request::builder()
                    .uri("/api/v2/locations?profile=untrusted")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["api_version"], "v2");
        assert_eq!(json["error"]["code"], "invalid_profile");
    }

    #[tokio::test]
    async fn v2_response_is_json_when_database_is_configured() {
        let url = std::env::var("UEC_DATABASE_URL").unwrap_or_else(|_| {
            "postgresql://uec:uec-local-development-only@localhost:5433/uec".into()
        });
        unsafe {
            std::env::set_var("UEC_DATABASE_URL", url);
        }
        let response = Router::new()
            .route(
                "/api/v2/locations",
                axum::routing::get(get_v2_locations_handler),
            )
            .with_state(test_state().await)
            .oneshot(
                Request::builder()
                    .uri("/api/v2/locations?country_code=DK")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let status = response.status();
        if status != StatusCode::OK {
            let body = axum::body::to_bytes(response.into_body(), usize::MAX)
                .await
                .unwrap();
            panic!(
                "unexpected status {status}: {}",
                String::from_utf8_lossy(&body)
            );
        }
        assert_eq!(
            response.headers().get("content-type").unwrap(),
            "application/json"
        );
        let body = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["api_version"], "v2");
        assert!(json["data"].is_array());
        assert!(json["meta"]["coverage_note"].is_string());
    }

    #[tokio::test]
    async fn v2_filters_are_accepted_without_bypassing_public_release_gate() {
        let url = std::env::var("UEC_DATABASE_URL").unwrap_or_else(|_| {
            "postgresql://uec:uec-local-development-only@localhost:5433/uec".into()
        });
        unsafe {
            std::env::set_var("UEC_DATABASE_URL", url);
        }
        for uri in [
            "/api/v2/locations?country_code=DK&category=retail_and_prepared_food",
            "/api/v2/locations?display_precision=city&lifecycle_status=active_observed",
        ] {
            let response = Router::new()
                .route(
                    "/api/v2/locations",
                    axum::routing::get(get_v2_locations_handler),
                )
                .with_state(test_state().await)
                .oneshot(Request::builder().uri(uri).body(Body::empty()).unwrap())
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            let body = axum::body::to_bytes(response.into_body(), usize::MAX)
                .await
                .unwrap();
            let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
            assert_eq!(json["api_version"], "v2");
            assert!(json["data"].as_array().unwrap().is_empty());
        }
    }

    #[tokio::test]
    async fn v2_default_and_opt_in_profiles_remain_empty_until_promotion() {
        let url = std::env::var("UEC_DATABASE_URL").unwrap_or_else(|_| {
            "postgresql://uec:uec-local-development-only@localhost:5433/uec".into()
        });
        unsafe {
            std::env::set_var("UEC_DATABASE_URL", url);
        }
        for uri in [
            "/api/v2/locations?country_code=ZZ",
            "/api/v2/locations?country_code=ZZ&category=logistics_and_storage",
            "/api/v2/locations?country_code=ZZ&category=retail_and_prepared_food&display_precision=exact",
            "/api/v2/locations?country_code=ZZ&lifecycle_status=explicitly_closed",
        ] {
            let response = Router::new()
                .route(
                    "/api/v2/locations",
                    axum::routing::get(get_v2_locations_handler),
                )
                .with_state(test_state().await)
                .oneshot(Request::builder().uri(uri).body(Body::empty()).unwrap())
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            let body = axum::body::to_bytes(response.into_body(), usize::MAX)
                .await
                .unwrap();
            let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
            assert!(json["data"].as_array().unwrap().is_empty());
        }
    }

    #[tokio::test]
    async fn v2_response_cannot_contain_raw_evidence_fields() {
        let url = std::env::var("UEC_DATABASE_URL").unwrap_or_else(|_| {
            "postgresql://uec:uec-local-development-only@localhost:5433/uec".into()
        });
        unsafe {
            std::env::set_var("UEC_DATABASE_URL", url);
        }
        let response = Router::new()
            .route(
                "/api/v2/locations",
                axum::routing::get(get_v2_locations_handler),
            )
            .with_state(test_state().await)
            .oneshot(
                Request::builder()
                    .uri("/api/v2/locations?country_code=DK")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let body = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let text = String::from_utf8(body.to_vec()).unwrap();
        for forbidden in ["raw_fields", "street_address", "phone", "private_address"] {
            assert!(
                !text.contains(forbidden),
                "public response contained forbidden field {forbidden}"
            );
        }
    }

    #[tokio::test]
    async fn v2_handles_concurrent_requests_through_shared_pool() {
        let state = test_state().await;
        let router = Router::new()
            .route(
                "/api/v2/locations",
                axum::routing::get(get_v2_locations_handler),
            )
            .with_state(state);
        let requests = (0..12).map(|_| {
            let router = router.clone();
            async move {
                router
                    .oneshot(
                        Request::builder()
                            .uri("/api/v2/locations?country_code=DK&limit=1")
                            .body(Body::empty())
                            .unwrap(),
                    )
                    .await
                    .unwrap()
                    .status()
            }
        });
        let statuses = futures_util::future::join_all(requests).await;
        assert!(statuses.iter().all(|status| *status == StatusCode::OK));
    }

    #[test]
    fn v2_schema_serializes_history_and_lifecycle_fields() {
        let item = V2Location {
            facility_id: uuid::Uuid::nil(),
            canonical_name: Some("Example".into()),
            country_code: "DK".into(),
            city: Some("Testby".into()),
            category: "slaughter".into(),
            publication_profile: "official".into(),
            factual_review_status: "reviewed".into(),
            privacy_screening_status: "passed".into(),
            project_approval: "approved".into(),
            reviewer_role: Some("maintainer".into()),
            publication_warning: None,
            display_precision: "city".into(),
            latitude: Some(55.0),
            longitude: Some(10.0),
            first_observed_at: None,
            last_observed_at: None,
            observation_count: Some(2),
            lifecycle_status: "active_observed".into(),
            source_type: "official".into(),
            source_rights_status: "attribution_required".into(),
            provenance_source: None,
            release_id: "test".into(),
            release_ruleset_version: "test".into(),
            provenance_source_id: "test".into(),
            provenance_source_name: "test".into(),
            provenance_source_url: "https://example.invalid".into(),
            provenance_retrieved_at: chrono::Utc::now(),
        };
        let json = serde_json::to_value(item).unwrap();
        assert_eq!(json["display_precision"], "city");
        assert_eq!(json["observation_count"], 2);
        assert_eq!(json["lifecycle_status"], "active_observed");
        assert_eq!(json["source_type"], "official");
        assert_eq!(json["source_rights_status"], "attribution_required");
        assert_eq!(json["category"], "slaughter");
        assert_eq!(json["publication_profile"], "official");
    }

    #[test]
    fn community_export_labels_screened_unreviewed_claims_in_every_row() {
        let row = V2ExportRow {
            facility_id: uuid::Uuid::nil(),
            canonical_name: Some("Synthetic claim".into()),
            country_code: "DK".into(),
            city: Some("Testby".into()),
            category: "slaughter".into(),
            display_precision: "city".into(),
            factual_review_status: "unreviewed".into(),
            privacy_screening_status: "passed".into(),
            project_approval: "pending".into(),
            reviewer_role: None,
            source_type: "user_submitted".into(),
            provenance_source_id: "synthetic.community".into(),
            provenance_source_name: "Synthetic source".into(),
            provenance_source_url: "https://example.invalid/community".into(),
            provenance_retrieved_at: chrono::Utc::now(),
            source_rights_status: "attribution_required".into(),
            release_id: "synthetic-release".into(),
            release_profile: "community".into(),
            profile_notice: export_profile_notice("community").into(),
            publication_warning: export_publication_warning("community", "unreviewed"),
            manifest_sha256: "synthetic-hash".into(),
        };
        let mut writer = csv::Writer::from_writer(Vec::new());
        writer.serialize(row).unwrap();
        let bytes = writer.into_inner().unwrap();
        let mut reader = csv::Reader::from_reader(bytes.as_slice());
        let headers = reader.headers().unwrap().clone();
        let fields = reader.records().next().unwrap().unwrap();
        let value = |name: &str| {
            fields
                .get(headers.iter().position(|h| h == name).unwrap())
                .unwrap()
        };
        assert_eq!(value("release_profile"), "community");
        assert_eq!(value("factual_review_status"), "unreviewed");
        assert_eq!(value("privacy_screening_status"), "passed");
        assert_eq!(value("project_approval"), "pending");
        assert_eq!(value("publication_warning"), UNREVIEWED_COMMUNITY_WARNING);
        assert_eq!(value("profile_notice"), COMMUNITY_EXPORT_NOTICE);
        assert_eq!(value("source_rights_status"), "attribution_required");
        assert!(export_publication_warning("official", "unreviewed").is_none());
        assert!(export_publication_warning("community", "reviewed").is_none());
    }
}

pub async fn get_aphis_reports_handler() -> impl IntoResponse {
    match CACHED_APHIS.as_ref() {
        Ok(reports) => Json(reports.clone()).into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Failed to read APHIS data: {}", e),
        )
            .into_response(),
    }
}

pub async fn get_inspection_reports_handler() -> impl IntoResponse {
    match CACHED_INSPECTION.as_ref() {
        Ok(reports) => Json(reports.clone()).into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Failed to read inspection reports data: {}", e),
        )
            .into_response(),
    }
}

fn parse_all_locations() -> Result<Vec<LocationResponse>, Box<dyn Error>> {
    let mut locations = Vec::new();

    println!("[DEBUG] Starting to parse all locations...");
    println!("[DEBUG] Available directories:");
    for locale_dir in DATA_DIR.dirs() {
        let dir_name = locale_dir
            .path()
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();
        println!("[DEBUG]   - {}", dir_name);
    }

    for locale_dir in DATA_DIR.dirs() {
        let dir_name = locale_dir
            .path()
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();

        let csv_path = format!("{}/locations.csv", dir_name);
        println!("[DEBUG] Looking for: {}", csv_path);
        if let Some(csv_data) = DATA_DIR.get_file(&csv_path) {
            println!("[DEBUG] Found CSV file for country: {}", dir_name);
            let mut reader = csv::Reader::from_reader(csv_data.contents());
            let mut country_count = 0;

            for (idx, result) in reader.deserialize().enumerate() {
                match result {
                    Ok(record) => {
                        let record: Location = record;
                        let animals_slaughtered = get_slaughtered_animals(&record);
                        let animals_processed = get_processed_animals(&record);
                        locations.push(LocationResponse {
                            country: dir_name.clone(),
                            establishment_id: record.establishment_id,
                            establishment_name: record.establishment_name,
                            latitude: record.latitude,
                            longitude: record.longitude,
                            r#type: record.activities,
                            state: record.state,
                            city: record.city,
                            street: record.street,
                            zip: record.zip,
                            slaughter: record.slaughter,
                            animals_slaughtered,
                            dbas: record.dbas,
                            phone: record.phone,
                            slaughter_volume_category: record.slaughter_volume_category,
                            processing_volume_category: record.processing_volume_category,
                            animals_processed,
                            grant_date: record.grant_date,
                        });
                        country_count += 1;
                    }
                    Err(e) => {
                        println!(
                            "[ERROR] Failed to deserialize row {} in {}: {}",
                            idx, dir_name, e
                        );
                        return Err(Box::new(e));
                    }
                }
            }
            println!(
                "[DEBUG] Parsed {} records from country: {}",
                country_count, dir_name
            );
        } else {
            println!("[WARN] CSV file not found: {}", csv_path);
        }
    }
    println!("[DEBUG] Total locations parsed: {}", locations.len());
    Ok(locations)
}

fn parse_aphis_reports() -> Result<Vec<AphisReport>, Box<dyn Error>> {
    let csv_data = include_str!("../static_data/us/aphis_data_final.csv");
    let mut reader = csv::Reader::from_reader(csv_data.as_bytes());

    let mut reports = Vec::new();
    for mut record in reader.deserialize::<AphisReport>().flatten() {
        record.animals_tested = Some(get_tested_animals(&record));
        reports.push(record);
    }
    Ok(reports)
}

fn parse_inspection_reports() -> Result<Vec<InspectionReport>, Box<dyn Error>> {
    let csv_data = include_str!("../static_data/us/inspection_reports.csv");
    let mut reader = csv::Reader::from_reader(csv_data.as_bytes());

    let mut reports = Vec::new();
    for result in reader.deserialize() {
        let record: InspectionReport = result?;
        reports.push(record);
    }
    Ok(reports)
}

#[derive(Deserialize)]
pub struct LocationParams {
    country_code: Option<String>,
}

#[derive(Serialize, Debug, Clone)]
struct LocationResponse {
    country: String,
    establishment_id: String,
    establishment_name: String,
    latitude: f64,
    longitude: f64,
    #[serde(rename = "type")]
    r#type: String,
    state: String,
    city: String,
    street: String,
    zip: String,
    slaughter: String,
    animals_slaughtered: String,
    animals_processed: String,
    slaughter_volume_category: String,
    processing_volume_category: String,
    dbas: String,
    phone: String,
    grant_date: String,
}

// =============================================================================
// APHIS Direct Query Proxy
// =============================================================================

struct AphisContext {
    fwuid: String,
    loaded_version: String,
    fetched_at: Instant,
}

static APHIS_HTTP_CLIENT: Lazy<reqwest::Client> = Lazy::new(|| reqwest::Client::new());
static APHIS_CONTEXT_CACHE: Lazy<Mutex<Option<AphisContext>>> = Lazy::new(|| Mutex::new(None));
const APHIS_CONTEXT_TTL_SECS: u64 = 4 * 3600;

fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut result = Vec::with_capacity(s.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let (Some(h), Some(l)) = (
                (bytes[i + 1] as char).to_digit(16),
                (bytes[i + 2] as char).to_digit(16),
            ) {
                result.push((h * 16 + l) as u8);
                i += 3;
                continue;
            }
        }
        result.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&result).into_owned()
}

async fn fetch_aphis_context() -> Result<AphisContext, String> {
    let html = APHIS_HTTP_CLIENT
        .get("https://aphis.my.site.com/PublicSearchTool/s/annual-reports")
        .header("User-Agent", "Mozilla/5.0")
        .send()
        .await
        .map_err(|e| format!("APHIS page fetch failed: {}", e))?
        .text()
        .await
        .map_err(|e| format!("APHIS page read failed: {}", e))?;

    let inline_pos = html
        .find("/inline.js")
        .ok_or("inline.js not found in APHIS page")?;
    let l_marker = "/sfsites/l/";
    let l_pos = html[..inline_pos]
        .rfind(l_marker)
        .ok_or("sfsites/l/ not found before inline.js in APHIS page")?;
    let encoded_json = &html[l_pos + l_marker.len()..inline_pos];
    let decoded = percent_decode(encoded_json);

    let ctx_json: Value = serde_json::from_str(&decoded)
        .map_err(|e| format!("Failed to parse APHIS context JSON: {}", e))?;

    let fwuid = ctx_json["fwuid"]
        .as_str()
        .ok_or("fwuid not found in APHIS context")?
        .to_string();

    let loaded_version = ctx_json["loaded"]
        .get("APPLICATION@markup://siteforce:communityApp")
        .and_then(|v| v.as_str())
        .ok_or("loaded version not found in APHIS context")?
        .to_string();

    Ok(AphisContext {
        fwuid,
        loaded_version,
        fetched_at: Instant::now(),
    })
}

async fn get_or_refresh_aphis_context(force: bool) -> Result<(String, String), String> {
    {
        let guard = APHIS_CONTEXT_CACHE.lock().await;
        if !force {
            if let Some(ref ctx) = *guard {
                if ctx.fetched_at.elapsed() < Duration::from_secs(APHIS_CONTEXT_TTL_SECS) {
                    return Ok((ctx.fwuid.clone(), ctx.loaded_version.clone()));
                }
            }
        }
    }
    let new_ctx = fetch_aphis_context().await?;
    let result = (new_ctx.fwuid.clone(), new_ctx.loaded_version.clone());
    let mut guard = APHIS_CONTEXT_CACHE.lock().await;
    *guard = Some(new_ctx);
    Ok(result)
}

fn build_ar_message(cert_num: &str) -> Value {
    json!({
        "actions": [{
            "id": "185;a",
            "descriptor": "apex://EFL_PSTController/ACTION$doARSearch",
            "callingDescriptor": "markup://c:EFL_PSTSearchResults",
            "params": {
                "searchCriteria": {
                    "certNumber": cert_num,
                    "index": 0,
                    "numberOfRows": 100,
                    "isARSearch": true
                },
                "parentId": null,
                "getCount": true,
                "hasException": false,
                "hasColE": false
            },
            "version": null
        }]
    })
}

fn build_ir_message(cert_num: &str) -> Value {
    json!({
        "actions": [{
            "id": "185;a",
            "descriptor": "apex://EFL_PSTController/ACTION$doIRSearch_UI",
            "callingDescriptor": "markup://c:EFL_PSTSearchResults",
            "params": {
                "searchCriteria": {
                    "certNumber": cert_num,
                    "index": 0,
                    "numberOfRows": 100
                },
                "parentId": null,
                "hasTeachableMoments": false,
                "getCount": true,
                "irFilterCriteria": null
            },
            "version": null
        }]
    })
}

async fn call_aphis_api(
    fwuid: &str,
    loaded_version: &str,
    message: Value,
    action_name: &str,
    page_uri: &str,
) -> Result<Value, String> {
    let aura_context = json!({
        "mode": "PROD",
        "fwuid": fwuid,
        "app": "siteforce:communityApp",
        "loaded": {
            "APPLICATION@markup://siteforce:communityApp": loaded_version
        },
        "dn": [],
        "globals": {},
        "uad": true
    });

    let url = format!(
        "https://aphis.my.site.com/PublicSearchTool/s/sfsites/aura?r=1&other.EFL_PST.{}=1",
        action_name
    );

    let message_str = message.to_string();
    let context_str = aura_context.to_string();

    let resp = APHIS_HTTP_CLIENT
        .post(&url)
        .form(&[
            ("message", message_str.as_str()),
            ("aura.context", context_str.as_str()),
            ("aura.pageURI", page_uri),
            ("aura.token", "undefined"),
        ])
        .send()
        .await
        .map_err(|e| format!("APHIS API call failed: {}", e))?;

    let body: Value = resp
        .json()
        .await
        .map_err(|e| format!("APHIS API response parse failed: {}", e))?;

    Ok(body)
}

#[derive(Deserialize)]
pub struct AphisQueryParams {
    cert: String,
    #[serde(rename = "type")]
    query_type: String,
}

pub async fn get_aphis_query_handler(Query(params): Query<AphisQueryParams>) -> impl IntoResponse {
    let is_annual = params.query_type == "annual";
    let action_name = if is_annual {
        "doARSearch"
    } else {
        "doIRSearch_UI"
    };
    let page_uri = if is_annual {
        "/PublicSearchTool/s/annual-reports"
    } else {
        "/PublicSearchTool/s/inspection-reports"
    };
    let message = if is_annual {
        build_ar_message(&params.cert)
    } else {
        build_ir_message(&params.cert)
    };

    let (fwuid, loaded) = match get_or_refresh_aphis_context(false).await {
        Ok(ctx) => ctx,
        Err(e) => return (StatusCode::BAD_GATEWAY, e).into_response(),
    };

    let body = match call_aphis_api(&fwuid, &loaded, message.clone(), action_name, page_uri).await {
        Ok(b) => b,
        Err(e) => return (StatusCode::BAD_GATEWAY, e).into_response(),
    };

    let state = body["actions"][0]["state"].as_str().unwrap_or("ERROR");
    let body = if state != "SUCCESS" {
        let (fwuid2, loaded2) = match get_or_refresh_aphis_context(true).await {
            Ok(ctx) => ctx,
            Err(e) => return (StatusCode::BAD_GATEWAY, e).into_response(),
        };
        match call_aphis_api(&fwuid2, &loaded2, message, action_name, page_uri).await {
            Ok(b) => b,
            Err(e) => return (StatusCode::BAD_GATEWAY, e).into_response(),
        }
    } else {
        body
    };

    let results = body["actions"][0]["returnValue"]["results"].clone();
    let results = if results.is_array() {
        results
    } else {
        Value::Array(vec![])
    };
    Json(results).into_response()
}
