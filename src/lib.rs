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
use std::collections::HashMap;
use std::error::Error;
use std::path::PathBuf;
use std::sync::{Arc, Mutex as StdMutex};
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

fn release_manifest_etag(manifest_sha256: &str, suppression_generation: i64) -> String {
    format!("\"{manifest_sha256}-{suppression_generation}\"")
}

fn if_none_match(headers: &HeaderMap, etag: &str) -> bool {
    headers
        .get(axum::http::header::IF_NONE_MATCH)
        .and_then(|value| value.to_str().ok())
        .is_some_and(|value| {
            value.split(',').any(|candidate| {
                let candidate = candidate.trim();
                candidate == "*" || candidate == etag || candidate.strip_prefix("W/") == Some(etag)
            })
        })
}

pub async fn get_v2_release_manifest_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
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
    let suppression_generation: i64 = match client.query_one(
        "SELECT generation FROM uec.public_suppression_generation",
        &[],
    ).await {
        Ok(row) => row.get(0),
        Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "suppression_generation_unavailable", "current publication eligibility unavailable"),
    };
    let etag = release_manifest_etag(&digest, suppression_generation);
    let cache_control = HeaderValue::from_static("public, max-age=0, must-revalidate");
    if if_none_match(&headers, &etag) {
        return Response::builder()
            .status(StatusCode::NOT_MODIFIED)
            .header(axum::http::header::ETAG, etag)
            .header(axum::http::header::CACHE_CONTROL, cache_control)
            .header("x-uec-suppression-generation", suppression_generation.to_string())
            .body(axum::body::Body::empty())
            .expect("manifest 304 response is valid")
            .into_response();
    }
    Response::builder()
        .status(StatusCode::OK)
        .header(axum::http::header::ETAG, etag)
        .header(axum::http::header::CACHE_CONTROL, cache_control)
        .header("x-uec-suppression-generation", suppression_generation.to_string())
        .header("content-type", "application/json")
        .body(axum::body::Body::from(Json(json!({"api_version":"v2", "data": {"release_id": row.get::<_,String>(0), "profile": row.get::<_,String>(1), "manifest": manifest, "manifest_sha256": digest, "suppression_generation": suppression_generation}})).to_string()))
        .expect("manifest response is valid")
        .into_response()
}

#[derive(Deserialize)]
pub struct PublicMapTilePath {
    release_id: String,
    tile_path: String,
}

#[derive(Deserialize)]
pub struct PublicMapTileParams {
    profile: Option<String>,
}

/// Serve an immutable MVT only while its release/profile and suppression
/// generation remain currently eligible. The staged artifact directory is
/// private until promotion makes the manifest lookup succeed.
fn map_artifact_feature_schema_valid(map_artifact: &Value) -> bool {
    let v1_properties = json!(["feature_key", "kind", "count", "exact_count", "coarse_count", "next_zoom", "record_id", "category_key"]);
    let v2_properties = json!(["feature_key", "kind", "count", "exact_count", "coarse_count", "next_zoom", "record_id", "category_key", "category_keys_compact"]);
    (map_artifact["feature_schema_version"] == "uec-map-feature-v1" && map_artifact["feature_properties"] == v1_properties)
        || (map_artifact["feature_schema_version"] == "uec-map-feature-v2" && map_artifact["feature_properties"] == v2_properties)
}

pub async fn get_v2_map_tile_handler(
    State(state): State<ApiState>,
    Path(path): Path<PublicMapTilePath>,
    headers: HeaderMap,
    Query(params): Query<PublicMapTileParams>,
) -> impl IntoResponse {
    if path.release_id.is_empty()
        || path.release_id.len() > 160
        || !path.release_id.bytes().all(|value| value.is_ascii_alphanumeric() || matches!(value, b'.' | b'_' | b'-'))
        || path.release_id == "."
        || path.release_id == ".."
    {
        return v2_error(StatusCode::BAD_REQUEST, "invalid_map_tile", "tile coordinates or release ID are invalid");
    }
    let profile = params.profile.as_deref().unwrap_or("official");
    if !V2_PROFILES.contains(&profile) {
        return v2_error(StatusCode::BAD_REQUEST, "invalid_profile", "profile is unsupported");
    }
    let parts = path.tile_path.split('/').collect::<Vec<_>>();
    if parts.len() != 3 {
        return v2_error(StatusCode::BAD_REQUEST, "invalid_map_tile", "tile coordinates are invalid");
    }
    let (Ok(z), Ok(x), Ok(y)) = (parts[0].parse::<u8>(), parts[1].parse::<u32>(), parts[2].strip_suffix(".mvt").unwrap_or("").parse::<u32>()) else {
        return v2_error(StatusCode::BAD_REQUEST, "invalid_map_tile", "tile coordinates are invalid");
    };
    if z > 14 || x >= (1u32 << z) || y >= (1u32 << z) {
        return v2_error(StatusCode::BAD_REQUEST, "invalid_map_tile", "tile coordinates are invalid");
    }
    let Some(pool) = state.database else {
        return v2_error(StatusCode::SERVICE_UNAVAILABLE, "database_not_configured", "V2 database is not configured");
    };
    let client = match pool.get().await {
        Ok(client) => client,
        Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "database_pool_unavailable", "database pool unavailable"),
    };
    let release_row = match client.query_opt(
        "SELECT manifest.manifest::text,manifest.manifest_sha256 FROM uec.releases release JOIN uec.release_manifests manifest ON manifest.release_id=release.release_id WHERE release.release_id=$1 AND release.profile=$2 AND release.status='promoted' AND release.test_only IS NOT TRUE",
        &[&path.release_id, &profile],
    ).await {
        Ok(row) => row,
        Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "map_tile_unavailable", "public map tile unavailable"),
    };
    let Some(release_row) = release_row else {
        return v2_error(StatusCode::GONE, "release_unavailable", "displayed release is no longer eligible");
    };
    let manifest_text: String = release_row.get(0);
    let manifest: Value = match serde_json::from_str(&manifest_text) {
        Ok(manifest) => manifest,
        Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "release_manifest_invalid", "release manifest integrity check failed"),
    };
    let manifest_digest: String = release_row.get(1);
    if format!("{:x}", Sha256::digest(canonical_json(&manifest).as_bytes())) != manifest_digest {
        return v2_error(StatusCode::SERVICE_UNAVAILABLE, "release_manifest_invalid", "release manifest integrity check failed");
    }
    let map_artifact = &manifest["map_artifact"];
    let expected_template = format!("/api/v2/releases/{}/map/tiles/{{z}}/{{x}}/{{y}}.mvt?profile={}", path.release_id, profile);
    if map_artifact["release_id"] != path.release_id
        || map_artifact["profile"] != profile
        || map_artifact["source_layer"] != "uec_map"
        || !map_artifact_feature_schema_valid(map_artifact)
        || map_artifact["min_zoom"].as_u64() != Some(0)
        || map_artifact["max_zoom"].as_u64() != Some(14)
        || map_artifact["tile_url_template"] != expected_template
        || map_artifact["cache_policy"]["max_age_seconds"].as_u64() != Some(0)
        || map_artifact["cache_policy"]["cache_control"] != "public, max-age=0, must-revalidate"
    {
        return v2_error(StatusCode::NOT_FOUND, "map_artifact_not_found", "public map tile unavailable");
    }
    let suppression_generation: i64 = match client.query_one("SELECT generation FROM uec.public_suppression_generation", &[]).await {
        Ok(row) => row.get(0),
        Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "suppression_generation_unavailable", "current publication eligibility unavailable"),
    };
    if map_artifact["suppression_generation"].as_i64() != Some(suppression_generation) {
        return v2_error(StatusCode::GONE, "map_artifact_revoked", "map artifact is no longer eligible");
    }
    let Some(tile) = map_artifact["tiles"].as_array().and_then(|tiles| tiles.iter().find(|tile| {
        tile["z"].as_u64() == Some(u64::from(z))
            && tile["x"].as_u64() == Some(u64::from(x))
            && tile["y"].as_u64() == Some(u64::from(y))
    })) else {
        return v2_error(StatusCode::NOT_FOUND, "map_tile_not_found", "map tile contains no public features");
    };
    let Some(root) = std::env::var_os("UEC_PUBLIC_MAP_ARTIFACT_ROOT").map(PathBuf::from) else {
        return v2_error(StatusCode::SERVICE_UNAVAILABLE, "map_artifact_unavailable", "public map artifacts are not configured");
    };
    let tile_path = root.join(&path.release_id).join(profile).join(z.to_string()).join(x.to_string()).join(format!("{y}.mvt"));
    let bytes = match std::fs::read(&tile_path) {
        Ok(bytes) if bytes.len() <= 2 * 1024 * 1024 => bytes,
        _ => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "map_artifact_unavailable", "public map artifact is unavailable"),
    };
    let expected_digest = tile["sha256"].as_str().unwrap_or_default();
    let actual_digest = format!("{:x}", Sha256::digest(&bytes));
    if expected_digest.len() != 64 || actual_digest != expected_digest {
        return v2_error(StatusCode::SERVICE_UNAVAILABLE, "map_artifact_invalid", "public map artifact integrity check failed");
    }
    let etag = format!("\"{expected_digest}\"");
    let max_age = map_artifact["cache_policy"]["max_age_seconds"].as_u64().unwrap_or(0).min(30);
    let cache_control = format!("public, max-age={max_age}, must-revalidate");
    if if_none_match(&headers, &etag) {
        return Response::builder()
            .status(StatusCode::NOT_MODIFIED)
            .header(axum::http::header::ETAG, etag)
            .header(axum::http::header::CACHE_CONTROL, cache_control)
            .header("x-uec-release-id", path.release_id)
            .header("x-uec-profile", profile)
            .header("x-uec-suppression-generation", suppression_generation.to_string())
            .body(axum::body::Body::empty())
            .expect("map tile 304 response is valid")
            .into_response();
    }
    Response::builder()
        .status(StatusCode::OK)
        .header(axum::http::header::CONTENT_TYPE, "application/vnd.mapbox-vector-tile")
        .header(axum::http::header::ETAG, etag)
        .header(axum::http::header::CACHE_CONTROL, cache_control)
        .header("x-uec-release-id", path.release_id)
        .header("x-uec-profile", profile)
        .header("x-uec-suppression-generation", suppression_generation.to_string())
        .body(axum::body::Body::from(bytes))
        .expect("map tile response is valid")
        .into_response()
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

/// Bump when tile properties or rendering semantics change.  Keeping it in
/// the key prevents an in-process deploy from serving bytes encoded for an
/// older frontend contract.
const REAL_PREVIEW_MVT_CONTRACT_VERSION: u8 = 1;
const REAL_PREVIEW_MVT_CACHE_TTL: Duration = Duration::from_secs(45);
const REAL_PREVIEW_MVT_CACHE_MAX_ENTRIES: usize = 768;
const REAL_PREVIEW_HIERARCHY_CACHE_MAX_ENTRIES: usize = 24;

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
struct RealPreviewMvtTileCacheKey {
    contract_version: u8,
    snapshot_boundary: String,
    source_id: Option<String>,
    cluster_cutoff_half_steps: u8,
    z: u8,
    x: u32,
    y: u32,
}

#[derive(Clone)]
struct RealPreviewMvtTileCacheEntry {
    bytes: Arc<[u8]>,
    inserted_at: Instant,
    last_used: u64,
}

struct RealPreviewMvtTileCacheInner {
    entries: HashMap<RealPreviewMvtTileCacheKey, RealPreviewMvtTileCacheEntry>,
    clock: u64,
}

/// A bounded LRU-ish tile-byte cache.  The lock only guards a HashMap lookup
/// or insertion; database work is always performed after it is released.
pub struct RealPreviewMvtTileCache {
    inner: StdMutex<RealPreviewMvtTileCacheInner>,
}

/// Private, process-local acceleration only. This is never an HTTP cache:
/// preview responses still carry `no-store` and no request credential is a
/// cache key. A process-level cache also keeps normal API state construction
/// simple for public routes that never touch the private tile projection.
static REAL_PREVIEW_MVT_TILE_CACHE: Lazy<RealPreviewMvtTileCache> =
    Lazy::new(RealPreviewMvtTileCache::default);

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
struct RealPreviewHierarchyCacheKey {
    contract_version: u8,
    snapshot_boundary: String,
    source_id: Option<String>,
    cluster_cutoff_half_steps: u8,
    z: u8,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct RealPreviewHierarchyFeature {
    feature_key: String,
    parent_key: Option<String>,
    kind: String,
    count: i32,
    precision: String,
    next_zoom: i32,
    x: f64,
    y: f64,
}

fn real_preview_hierarchy_tile_features(
    features: &[RealPreviewHierarchyFeature],
    zoom: u8,
    tile_x: u32,
    tile_y: u32,
) -> Vec<RealPreviewHierarchyFeature> {
    const WEB_MERCATOR_HALF_WORLD: f64 = std::f64::consts::PI * 6_378_137.0;
    let count = 2_f64.powi(i32::from(zoom));
    let tile_size = 2.0 * WEB_MERCATOR_HALF_WORLD / count;
    let buffer = tile_size * (512.0 / 4096.0);
    let min_x = -WEB_MERCATOR_HALF_WORLD + f64::from(tile_x) * tile_size - buffer;
    let max_x = min_x + tile_size + 2.0 * buffer;
    let max_y = WEB_MERCATOR_HALF_WORLD - f64::from(tile_y) * tile_size + buffer;
    let min_y = max_y - tile_size - 2.0 * buffer;
    let world_width = 2.0 * WEB_MERCATOR_HALF_WORLD;
    let mut selected = Vec::new();
    for feature in features {
        if feature.y < min_y || feature.y > max_y {
            continue;
        }
        if feature.x >= min_x && feature.x <= max_x {
            selected.push(feature.clone());
        } else if feature.x - world_width >= min_x && feature.x - world_width <= max_x {
            let mut wrapped = feature.clone();
            wrapped.x -= world_width;
            selected.push(wrapped);
        } else if feature.x + world_width >= min_x && feature.x + world_width <= max_x {
            let mut wrapped = feature.clone();
            wrapped.x += world_width;
            selected.push(wrapped);
        }
    }
    selected
}

#[derive(Clone)]
struct RealPreviewHierarchyCacheEntry {
    features: Arc<[RealPreviewHierarchyFeature]>,
    inserted_at: Instant,
}

#[derive(Default)]
struct RealPreviewHierarchyCache {
    inner: StdMutex<HashMap<RealPreviewHierarchyCacheKey, RealPreviewHierarchyCacheEntry>>,
}

static REAL_PREVIEW_CLUSTER_HIERARCHY_CACHE: Lazy<RealPreviewHierarchyCache> =
    Lazy::new(RealPreviewHierarchyCache::default);
static REAL_PREVIEW_CLUSTER_HIERARCHY_BUILD_LOCK: Lazy<Mutex<()>> =
    Lazy::new(|| Mutex::new(()));

impl RealPreviewHierarchyCache {
    fn get(&self, key: &RealPreviewHierarchyCacheKey) -> Option<Arc<[RealPreviewHierarchyFeature]>> {
        let mut inner = self.inner.lock().expect("MVT hierarchy cache lock is not poisoned");
        let now = Instant::now();
        inner.retain(|_, entry| now.duration_since(entry.inserted_at) <= REAL_PREVIEW_MVT_CACHE_TTL);
        inner.get(key).map(|entry| Arc::clone(&entry.features))
    }

    fn insert(
        &self,
        key: RealPreviewHierarchyCacheKey,
        features: Vec<RealPreviewHierarchyFeature>,
    ) -> Arc<[RealPreviewHierarchyFeature]> {
        let mut inner = self.inner.lock().expect("MVT hierarchy cache lock is not poisoned");
        if inner.len() >= REAL_PREVIEW_HIERARCHY_CACHE_MAX_ENTRIES {
            if let Some(oldest) = inner.iter().min_by_key(|(_, entry)| entry.inserted_at).map(|(key, _)| key.clone()) {
                inner.remove(&oldest);
            }
        }
        let features: Arc<[RealPreviewHierarchyFeature]> = Arc::from(features);
        inner.insert(key, RealPreviewHierarchyCacheEntry { features: Arc::clone(&features), inserted_at: Instant::now() });
        features
    }
}

#[derive(Clone)]
struct RealPreviewClusterMember {
    feature_key: String,
    kind: String,
    source_id: Option<String>,
    precision: String,
    weight: i32,
    x: f64,
    y: f64,
}

fn real_preview_cells_are_neighbors(cell_x: i64, cell_y: i64, other_x: i64, other_y: i64, cell_size: f64, radius: f64) -> bool {
    let gap_x = (cell_x.abs_diff(other_x).saturating_sub(1) as f64) * cell_size;
    let gap_y = (cell_y.abs_diff(other_y).saturating_sub(1) as f64) * cell_size;
    gap_x * gap_x + gap_y * gap_y <= radius * radius
}

fn real_preview_find_cluster_root(parents: &mut [usize], mut index: usize) -> usize {
    while parents[index] != index {
        parents[index] = parents[parents[index]];
        index = parents[index];
    }
    index
}

fn real_preview_union_clusters(parents: &mut [usize], first: usize, second: usize) {
    let left = real_preview_find_cluster_root(parents, first);
    let right = real_preview_find_cluster_root(parents, second);
    if left != right {
        let (root, child) = if left < right { (left, right) } else { (right, left) };
        parents[child] = root;
    }
}

fn real_preview_opaque_key(namespace: &str, value: &str) -> String {
    let digest = Sha256::digest(format!("{namespace}:{value}").as_bytes());
    digest[..16].iter().map(|byte| format!("{byte:02x}")).collect()
}

fn real_preview_build_cluster_features(
    mut members: Vec<RealPreviewClusterMember>,
    radius: f64,
    zoom: u8,
) -> Vec<RealPreviewHierarchyFeature> {
    members.sort_by(|left, right| left.feature_key.cmp(&right.feature_key));
    if members.is_empty() || !radius.is_finite() || radius <= 0.0 {
        return Vec::new();
    }
    // Cells are only an acceleration structure, not cluster boundaries. A
    // cell diagonal is <= radius, so every member of a dense cell is connected;
    // neighboring cells are joined only after an exact distance test.
    let cell_size = radius / std::f64::consts::SQRT_2;
    let cells: Vec<_> = members.iter().map(|member| ((member.x / cell_size).floor() as i64, (member.y / cell_size).floor() as i64)).collect();
    let mut buckets: HashMap<(i64, i64), Vec<usize>> = HashMap::new();
    for (index, cell) in cells.iter().copied().enumerate() {
        buckets.entry(cell).or_default().push(index);
    }
    let mut core = vec![false; members.len()];
    for (cell, bucket) in &buckets {
        if bucket.len() >= 3 {
            for index in bucket { core[*index] = true; }
            continue;
        }
        for index in bucket {
            let point = &members[*index];
            let mut neighbor_count = 0;
            for dx in -2..=2 {
                for dy in -2..=2 {
                    if !real_preview_cells_are_neighbors(cell.0, cell.1, cell.0 + dx, cell.1 + dy, cell_size, radius) { continue; }
                    if let Some(neighbors) = buckets.get(&(cell.0 + dx, cell.1 + dy)) {
                        for other in neighbors {
                            let candidate = &members[*other];
                            let x = candidate.x - point.x;
                            let y = candidate.y - point.y;
                            if x * x + y * y <= radius * radius {
                                neighbor_count += 1;
                                if neighbor_count >= 3 { core[*index] = true; break; }
                            }
                        }
                    }
                    if core[*index] { break; }
                }
                if core[*index] { break; }
            }
        }
    }
    let mut parents: Vec<_> = (0..members.len()).collect();
    let mut ordered_cells: Vec<_> = buckets.keys().copied().collect();
    ordered_cells.sort_unstable();
    let mut cell_representatives = HashMap::new();
    for cell in &ordered_cells {
        let Some(bucket) = buckets.get(cell) else { continue; };
        let mut representative = None;
        for index in bucket {
            if core[*index] {
                if let Some(first) = representative {
                    real_preview_union_clusters(&mut parents, first, *index);
                } else {
                    representative = Some(*index);
                }
            }
        }
        if let Some(representative) = representative { cell_representatives.insert(*cell, representative); }
    }
    for cell in &ordered_cells {
        let Some(&representative) = cell_representatives.get(cell) else { continue; };
        for dx in -2..=2 {
            for dy in -2..=2 {
                let neighbor_cell = (cell.0 + dx, cell.1 + dy);
                if neighbor_cell <= *cell || !real_preview_cells_are_neighbors(cell.0, cell.1, neighbor_cell.0, neighbor_cell.1, cell_size, radius) { continue; }
                let Some(&neighbor_representative) = cell_representatives.get(&neighbor_cell) else { continue; };
                let first_bucket = &buckets[cell];
                let second_bucket = &buckets[&neighbor_cell];
                let mut connected = false;
                'pairs: for first in first_bucket.iter().filter(|index| core[**index]) {
                    for second in second_bucket.iter().filter(|index| core[**index]) {
                        let dx = members[*first].x - members[*second].x;
                        let dy = members[*first].y - members[*second].y;
                        if dx * dx + dy * dy <= radius * radius {
                            connected = true;
                            break 'pairs;
                        }
                    }
                }
                if connected { real_preview_union_clusters(&mut parents, representative, neighbor_representative); }
            }
        }
    }
    let mut assignments = vec![None; members.len()];
    for index in 0..members.len() {
        if core[index] {
            assignments[index] = Some(real_preview_find_cluster_root(&mut parents, index));
            continue;
        }
        let cell = cells[index];
        let point = &members[index];
        'neighbor_cells: for dx in -2..=2 {
            for dy in -2..=2 {
                let neighbor_cell = (cell.0 + dx, cell.1 + dy);
                if !real_preview_cells_are_neighbors(cell.0, cell.1, neighbor_cell.0, neighbor_cell.1, cell_size, radius) { continue; }
                let Some(bucket) = buckets.get(&neighbor_cell) else { continue; };
                for neighbor in bucket {
                    if !core[*neighbor] { continue; }
                    let adjacent = &members[*neighbor];
                    let distance_x = point.x - adjacent.x;
                    let distance_y = point.y - adjacent.y;
                    if distance_x * distance_x + distance_y * distance_y <= radius * radius {
                        assignments[index] = Some(real_preview_find_cluster_root(&mut parents, *neighbor));
                        break 'neighbor_cells;
                    }
                }
            }
        }
    }
    let mut grouped: HashMap<usize, Vec<usize>> = HashMap::new();
    for (index, root) in assignments.iter().enumerate() {
        if let Some(root) = root { grouped.entry(*root).or_default().push(index); }
    }
    let mut output = Vec::with_capacity(grouped.len() + members.len());
    for indexes in grouped.values() {
        let mut sorted_keys: Vec<_> = indexes.iter().map(|index| members[*index].feature_key.as_str()).collect();
        sorted_keys.sort_unstable();
        let min_key = sorted_keys.first().copied().unwrap_or_default();
        let max_key = sorted_keys.last().copied().unwrap_or_default();
        let mut sum_x = 0.0;
        let mut sum_y = 0.0;
        let mut represented = 0_i32;
        for index in indexes {
            sum_x += members[*index].x;
            sum_y += members[*index].y;
            represented += members[*index].weight;
        }
        let feature_key = real_preview_opaque_key("cluster", &format!("{min_key}:{max_key}:{}:{zoom}", indexes.len()));
        output.push(RealPreviewHierarchyFeature {
            feature_key,
            parent_key: None,
            kind: "cluster".into(),
            count: represented,
            precision: "mixed_location_cluster".into(),
            next_zoom: i32::from(zoom.saturating_add(1).min(14)),
            x: sum_x / indexes.len() as f64,
            y: sum_y / indexes.len() as f64,
        });
    }
    for (index, root) in assignments.iter().enumerate() {
        if root.is_some() { continue; }
        let member = &members[index];
        let precision = if member.source_id.as_deref() == Some("us.fsis") && member.precision == "source-provided" {
            "source_provided_unverified"
        } else if member.kind == "city_reference" {
            &member.precision
        } else if ["numeric", "exact", "source_numeric", "source_coordinates", "facility_coordinate"].contains(&member.precision.as_str()) {
            "source_numeric_pending_review"
        } else if member.precision == "source-provided" {
            "approximate_source_provided_pending_review"
        } else {
            "approximate_source_precision_unknown_pending_review"
        };
        output.push(RealPreviewHierarchyFeature {
            feature_key: member.feature_key.clone(),
            parent_key: None,
            kind: member.kind.clone(),
            count: member.weight,
            precision: precision.to_owned(),
            next_zoom: i32::from(zoom.saturating_add(1).min(14)),
            x: member.x,
            y: member.y,
        });
    }
    output.sort_by(|left, right| left.feature_key.cmp(&right.feature_key));
    output
}

async fn get_or_build_real_preview_cluster_hierarchy(
    client: &tokio_postgres::Client,
    key: RealPreviewHierarchyCacheKey,
    cluster_radius: f64,
) -> Option<Arc<[RealPreviewHierarchyFeature]>> {
    if let Some(features) = REAL_PREVIEW_CLUSTER_HIERARCHY_CACHE.get(&key) {
        return Some(features);
    }
    let _build_guard = REAL_PREVIEW_CLUSTER_HIERARCHY_BUILD_LOCK.lock().await;
    if let Some(features) = REAL_PREVIEW_CLUSTER_HIERARCHY_CACHE.get(&key) {
        return Some(features);
    }
    let sql = r#"
WITH sources AS (
  SELECT source_id FROM real_preview.source_preview_runs
  UNION
  SELECT source_id FROM real_preview.source_manifests
),
latest AS (
  SELECT sources.source_id,
         COALESCE(
           (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
            WHERE run.source_id = sources.source_id
            ORDER BY run.created_at DESC, run.run_id DESC LIMIT 1),
           (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
            WHERE manifest.source_id = sources.source_id
            ORDER BY manifest.retrieved_at DESC, manifest.snapshot_sha256 DESC LIMIT 1)
         ) AS snapshot_sha256
  FROM sources
),
placeable AS (
  SELECT c.candidate_id::text AS candidate_id, c.source_id,
         COALESCE(c.coordinate_precision,'') AS coordinate_precision,
         c.display_geometry_source,
         CASE WHEN c.display_geometry_source IS NULL THEN c.longitude ELSE c.display_longitude END AS longitude,
         CASE WHEN c.display_geometry_source IS NULL THEN c.latitude ELSE c.display_latitude END AS latitude
  FROM real_preview.candidates c
  WHERE c.default_map_scope = true
    AND c.location_class IN ('numeric_source_coordinate','city_postal')
    AND (
      (c.display_geometry_source IS NULL AND c.longitude BETWEEN -180 AND 180
       AND c.latitude BETWEEN -90 AND 90 AND (c.longitude <> 0 OR c.latitude <> 0))
      OR (c.display_geometry_source IS NOT NULL AND c.display_longitude BETWEEN -180 AND 180
          AND c.display_latitude BETWEEN -90 AND 90
          AND (c.display_longitude <> 0 OR c.display_latitude <> 0))
    )
    AND (c.source_id, c.snapshot_sha256) IN (SELECT source_id, snapshot_sha256 FROM latest)
    AND ($1::text IS NULL OR c.source_id = $1)
),
numeric AS (
  SELECT candidate_id, source_id, coordinate_precision, longitude, latitude
  FROM placeable WHERE display_geometry_source IS NULL
),
reference_points AS (
  SELECT longitude, latitude, count(*)::integer AS count,
         CASE WHEN bool_and(display_geometry_source LIKE '%approximate locality reference; not facility coordinates%')
              THEN 'locality_reference_coarse'::text
              ELSE 'city_reference_approximate'::text END AS precision
  FROM placeable
  WHERE display_geometry_source IS NOT NULL
  GROUP BY longitude, latitude
)
SELECT candidate_id,source_id,coordinate_precision,display_geometry_source,longitude,latitude
FROM placeable
ORDER BY candidate_id
"#;
    let rows = client.query(sql, &[&key.source_id]).await.ok()?;
    let mut members = Vec::with_capacity(rows.len());
    let mut references: HashMap<(u64, u64), (f64, f64, i32, bool)> = HashMap::new();
    for row in rows {
        let candidate_id: String = row.get(0);
        let source_id: String = row.get(1);
        let coordinate_precision: String = row.get(2);
        let display_geometry_source: Option<String> = row.get(3);
        let longitude: f64 = row.get(4);
        let latitude: f64 = row.get(5);
        let latitude = latitude.clamp(-85.05112878, 85.05112878).to_radians();
        let x = longitude.to_radians() * 6_378_137.0;
        let y = (std::f64::consts::FRAC_PI_4 + latitude / 2.0).tan().ln() * 6_378_137.0;
        if let Some(display_source) = display_geometry_source {
            let entry = references.entry((longitude.to_bits(), row.get::<_, f64>(5).to_bits()))
                .or_insert((x, y, 0, true));
            entry.2 += 1;
            entry.3 &= display_source.contains("approximate locality reference; not facility coordinates");
        } else {
            members.push(RealPreviewClusterMember {
                feature_key: candidate_id,
                kind: "source_coordinate".into(),
                source_id: Some(source_id),
                precision: coordinate_precision,
                weight: 1,
                x,
                y,
            });
        }
    }
    for ((longitude_bits, latitude_bits), (x, y, count, all_locality)) in references {
        let longitude = f64::from_bits(longitude_bits);
        let latitude = f64::from_bits(latitude_bits);
        members.push(RealPreviewClusterMember {
            feature_key: real_preview_opaque_key("city-reference", &format!("{longitude:.12}:{latitude:.12}")),
            kind: "city_reference".into(),
            source_id: None,
            precision: if all_locality { "locality_reference_coarse" } else { "city_reference_approximate" }.into(),
            weight: count,
            x,
            y,
        });
    }
    let features = real_preview_build_cluster_features(members, cluster_radius, key.z);
    Some(REAL_PREVIEW_CLUSTER_HIERARCHY_CACHE.insert(key, features))
}

impl Default for RealPreviewMvtTileCache {
    fn default() -> Self {
        Self {
            inner: StdMutex::new(RealPreviewMvtTileCacheInner {
                entries: HashMap::new(),
                clock: 0,
            }),
        }
    }
}

impl RealPreviewMvtTileCache {
    fn get(&self, key: &RealPreviewMvtTileCacheKey) -> Option<Arc<[u8]>> {
        let mut inner = self.inner.lock().expect("MVT tile cache lock is not poisoned");
        let now = Instant::now();
        if inner
            .entries
            .get(key)
            .is_some_and(|entry| now.duration_since(entry.inserted_at) > REAL_PREVIEW_MVT_CACHE_TTL)
        {
            inner.entries.remove(key);
            return None;
        }
        inner.clock = inner.clock.wrapping_add(1);
        let clock = inner.clock;
        inner.entries.get_mut(key).map(|entry| {
            entry.last_used = clock;
            Arc::clone(&entry.bytes)
        })
    }

    fn insert(&self, key: RealPreviewMvtTileCacheKey, bytes: Vec<u8>) -> Arc<[u8]> {
        let mut inner = self.inner.lock().expect("MVT tile cache lock is not poisoned");
        inner.clock = inner.clock.wrapping_add(1);
        let bytes: Arc<[u8]> = bytes.into();
        let clock = inner.clock;
        inner.entries.insert(
            key,
            RealPreviewMvtTileCacheEntry {
                bytes: Arc::clone(&bytes),
                inserted_at: Instant::now(),
                last_used: clock,
            },
        );
        if inner.entries.len() > REAL_PREVIEW_MVT_CACHE_MAX_ENTRIES {
            if let Some(oldest) = inner
                .entries
                .iter()
                .min_by_key(|(_, entry)| entry.last_used)
                .map(|(key, _)| key.clone())
            {
                inner.entries.remove(&oldest);
            }
        }
        bytes
    }
}

#[derive(Deserialize)]
pub struct RealPreviewPageParams {
    pub cursor: Option<uuid::Uuid>,
    pub limit: Option<i64>,
    pub q: Option<String>,
    pub source_id: Option<String>,
    pub default_map_scope: Option<bool>,
    /// Comma-separated taxonomy primary keys; multiple values use OR semantics.
    pub category_keys: Option<String>,
}

#[derive(Deserialize)]
pub struct RealPreviewViewportParams {
    pub west: f64,
    pub south: f64,
    pub east: f64,
    pub north: f64,
    pub cursor: Option<uuid::Uuid>,
    pub limit: Option<i64>,
    pub source_id: Option<String>,
}

/// The tile route intentionally accepts only a small, source-shaped selector.
/// It is never reflected into a response and is still passed as a bound SQL
/// parameter.  This keeps the private map source from becoming a general
/// purpose query surface.
#[derive(Deserialize)]
pub struct RealPreviewTileParams {
    pub source_id: Option<String>,
    pub cluster_cutoff: Option<f64>,
}

/// Compact private map payload used by the browser's local cluster index.
/// Numeric candidates remain one feature each; coarse administrative places
/// are grouped by reference geometry and source so source filters preserve
/// their represented weight.
#[derive(Deserialize)]
pub struct RealPreviewMapFeedParams {
    pub source_id: Option<String>,
}

const REAL_PREVIEW_MAP_FEED_MAX_FEATURES: i64 = 200_000;

// Keep the per-candidate taxonomy projection in the same SQL query as the
// list/detail response. This avoids an N+1 request/query path and preserves
// latest-set semantics while remaining additive to the legacy scalar field.
const REAL_PREVIEW_TAXONOMY_SELECT_SQL: &str = r#"
, COALESCE((
    SELECT s.display_category
    FROM real_preview.candidate_taxonomy_assignment_sets s
    WHERE s.candidate_id=candidate.candidate_id AND s.taxonomy_version='uec-taxonomy-v1'
    ORDER BY s.created_at DESC,s.assignment_set_id DESC LIMIT 1
  ), CASE WHEN candidate.category = ANY(ARRAY['animal_keeping_and_production','slaughter','processing_and_preparation','research_and_animal_use','other_regulated_premises','unclassified']::text[])
       THEN candidate.category ELSE 'unclassified' END) AS taxonomy_display_category
, COALESCE((
    SELECT array_agg(DISTINCT a.primary_key ORDER BY a.primary_key)
    FROM real_preview.candidate_taxonomy_assignment_sets s
    JOIN real_preview.candidate_taxonomy_assignments a USING (assignment_set_id)
    WHERE s.candidate_id=candidate.candidate_id AND s.taxonomy_version='uec-taxonomy-v1'
      AND NOT EXISTS (SELECT 1 FROM real_preview.candidate_taxonomy_assignment_sets newer
        WHERE newer.candidate_id=s.candidate_id AND newer.taxonomy_version=s.taxonomy_version
          AND (newer.created_at,newer.assignment_set_id)>(s.created_at,s.assignment_set_id))
  ), CASE WHEN candidate.category = ANY(ARRAY['animal_keeping_and_production','slaughter','processing_and_preparation','research_and_animal_use','other_regulated_premises','unclassified']::text[])
       THEN ARRAY[candidate.category] ELSE ARRAY['unclassified']::text[] END) AS taxonomy_primary_categories
, COALESCE((
    SELECT jsonb_agg(DISTINCT jsonb_build_object('key',a.leaf_key,'label',COALESCE(a.leaf_label,a.leaf_key)))
    FROM real_preview.candidate_taxonomy_assignment_sets s
    JOIN real_preview.candidate_taxonomy_assignments a USING (assignment_set_id)
    WHERE s.candidate_id=candidate.candidate_id AND s.taxonomy_version='uec-taxonomy-v1'
      AND a.leaf_key IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM real_preview.candidate_taxonomy_assignment_sets newer
        WHERE newer.candidate_id=s.candidate_id AND newer.taxonomy_version=s.taxonomy_version
          AND (newer.created_at,newer.assignment_set_id)>(s.created_at,s.assignment_set_id))
  ), '[]'::jsonb)::text AS taxonomy_leaf_activities_json
, COALESCE((
    SELECT jsonb_agg(jsonb_build_object('primary_key',a.primary_key,'leaf_key',a.leaf_key,'leaf_label',a.leaf_label,
      'source_code_reference',a.source_code_reference,'source_label_reference',a.source_label_reference,
      'source_code',a.source_code,'source_label',a.source_label,'method',a.mapping_method,
      'status',a.mapping_status,'taxonomy_version',s.taxonomy_version,
      'crosswalk_version',s.crosswalk_version,'ruleset_version',s.ruleset_version)
      ORDER BY a.assignment_ordinal)
    FROM real_preview.candidate_taxonomy_assignment_sets s
    JOIN real_preview.candidate_taxonomy_assignments a USING (assignment_set_id)
    WHERE s.candidate_id=candidate.candidate_id AND s.taxonomy_version='uec-taxonomy-v1'
      AND NOT EXISTS (SELECT 1 FROM real_preview.candidate_taxonomy_assignment_sets newer
        WHERE newer.candidate_id=s.candidate_id AND newer.taxonomy_version=s.taxonomy_version
          AND (newer.created_at,newer.assignment_set_id)>(s.created_at,s.assignment_set_id))
  ), '[]'::jsonb)::text AS taxonomy_assignments_json
"#;

/// Resolves a deliberately opaque administrative-reference key emitted by the
/// MVT projection.  The key is only meaningful to this private preview
/// endpoint; the tile continues to carry no member payload.
#[derive(Deserialize)]
pub struct RealPreviewReferenceParams {
    pub cursor: Option<uuid::Uuid>,
    pub limit: Option<i64>,
    pub source_id: Option<String>,
}

fn real_preview_response(status: StatusCode, body: Value) -> Response<axum::body::Body> {
    let mut response = (status, Json(body)).into_response();
    response.headers_mut().insert(
        axum::http::header::CACHE_CONTROL,
        HeaderValue::from_static("no-store"),
    );
    response
}

fn real_preview_tile_response(status: StatusCode, bytes: Vec<u8>) -> Response<axum::body::Body> {
    Response::builder()
        .status(status)
        .header(axum::http::header::CONTENT_TYPE, "application/vnd.mapbox-vector-tile")
        .header(axum::http::header::CACHE_CONTROL, "no-store")
        .body(axum::body::Body::from(bytes))
        .expect("a static private-preview tile response is valid")
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

fn real_preview_https_url(value: Option<String>) -> Option<String> {
    let value = value?;
    if value.len() > 2048 || value.chars().any(char::is_control) {
        return None;
    }
    let uri = value.parse::<axum::http::Uri>().ok()?;
    let authority = uri.authority()?;
    if uri.scheme_str() != Some("https")
        || authority.host().is_empty()
        || authority.as_str().contains('@')
    {
        return None;
    }
    Some(value)
}

fn real_preview_candidate(row: &tokio_postgres::Row) -> Value {
    let stored_kind: String = row.get("location_class");
    let stored_latitude: Option<f64> = row.get("latitude");
    let stored_longitude: Option<f64> = row.get("longitude");
    let city: Option<String> = row.get("city");
    let postal_code: Option<String> = row.get("postal_code");
    let display_latitude: Option<f64> = row.get("display_latitude");
    let display_longitude: Option<f64> = row.get("display_longitude");
    let display_geometry_source: Option<String> = row.get("display_geometry_source");
    let (kind, latitude, longitude) = safe_real_preview_location(
        &stored_kind,
        city.as_deref()
            .is_some_and(|value| !value.trim().is_empty()),
        postal_code
            .as_deref()
            .is_some_and(|value| !value.trim().is_empty()),
        stored_latitude,
        stored_longitude,
    );
    let is_city_reference = kind == "city_postal"
        && display_geometry_source.is_some()
        && safe_real_preview_location("numeric_source_coordinate", false, false, display_latitude, display_longitude).1.is_some();
    let reference_disclosure = is_city_reference
        .then(|| real_preview_reference_disclosure(display_geometry_source.as_deref()));
    let candidate_id: uuid::Uuid = row.get("candidate_id");
    json!({
        "candidate_id": candidate_id,
        "display_name": row.get::<_, Option<String>>("display_name"),
        "activity_label": row.get::<_, Option<String>>("activity_label"),
        "category": row.get::<_, Option<String>>("category"),
        "activity_categories": row.get::<_, Vec<String>>("activity_categories"),
        "source_activity_codes": row.get::<_, Vec<String>>("source_activity_codes"),
        "source_activity_labels": row.get::<_, Vec<String>>("source_activity_labels"),
        "activity_mapping_status": row.get::<_, String>("activity_mapping_status"),
        "taxonomy_display_category": row.get::<_, String>("taxonomy_display_category"),
        "taxonomy_primary_categories": row.get::<_, Vec<String>>("taxonomy_primary_categories"),
        "taxonomy_leaf_activities": serde_json::from_str(row.get::<_, String>("taxonomy_leaf_activities_json").as_str()).unwrap_or_else(|_| json!([])),
        "taxonomy_assignments": serde_json::from_str(row.get::<_, String>("taxonomy_assignments_json").as_str()).unwrap_or_else(|_| json!([])),
        "classification_ruleset_version": row.get::<_, Option<String>>("classification_ruleset_version"),
        "activity_source": row.get::<_, Option<String>>("activity_source"),
        "source_name": row.get::<_, Option<String>>("source_name"),
        "source_record_id": candidate_id,
        "source_url": real_preview_https_url(row.get::<_, Option<String>>("source_url")),
        "source_record_url": real_preview_https_url(row.get::<_, Option<String>>("source_record_url")),
        "retrieved_at": row.get::<_, chrono::DateTime<chrono::Utc>>("retrieved_at"),
        "observed_at": row.get::<_, Option<chrono::DateTime<chrono::Utc>>>("observed_at"),
        "evidence_summary": row.get::<_, Option<String>>("evidence_summary"),
        "source_id": row.get::<_, String>("source_id"),
        "location_class": kind,
        "display_precision": if kind == "numeric_source_coordinate" {
            real_preview_coordinate_precision(
                row.get::<_, String>("source_id").as_str(),
                row.get::<_, Option<String>>("coordinate_precision").as_deref(),
            )
        } else if let Some((display_precision, _, _)) = reference_disclosure { display_precision } else { "city_postal_coarse" },
        "country_code": row.get::<_, Option<String>>("country_code"),
        "default_map_scope": row.get::<_, bool>("default_map_scope"),
        "map_scope_reason": row.get::<_, Option<String>>("map_scope_reason"),
        "city": city,
        "postal_code": postal_code,
        "latitude": if is_city_reference { display_latitude } else { latitude },
        "longitude": if is_city_reference { display_longitude } else { longitude },
        "coordinate_precision": if let Some((_, coordinate_precision, _)) = reference_disclosure { Some(coordinate_precision.to_string()) } else if stored_kind == "numeric_source_coordinate" && kind != stored_kind { None::<String> } else { row.get::<_, Option<String>>("coordinate_precision") },
        "coordinate_provenance": if is_city_reference { display_geometry_source.clone() } else { None::<String> },
        "coordinate_review_status": if let Some((_, _, review_status)) = reference_disclosure { review_status } else if kind == "numeric_source_coordinate" { "pending_human_privacy_review" } else { "coarse_non_point" },
        "factual_review_status": "not_reviewed",
        "privacy_screening_status": "pending",
        "project_approval": false,
        "publication_status": "not_published",
        "preview_label": if is_city_reference { "Approximate city location — not a facility point; private preview only" }
            else if row.get::<_, String>("source_id") == "us.fsis" && row.get::<_, Option<String>>("coordinate_precision").as_deref() == Some("source-provided") { "FSIS source-provided coordinate — precision unverified; private rehearsal only; not approved or published" }
            else { "Private real V2 candidate — not project-approved or published" }
    })
}

fn real_preview_coordinate_precision(source_id: &str, precision: Option<&str>) -> &'static str {
    match (source_id, precision) {
        ("us.fsis", Some("source-provided")) => "source_provided_unverified",
        (_, Some("numeric" | "exact" | "source_numeric" | "source_coordinates" | "facility_coordinate")) => "source_numeric_pending_review",
        (_, Some("source-provided")) => "approximate_source_provided_pending_review",
        _ => "approximate_source_precision_unknown_pending_review",
    }
}

fn real_preview_reference_disclosure(source: Option<&str>) -> (&'static str, &'static str, &'static str) {
    if source.is_some_and(|value| value.contains("approximate locality reference; not facility coordinates")) {
        ("locality_reference_coarse", "locality_reference_coarse", "locality_reference_not_facility_or_centroid")
    } else {
        ("city_reference_approximate", "administrative-reference-centre-approximate", "approximate_city_location_not_facility_point")
    }
}

const REAL_PREVIEW_LATEST_SNAPSHOT: &str = "candidate.snapshot_sha256 = COALESCE((SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run WHERE run.source_id=candidate.source_id ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),(SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest WHERE manifest.source_id=candidate.source_id ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1))";

fn safe_real_preview_location(
    stored_kind: &str,
    has_city: bool,
    has_postal: bool,
    latitude: Option<f64>,
    longitude: Option<f64>,
) -> (String, Option<f64>, Option<f64>) {
    let usable_numeric = latitude.zip(longitude).is_some_and(|(lat, lon)| {
        lat.is_finite()
            && lon.is_finite()
            && (-90.0..=90.0).contains(&lat)
            && (-180.0..=180.0).contains(&lon)
            && (lat != 0.0 || lon != 0.0)
    });
    match (stored_kind, usable_numeric) {
        ("numeric_source_coordinate", true) => (stored_kind.to_owned(), latitude, longitude),
        ("numeric_source_coordinate", false) if has_city || has_postal => {
            ("city_postal".into(), None, None)
        }
        ("numeric_source_coordinate", false) => ("unmapped_private_observation".into(), None, None),
        ("city_postal", _) if has_city || has_postal => ("city_postal".into(), None, None),
        ("city_postal", _) => ("unmapped_private_observation".into(), None, None),
        _ => (stored_kind.to_owned(), None, None),
    }
}

fn valid_real_preview_tile_source(value: Option<&str>) -> bool {
    value.is_none_or(|source| {
        !source.is_empty()
            && source.len() <= 128
            && source
                .bytes()
                .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'-' | b'_'))
    })
}

fn parse_real_preview_taxonomy_categories(value: Option<&str>) -> Result<Option<Vec<String>>, ()> {
    let Some(value) = value.map(str::trim).filter(|value| !value.is_empty()) else {
        return Ok(None);
    };
    if value.len() > 512 {
        return Err(());
    }
    let mut categories = Vec::new();
    for category in value.split(',').map(str::trim) {
        if !V2_TAXONOMY_PRIMARY_CATEGORIES.contains(&category) {
            return Err(());
        }
        if !categories.iter().any(|existing| existing == category) {
            categories.push(category.to_string());
        }
    }
    if categories.is_empty() || categories.len() > V2_TAXONOMY_PRIMARY_CATEGORIES.len() {
        return Err(());
    }
    Ok(Some(categories))
}

fn valid_real_preview_cluster_cutoff(value: f64) -> bool {
    value.is_finite() && (4.0..=14.0).contains(&value) && (value * 2.0).fract() == 0.0
}

fn valid_real_preview_reference_key(value: &str) -> bool {
    value.len() == 32 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

/// Screen-scale divisor for the organic low-zoom density radius. It controls
/// cluster size without partitioning points into visible grid cells.
const REAL_PREVIEW_CLUSTER_RADIUS_DIVISOR: f64 = 8.0;

/// A development-only, lightweight MVT projection for the local private
/// preview.  It deliberately contains neither candidate display fields nor
/// source payload. At low zooms every placeable record contributes to one
/// deterministic WebMercator hierarchy, including administrative references.
/// Once that hierarchy resolves, those references remain labelled aggregates
/// rather than being silently promoted to facility points.
pub async fn get_real_preview_map_tile_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Path((z, x, y)): Path<(u8, u32, u32)>,
    Query(params): Query<RealPreviewTileParams>,
) -> Response<axum::body::Body> {
    if let Err(response) = real_preview_authorized(&state, &headers) {
        return response;
    }
    // z=14 is intentionally the endpoint ceiling.  Above it MapLibre can
    // overzoom the last tile while a selected candidate obtains its complete
    // detail from the existing detail route.
    if z > 14 || x >= (1_u32 << z) || y >= (1_u32 << z)
        || !valid_real_preview_tile_source(params.source_id.as_deref())
        || params.cluster_cutoff.is_some_and(|cutoff| !valid_real_preview_cluster_cutoff(cutoff))
    {
        return real_preview_error(
            StatusCode::BAD_REQUEST,
            "invalid_map_tile",
            "tile coordinates or source filter are invalid",
        );
    }
    let Some(pool) = state.database else {
        return real_preview_unavailable();
    };
    let Ok(client) = pool.get().await else {
        return real_preview_unavailable();
    };

    // A tile is valid only for the newest source snapshot(s). Resolve that
    // small boundary before looking up bytes, so an import naturally selects a
    // fresh cache namespace without a cache-wide purge or mutable database
    // coordination. The boundary never leaves this process.
    let snapshot_boundary: String = match client
        .query_one(
            "WITH sources AS (SELECT source_id FROM real_preview.source_preview_runs UNION SELECT source_id FROM real_preview.source_manifests), latest AS (SELECT sources.source_id,COALESCE((SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run WHERE run.source_id=sources.source_id ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),(SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest WHERE manifest.source_id=sources.source_id ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1)) AS snapshot_sha256 FROM sources) SELECT COALESCE(string_agg(source_id || ':' || snapshot_sha256, ',' ORDER BY source_id), 'no-snapshots') FROM latest WHERE ($1::text IS NULL OR source_id=$1)",
            &[&params.source_id],
        )
        .await
    {
        Ok(row) => row.get(0),
        Err(_) => return real_preview_unavailable(),
    };
    let cache_key = RealPreviewMvtTileCacheKey {
        contract_version: REAL_PREVIEW_MVT_CONTRACT_VERSION,
        snapshot_boundary,
        source_id: params.source_id.clone(),
        cluster_cutoff_half_steps: (params.cluster_cutoff.unwrap_or(7.5) * 2.0) as u8,
        z,
        x,
        y,
    };
    if let Some(bytes) = REAL_PREVIEW_MVT_TILE_CACHE.get(&cache_key) {
        return real_preview_tile_response(StatusCode::OK, bytes.to_vec());
    }

    // The radius scales with the current MVT zoom, but low-zoom membership is
    // computed from the complete deterministically ordered source set below.
    // There are no tile-local partitions, so a cluster cannot split at a seam.
    let grid_size = 40_075_016.685_578_49_f64 / f64::from(1_u32 << z)
        / REAL_PREVIEW_CLUSTER_RADIUS_DIVISOR;
    let cluster_cutoff = params.cluster_cutoff.unwrap_or(7.5);
    let cluster_zoom = f64::from(z) < cluster_cutoff;
    let sql = r#"
WITH
-- Calculate the buffered geographic envelope before touching candidate
-- coordinates. This is intentionally a raw lon/lat range predicate: it lets
-- the existing partial B-tree map indexes discard the rest of the preview
-- corpus before PostGIS transforms or grid aggregation occur.
tile AS (
  SELECT bounds,
         ST_Transform(bounds, 4326) AS geographic_bounds,
         ST_Transform(ST_Expand(bounds, $5::double precision), 4326) AS buffered_geographic_bounds,
         (ST_XMin(ST_Transform(bounds, 4326)) - $5::double precision * 180.0 / (pi() * 6378137.0)) AS min_longitude,
         (ST_XMax(ST_Transform(bounds, 4326)) + $5::double precision * 180.0 / (pi() * 6378137.0)) AS max_longitude
  FROM (SELECT ST_TileEnvelope($1::integer, $2::integer, $3::integer) AS bounds) world_tile
),
sources AS (
  SELECT source_id FROM real_preview.source_preview_runs
  UNION
  SELECT source_id FROM real_preview.source_manifests
),
latest AS (
  SELECT sources.source_id,
         COALESCE(
           (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
            WHERE run.source_id = sources.source_id
            ORDER BY run.created_at DESC, run.run_id DESC LIMIT 1),
           (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
            WHERE manifest.source_id = sources.source_id
            ORDER BY manifest.retrieved_at DESC, manifest.snapshot_sha256 DESC LIMIT 1)
         ) AS snapshot_sha256
  FROM sources
),
coordinate_candidates AS (
  -- Keep the two coordinate representations separate. COALESCE in a single
  -- predicate prevents PostgreSQL from using either of the purpose-built map
  -- indexes and used to transform/group nearly every candidate for each tile.
  SELECT c.candidate_id, c.source_id, c.location_class, c.coordinate_precision,
         NULL::text AS display_geometry_source, c.longitude AS longitude, c.latitude AS latitude
  FROM real_preview.candidates c CROSS JOIN tile
  WHERE c.default_map_scope = true
    AND c.display_geometry_source IS NULL
    AND c.location_class = 'numeric_source_coordinate'
    AND c.latitude BETWEEN -90 AND 90 AND c.longitude BETWEEN -180 AND 180
    AND (c.latitude <> 0 OR c.longitude <> 0)
    AND ($6::boolean OR (
      c.longitude BETWEEN GREATEST(tile.min_longitude, -180.0) AND LEAST(tile.max_longitude, 180.0)
      OR (tile.min_longitude < -180.0 AND c.longitude BETWEEN tile.min_longitude + 360.0 AND 180.0)
      OR (tile.max_longitude > 180.0 AND c.longitude BETWEEN -180.0 AND tile.max_longitude - 360.0)
    ))
    AND ($6::boolean OR c.latitude BETWEEN ST_YMin(tile.buffered_geographic_bounds) AND ST_YMax(tile.buffered_geographic_bounds))
    AND (c.source_id, c.snapshot_sha256) IN (SELECT source_id, snapshot_sha256 FROM latest)
    AND ($4::text IS NULL OR c.source_id = $4)
  UNION ALL
  SELECT c.candidate_id, c.source_id, c.location_class, c.coordinate_precision,
         c.display_geometry_source, c.display_longitude AS longitude, c.display_latitude AS latitude
  FROM real_preview.candidates c CROSS JOIN tile
  WHERE c.default_map_scope = true
    AND c.display_geometry_source IS NOT NULL
    AND c.display_latitude BETWEEN -90 AND 90 AND c.display_longitude BETWEEN -180 AND 180
    AND (c.display_latitude <> 0 OR c.display_longitude <> 0)
    AND ($6::boolean OR (
      c.display_longitude BETWEEN GREATEST(tile.min_longitude, -180.0) AND LEAST(tile.max_longitude, 180.0)
      OR (tile.min_longitude < -180.0 AND c.display_longitude BETWEEN tile.min_longitude + 360.0 AND 180.0)
      OR (tile.max_longitude > 180.0 AND c.display_longitude BETWEEN -180.0 AND tile.max_longitude - 360.0)
    ))
    AND ($6::boolean OR c.display_latitude BETWEEN ST_YMin(tile.buffered_geographic_bounds) AND ST_YMax(tile.buffered_geographic_bounds))
    AND (c.source_id, c.snapshot_sha256) IN (SELECT source_id, snapshot_sha256 FROM latest)
    AND ($4::text IS NULL OR c.source_id = $4)
),
placeable AS (
  SELECT candidate_id, source_id, location_class, coordinate_precision,
         display_geometry_source,
         ST_Transform(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326), 3857) AS geom
  FROM coordinate_candidates
),
numeric AS (
  SELECT * FROM placeable WHERE display_geometry_source IS NULL
),
reference_points AS (
  SELECT md5('city-reference:' || ST_X(geom)::text || ':' || ST_Y(geom)::text) AS feature_key,
         count(*)::integer AS count,
         CASE WHEN bool_and(display_geometry_source LIKE '%approximate locality reference; not facility coordinates%')
              THEN 'locality_reference_coarse'::text
              ELSE 'city_reference_approximate'::text END AS precision,
         ST_Centroid(ST_Collect(geom)) AS geom
  FROM placeable
  WHERE display_geometry_source IS NOT NULL
  GROUP BY ST_X(geom), ST_Y(geom)
),
reference_features AS (
  SELECT feature_key, NULL::text AS parent_key, 'city_reference'::text AS kind,
         count, precision, 14::integer AS next_zoom, geom
  FROM reference_points
),
numeric_features AS (
  SELECT candidate_id::text AS feature_key,
         NULL::text AS parent_key,
         'source_coordinate'::text AS kind,
         1::integer AS count,
         CASE WHEN source_id = 'us.fsis' AND coordinate_precision = 'source-provided' THEN 'source_provided_unverified'
              WHEN coordinate_precision IN ('numeric','exact','source_numeric','source_coordinates','facility_coordinate') THEN 'source_numeric_pending_review'
              WHEN coordinate_precision = 'source-provided' THEN 'approximate_source_provided_pending_review'
              ELSE 'approximate_source_precision_unknown_pending_review' END AS precision,
         14::integer AS next_zoom,
         geom
  FROM numeric WHERE NOT $6::boolean
),
features AS (
  SELECT * FROM numeric_features
  UNION ALL
  SELECT * FROM reference_features
),
tile_features AS (
   SELECT feature_key, parent_key, kind, count, precision, next_zoom,
          -- A 512-unit MVT buffer duplicates edge symbols into neighbour tiles.
          -- It pairs with MapLibre's tile fade so a pan never exposes a blank seam.
          ST_AsMVTGeom(geom, tile.bounds, 4096, 512, true) AS geom
  FROM features CROSS JOIN tile
  WHERE geom && ST_Expand(tile.bounds, $5::double precision)
)
SELECT COALESCE(ST_AsMVT(tile_features, 'uec_preview', 4096, 'geom'), ''::bytea) FROM tile_features
"#;
    let row = if cluster_zoom {
        let hierarchy_key = RealPreviewHierarchyCacheKey {
            contract_version: REAL_PREVIEW_MVT_CONTRACT_VERSION,
            snapshot_boundary: cache_key.snapshot_boundary.clone(),
            source_id: params.source_id.clone(),
            cluster_cutoff_half_steps: cache_key.cluster_cutoff_half_steps,
            z,
        };
        let Some(features) = get_or_build_real_preview_cluster_hierarchy(
            &client,
            hierarchy_key,
            grid_size * 0.12,
        )
        .await
        else {
            return real_preview_unavailable();
        };
        let tile_features = real_preview_hierarchy_tile_features(features.as_ref(), z, x, y);
        let Ok(feature_payload) = serde_json::to_string(&tile_features) else {
            return real_preview_unavailable();
        };
        client
            .query_one(
                r#"
WITH tile AS (
  SELECT ST_TileEnvelope($1::integer,$2::integer,$3::integer) AS bounds
), features AS (
  SELECT feature_key,parent_key,kind,count,precision,next_zoom,
         ST_SetSRID(ST_MakePoint(x,y),3857) AS geom
  FROM jsonb_to_recordset($4::text::jsonb) AS f(
    feature_key text,parent_key text,kind text,count integer,precision text,
    next_zoom integer,x double precision,y double precision
  )
), tile_features AS (
  SELECT feature_key,parent_key,kind,count,precision,next_zoom,
         ST_AsMVTGeom(geom,tile.bounds,4096,512,true) AS geom
  FROM features CROSS JOIN tile
  WHERE geom && ST_Expand(tile.bounds,$5::double precision)
)
SELECT COALESCE(ST_AsMVT(tile_features,'uec_preview',4096,'geom'),''::bytea)
FROM tile_features
"#,
                &[&(i32::from(z)), &(x as i32), &(y as i32), &feature_payload, &grid_size],
            )
            .await
    } else {
        client
            .query_one(
                sql,
                &[
                    &(i32::from(z)),
                    &(x as i32),
                    &(y as i32),
                    &params.source_id,
                    &grid_size,
                    &cluster_zoom,
                ],
            )
            .await
    };
    let row = match row {
        Ok(row) => row,
        Err(_) => return real_preview_unavailable(),
    };
    let bytes = REAL_PREVIEW_MVT_TILE_CACHE.insert(cache_key, row.get::<_, Vec<u8>>(0));
    real_preview_tile_response(StatusCode::OK, bytes.to_vec())
}

/// Returns the bounded current-snapshot map projection in one response rather
/// than requiring the browser to traverse every private candidate page. The
/// projection is intentionally an allowlist: key, kind, precision, source,
/// coordinates, and represented weight only.
pub async fn get_real_preview_map_feed_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Query(params): Query<RealPreviewMapFeedParams>,
) -> Response<axum::body::Body> {
    if let Err(response) = real_preview_authorized(&state, &headers) {
        return response;
    }
    if !valid_real_preview_tile_source(params.source_id.as_deref()) {
        return real_preview_error(
            StatusCode::BAD_REQUEST,
            "invalid_map_feed",
            "map feed source filter is invalid",
        );
    }
    let Some(pool) = state.database else {
        return real_preview_unavailable();
    };
    let Ok(client) = pool.get().await else {
        return real_preview_unavailable();
    };
    let snapshot_boundary: String = match client.query_one(
        "WITH sources AS (SELECT source_id FROM real_preview.source_preview_runs UNION SELECT source_id FROM real_preview.source_manifests), latest AS (SELECT sources.source_id,COALESCE((SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run WHERE run.source_id=sources.source_id ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),(SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest WHERE manifest.source_id=sources.source_id ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1)) AS snapshot_sha256 FROM sources) SELECT COALESCE(string_agg(source_id || ':' || snapshot_sha256, ',' ORDER BY source_id), 'no-snapshots') FROM latest",
        &[],
    ).await {
        Ok(row) => row.get(0),
        Err(_) => return real_preview_unavailable(),
    };
    let snapshot_id = format!("{:x}", Sha256::digest(snapshot_boundary.as_bytes()));

    // Keep one row per numeric coordinate and group coarse references by both
    // the stable geometry key and source_id. Fetch one beyond the bound so the
    // endpoint can fail closed instead of silently dropping represented rows.
    let rows = match client.query(
        r#"
WITH sources AS (
  SELECT source_id FROM real_preview.source_preview_runs
  UNION
  SELECT source_id FROM real_preview.source_manifests
), latest AS (
  SELECT sources.source_id,
         COALESCE(
           (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
            WHERE run.source_id=sources.source_id
            ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),
           (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
            WHERE manifest.source_id=sources.source_id
            ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1)
         ) AS snapshot_sha256
  FROM sources
), current_map AS (
  SELECT candidate.candidate_id, candidate.source_id,
         candidate.location_class, candidate.coordinate_precision,
         candidate.display_geometry_source,
         COALESCE((SELECT s.display_category
           FROM real_preview.candidate_taxonomy_assignment_sets s
           WHERE s.candidate_id=candidate.candidate_id AND s.taxonomy_version='uec-taxonomy-v1'
           ORDER BY s.created_at DESC,s.assignment_set_id DESC LIMIT 1),
           CASE WHEN candidate.category=ANY(ARRAY['animal_keeping_and_production','slaughter','processing_and_preparation','research_and_animal_use','other_regulated_premises','unclassified']::text[])
             THEN candidate.category ELSE 'unclassified' END) AS category_key,
         COALESCE((SELECT array_agg(DISTINCT a.primary_key ORDER BY a.primary_key)
           FROM real_preview.candidate_taxonomy_assignment_sets s
           JOIN real_preview.candidate_taxonomy_assignments a USING(assignment_set_id)
           WHERE s.candidate_id=candidate.candidate_id AND s.taxonomy_version='uec-taxonomy-v1'
             AND NOT EXISTS (SELECT 1 FROM real_preview.candidate_taxonomy_assignment_sets newer
               WHERE newer.candidate_id=s.candidate_id AND newer.taxonomy_version=s.taxonomy_version
                 AND (newer.created_at,newer.assignment_set_id)>(s.created_at,s.assignment_set_id))),
           CASE WHEN candidate.category=ANY(ARRAY['animal_keeping_and_production','slaughter','processing_and_preparation','research_and_animal_use','other_regulated_premises','unclassified']::text[])
             THEN ARRAY[candidate.category] ELSE ARRAY['unclassified']::text[] END) AS category_keys,
         CASE WHEN candidate.display_geometry_source IS NULL THEN candidate.longitude
              ELSE candidate.display_longitude END AS longitude,
         CASE WHEN candidate.display_geometry_source IS NULL THEN candidate.latitude
              ELSE candidate.display_latitude END AS latitude
  FROM real_preview.candidates candidate
  JOIN real_preview.source_manifests manifest
    ON manifest.source_id=candidate.source_id
   AND manifest.snapshot_sha256=candidate.snapshot_sha256
  WHERE candidate.default_map_scope=true
    AND (candidate.source_id,candidate.snapshot_sha256) IN
        (SELECT source_id,snapshot_sha256 FROM latest)
    AND ($1::text IS NULL OR candidate.source_id=$1)
    AND ((candidate.display_geometry_source IS NULL
          AND candidate.location_class='numeric_source_coordinate'
          AND candidate.latitude BETWEEN -90 AND 90
          AND candidate.longitude BETWEEN -180 AND 180
          AND (candidate.latitude<>0 OR candidate.longitude<>0))
      OR (candidate.display_geometry_source IS NOT NULL
          AND candidate.display_latitude BETWEEN -90 AND 90
          AND candidate.display_longitude BETWEEN -180 AND 180
          AND (candidate.display_latitude<>0 OR candidate.display_longitude<>0)))
), projected AS (
  SELECT candidate_id::text AS feature_key,
         'source_coordinate'::text AS kind,
         CASE WHEN source_id = 'us.fsis' AND coordinate_precision = 'source-provided' THEN 'source_provided_unverified'
              WHEN coordinate_precision IN ('numeric','exact','source_numeric','source_coordinates','facility_coordinate') THEN 'source_numeric_pending_review'
              WHEN coordinate_precision='source-provided' THEN 'approximate_source_provided_pending_review'
              ELSE 'approximate_source_precision_unknown_pending_review' END AS precision,
         source_id, latitude, longitude, 1::bigint AS weight,
         category_key, category_keys
  FROM current_map WHERE display_geometry_source IS NULL
  UNION ALL
  SELECT md5('city-reference:' || ST_X(geom)::text || ':' || ST_Y(geom)::text) AS feature_key,
         'city_reference'::text AS kind,
         'city_reference_approximate'::text AS precision,
         source_id,
         ST_Y(ST_Transform(geom,4326)) AS latitude,
         ST_X(ST_Transform(geom,4326)) AS longitude,
         count(*)::bigint AS weight,
         'unclassified'::text AS category_key,
         ARRAY['unclassified']::text[] AS category_keys
  FROM (
    SELECT source_id,
           ST_Transform(ST_SetSRID(ST_MakePoint(longitude,latitude),4326),3857) AS geom
    FROM current_map WHERE display_geometry_source IS NOT NULL
  ) reference_geometries
  GROUP BY source_id, geom
)
SELECT feature_key,kind,precision,source_id,latitude,longitude,weight,category_key,category_keys
FROM projected
ORDER BY source_id,kind,feature_key
LIMIT $2
"#,
        &[&params.source_id, &(REAL_PREVIEW_MAP_FEED_MAX_FEATURES + 1)],
    ).await {
        Ok(rows) => rows,
        Err(_) => return real_preview_unavailable(),
    };
    if rows.len() as i64 > REAL_PREVIEW_MAP_FEED_MAX_FEATURES {
        return real_preview_error(
            StatusCode::PAYLOAD_TOO_LARGE,
            "map_feed_too_large",
            "map feed exceeds the bounded feature limit",
        );
    }
    let data: Vec<Value> = rows.iter().map(|row| json!({
        "key": row.get::<_, String>(0),
        "kind": row.get::<_, String>(1),
        "precision": row.get::<_, String>(2),
        "source_id": row.get::<_, String>(3),
        "latitude": row.get::<_, f64>(4),
        "longitude": row.get::<_, f64>(5),
        "weight": row.get::<_, i64>(6),
        "category_key": row.get::<_, String>(7),
        "category_keys": row.get::<_, Vec<String>>(8),
    })).collect();
    let total_weight: i64 = rows.iter().map(|row| row.get::<_, i64>(6)).sum();
    let mut source_weights = std::collections::BTreeMap::<String, i64>::new();
    for row in &rows {
        *source_weights.entry(row.get::<_, String>(3)).or_default() += row.get::<_, i64>(6);
    }
    let mut response = real_preview_response(StatusCode::OK, json!({
        "api_version":"real-preview-v1",
        "data":data,
        "meta":{
            "bounded":true,
            "private_preview":true,
            "scope":"default_map_scope",
            "zoom_max":14,
            "feature_limit":REAL_PREVIEW_MAP_FEED_MAX_FEATURES,
            "snapshot_id":snapshot_id,
            "total_weight":total_weight,
            "source_weights":source_weights
        }
    }));
    response.headers_mut().insert(
        axum::http::header::VARY,
        HeaderValue::from_static("accept-encoding"),
    );
    response
}

/// Pages the real candidates represented by one administrative reference MVT
/// feature.  This is intentionally separate from the tile projection: a tile
/// has only an opaque key/count/geometry, while this authenticated endpoint
/// returns the normal private-preview candidate envelope when the user asks to
/// inspect that reference.
pub async fn get_real_preview_reference_handler(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Path(reference_key): Path<String>,
    Query(params): Query<RealPreviewReferenceParams>,
) -> Response<axum::body::Body> {
    if let Err(response) = real_preview_authorized(&state, &headers) {
        return response;
    }
    let limit = params.limit.unwrap_or(100);
    if !valid_real_preview_reference_key(&reference_key)
        || !(1..=200).contains(&limit)
        || !valid_real_preview_tile_source(params.source_id.as_deref())
    {
        return real_preview_error(
            StatusCode::BAD_REQUEST,
            "invalid_map_reference",
            "reference key, page, or source filter is invalid",
        );
    }
    let Some(pool) = state.database else {
        return real_preview_unavailable();
    };
    let Ok(client) = pool.get().await else {
        return real_preview_unavailable();
    };
    let query_limit = limit + 1;
    // The expression deliberately mirrors `reference_features` in the MVT
    // query.  It only resolves administrative display geometries and retains
    // the current-snapshot/source boundaries used by every preview endpoint.
    let rows = match client.query(
        &format!("WITH sources AS (SELECT source_id FROM real_preview.source_preview_runs UNION SELECT source_id FROM real_preview.source_manifests), latest AS (SELECT sources.source_id,COALESCE((SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run WHERE run.source_id=sources.source_id ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),(SELECT source_manifest.snapshot_sha256 FROM real_preview.source_manifests source_manifest WHERE source_manifest.source_id=sources.source_id ORDER BY source_manifest.retrieved_at DESC,source_manifest.snapshot_sha256 DESC LIMIT 1)) AS snapshot_sha256 FROM sources) SELECT candidate.*,manifest.source_url,manifest.retrieved_at {} FROM real_preview.candidates candidate JOIN real_preview.source_manifests manifest ON manifest.snapshot_sha256=candidate.snapshot_sha256 AND manifest.source_id=candidate.source_id WHERE candidate.default_map_scope=true AND candidate.display_geometry_source IS NOT NULL AND candidate.display_latitude BETWEEN -90 AND 90 AND candidate.display_longitude BETWEEN -180 AND 180 AND (candidate.display_latitude<>0 OR candidate.display_longitude<>0) AND md5('city-reference:' || ST_X(ST_Transform(ST_SetSRID(ST_MakePoint(candidate.display_longitude,candidate.display_latitude),4326),3857))::text || ':' || ST_Y(ST_Transform(ST_SetSRID(ST_MakePoint(candidate.display_longitude,candidate.display_latitude),4326),3857))::text)=$1 AND (candidate.source_id,candidate.snapshot_sha256) IN (SELECT source_id,snapshot_sha256 FROM latest) AND ($2::uuid IS NULL OR candidate.candidate_id>$2) AND ($4::text IS NULL OR candidate.source_id=$4) ORDER BY candidate.candidate_id LIMIT $3", REAL_PREVIEW_TAXONOMY_SELECT_SQL),
        &[&reference_key, &params.cursor, &query_limit, &params.source_id],
    ).await {
        Ok(rows) => rows,
        Err(_) => return real_preview_unavailable(),
    };
    let has_next = rows.len() as i64 > limit;
    let data: Vec<Value> = rows.iter().take(limit as usize).map(real_preview_candidate).collect();
    let next = has_next.then(|| rows[(limit - 1) as usize].get::<_, uuid::Uuid>("candidate_id"));
    real_preview_response(
        StatusCode::OK,
        json!({"api_version":"real-preview-v1","data":data,"meta":{"bounded":true,"next_cursor":next,"private_preview":true,"reference_key":reference_key}}),
    )
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
    let category_keys = match parse_real_preview_taxonomy_categories(params.category_keys.as_deref()) {
        Ok(keys) => keys,
        Err(()) => return real_preview_error(
            StatusCode::BAD_REQUEST,
            "invalid_category_keys",
            "category_keys contains an unsupported taxonomy category",
        ),
    };
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
    let query_limit = limit + 1;
    let rows = match client.query(
        &format!("SELECT candidate.*,manifest.source_url,manifest.retrieved_at {} FROM real_preview.candidates candidate JOIN real_preview.source_manifests manifest ON manifest.snapshot_sha256=candidate.snapshot_sha256 AND manifest.source_id=candidate.source_id WHERE {} AND ($1::uuid IS NULL OR candidate.candidate_id > $1) AND ($2='' OR COALESCE(candidate.display_name,'') ILIKE '%' || $2 || '%' OR COALESCE(candidate.activity_label,'') ILIKE '%' || $2 || '%' OR COALESCE(candidate.activity_source,'') ILIKE '%' || $2 || '%' OR COALESCE(candidate.source_name,'') ILIKE '%' || $2 || '%' OR candidate.source_id ILIKE '%' || $2 || '%' OR COALESCE(candidate.city,'') ILIKE '%' || $2 || '%' OR COALESCE(candidate.postal_code,'') ILIKE '%' || $2 || '%' OR EXISTS (SELECT 1 FROM real_preview.candidate_taxonomy_assignment_sets ts JOIN real_preview.candidate_taxonomy_assignments ta USING (assignment_set_id) WHERE ts.candidate_id=candidate.candidate_id AND ts.taxonomy_version='uec-taxonomy-v1' AND NOT EXISTS (SELECT 1 FROM real_preview.candidate_taxonomy_assignment_sets newer WHERE newer.candidate_id=ts.candidate_id AND newer.taxonomy_version=ts.taxonomy_version AND (newer.created_at,newer.assignment_set_id)>(ts.created_at,ts.assignment_set_id)) AND (COALESCE(ta.leaf_label,'') ILIKE '%' || $2 || '%' OR COALESCE(ta.source_label,'') ILIKE '%' || $2 || '%' OR COALESCE(ta.source_code,'') ILIKE '%' || $2 || '%')) ) AND ($4::text IS NULL OR candidate.source_id=$4) AND ($5::bool IS NULL OR candidate.default_map_scope=$5) AND ($6::text[] IS NULL OR EXISTS (SELECT 1 FROM real_preview.candidate_taxonomy_assignment_sets ts JOIN real_preview.candidate_taxonomy_assignments ta USING (assignment_set_id) WHERE ts.candidate_id=candidate.candidate_id AND ts.taxonomy_version='uec-taxonomy-v1' AND NOT EXISTS (SELECT 1 FROM real_preview.candidate_taxonomy_assignment_sets newer WHERE newer.candidate_id=ts.candidate_id AND newer.taxonomy_version=ts.taxonomy_version AND (newer.created_at,newer.assignment_set_id)>(ts.created_at,ts.assignment_set_id)) AND ta.primary_key=ANY($6)) OR (NOT EXISTS (SELECT 1 FROM real_preview.candidate_taxonomy_assignment_sets ts WHERE ts.candidate_id=candidate.candidate_id AND ts.taxonomy_version='uec-taxonomy-v1') AND (candidate.category=ANY($6) OR (candidate.category IS NULL AND 'unclassified'=ANY($6))))) ORDER BY candidate.candidate_id LIMIT $3", REAL_PREVIEW_TAXONOMY_SELECT_SQL, REAL_PREVIEW_LATEST_SNAPSHOT),
        &[&cursor, &query, &query_limit, &params.source_id, &params.default_map_scope, &category_keys],
    ).await { Ok(rows) => rows, Err(_) => return real_preview_unavailable() };
    let has_next = rows.len() as i64 > limit;
    let data: Vec<Value> = rows.iter().take(limit as usize).map(real_preview_candidate).collect();
    let next = has_next.then(|| rows[(limit - 1) as usize].get::<_, uuid::Uuid>("candidate_id"));
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
    let query_limit = limit + 1;
    let rows = match client.query(
        &format!("SELECT candidate.*,manifest.source_url,manifest.retrieved_at {} FROM real_preview.candidates candidate JOIN real_preview.source_manifests manifest ON manifest.snapshot_sha256=candidate.snapshot_sha256 AND manifest.source_id=candidate.source_id WHERE candidate.default_map_scope=true AND (((candidate.location_class='numeric_source_coordinate' AND candidate.latitude BETWEEN -90 AND 90 AND candidate.longitude BETWEEN -180 AND 180 AND (candidate.latitude<>0 OR candidate.longitude<>0)) OR (candidate.display_geometry_source IS NOT NULL AND candidate.display_latitude BETWEEN -90 AND 90 AND candidate.display_longitude BETWEEN -180 AND 180)) AND COALESCE(candidate.display_longitude,candidate.longitude) BETWEEN $1 AND $3 AND COALESCE(candidate.display_latitude,candidate.latitude) BETWEEN $2 AND $4) AND {} AND ($5::uuid IS NULL OR candidate.candidate_id > $5) AND ($7::text IS NULL OR candidate.source_id=$7) ORDER BY candidate.candidate_id LIMIT $6", REAL_PREVIEW_TAXONOMY_SELECT_SQL, REAL_PREVIEW_LATEST_SNAPSHOT),
        &[&params.west,&params.south,&params.east,&params.north,&params.cursor,&query_limit,&params.source_id],
    ).await { Ok(rows) => rows, Err(_) => return real_preview_unavailable() };
    let has_next = rows.len() as i64 > limit;
    let data: Vec<Value> = rows.iter().take(limit as usize).map(real_preview_candidate).collect();
    let next = has_next.then(|| rows[(limit - 1) as usize].get::<_, uuid::Uuid>("candidate_id"));
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
    let row = match client.query_opt(&format!("SELECT candidate.*,manifest.source_url,manifest.retrieved_at {} FROM real_preview.candidates candidate JOIN real_preview.source_manifests manifest ON manifest.snapshot_sha256=candidate.snapshot_sha256 AND manifest.source_id=candidate.source_id WHERE candidate.candidate_id=$1 AND {}", REAL_PREVIEW_TAXONOMY_SELECT_SQL, REAL_PREVIEW_LATEST_SNAPSHOT), &[&id]).await { Ok(row) => row, Err(_) => return real_preview_unavailable() };
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
    let rows = match client.query(&format!("SELECT candidate.source_id,CASE WHEN candidate.location_class='numeric_source_coordinate' AND NOT (candidate.latitude BETWEEN -90 AND 90 AND candidate.longitude BETWEEN -180 AND 180 AND (candidate.latitude<>0 OR candidate.longitude<>0)) THEN CASE WHEN NULLIF(BTRIM(candidate.city),'') IS NOT NULL OR NULLIF(BTRIM(candidate.postal_code),'') IS NOT NULL THEN 'city_postal' ELSE 'unmapped_private_observation' END ELSE candidate.location_class END AS safe_location_class,candidate.default_map_scope,count(*)::bigint FROM real_preview.candidates candidate JOIN real_preview.source_manifests manifest ON manifest.snapshot_sha256=candidate.snapshot_sha256 AND manifest.source_id=candidate.source_id WHERE {} GROUP BY candidate.source_id,safe_location_class,candidate.default_map_scope ORDER BY candidate.source_id,safe_location_class,candidate.default_map_scope", REAL_PREVIEW_LATEST_SNAPSHOT), &[]).await { Ok(rows) => rows, Err(_) => return real_preview_unavailable() };
    let data: Vec<Value> = rows.iter().map(|row| json!({"source_id":row.get::<_,String>(0),"location_class":row.get::<_,String>(1),"default_map_scope":row.get::<_,bool>(2),"count":row.get::<_,i64>(3)})).collect();
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
    let snapshot_boundary: String = match client.query_one(
        "WITH sources AS (SELECT source_id FROM real_preview.source_preview_runs UNION SELECT source_id FROM real_preview.source_manifests), latest AS (SELECT sources.source_id,COALESCE((SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run WHERE run.source_id=sources.source_id ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),(SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest WHERE manifest.source_id=sources.source_id ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1)) AS snapshot_sha256 FROM sources) SELECT COALESCE(string_agg(source_id || ':' || snapshot_sha256, ',' ORDER BY source_id), 'no-snapshots') FROM latest",
        &[],
    ).await {
        Ok(row) => row.get(0),
        Err(_) => return real_preview_unavailable(),
    };
    let snapshot_id = format!("{:x}", Sha256::digest(snapshot_boundary.as_bytes()));
    let runtime_rows = match client.query("SELECT DISTINCT ON (source_id) source_id,run_id FROM real_preview.source_preview_runs ORDER BY source_id,created_at DESC,run_id DESC", &[]).await { Ok(rows) => rows, Err(_) => return real_preview_unavailable() };
    let runtime_ledger = json!(runtime_rows.iter().map(|row| json!({"source_id":row.get::<_,String>(0),"run_id":row.get::<_,String>(1)})).collect::<Vec<_>>());
    let counts = match client.query_one(&format!("SELECT count(*)::bigint,count(*) FILTER (WHERE candidate.location_class='numeric_source_coordinate' AND candidate.latitude BETWEEN -90 AND 90 AND candidate.longitude BETWEEN -180 AND 180 AND (candidate.latitude<>0 OR candidate.longitude<>0))::bigint,count(*) FILTER (WHERE candidate.location_class='city_postal' OR (candidate.location_class='numeric_source_coordinate' AND NOT (candidate.latitude BETWEEN -90 AND 90 AND candidate.longitude BETWEEN -180 AND 180 AND (candidate.latitude<>0 OR candidate.longitude<>0)) AND (NULLIF(BTRIM(candidate.city),'') IS NOT NULL OR NULLIF(BTRIM(candidate.postal_code),'') IS NOT NULL)))::bigint,count(*) FILTER (WHERE candidate.location_class='unmapped_private_observation' OR (candidate.location_class='numeric_source_coordinate' AND NOT (candidate.latitude BETWEEN -90 AND 90 AND candidate.longitude BETWEEN -180 AND 180 AND (candidate.latitude<>0 OR candidate.longitude<>0)) AND NULLIF(BTRIM(candidate.city),'') IS NULL AND NULLIF(BTRIM(candidate.postal_code),'') IS NULL))::bigint,count(*) FILTER (WHERE candidate.default_map_scope)::bigint,count(*) FILTER (WHERE NOT candidate.default_map_scope)::bigint,count(*) FILTER (WHERE candidate.default_map_scope AND ((candidate.location_class='numeric_source_coordinate' AND candidate.latitude BETWEEN -90 AND 90 AND candidate.longitude BETWEEN -180 AND 180 AND (candidate.latitude<>0 OR candidate.longitude<>0)) OR candidate.display_latitude IS NOT NULL))::bigint,count(*) FILTER (WHERE candidate.default_map_scope AND candidate.location_class='city_postal' AND candidate.display_latitude IS NOT NULL)::bigint FROM real_preview.candidates candidate JOIN real_preview.source_manifests manifest ON manifest.snapshot_sha256=candidate.snapshot_sha256 AND manifest.source_id=candidate.source_id WHERE {}", REAL_PREVIEW_LATEST_SNAPSHOT), &[]).await { Ok(row) => row, Err(_) => return real_preview_unavailable() };
    real_preview_response(
        StatusCode::OK,
        json!({"api_version":"real-preview-v1","data":{"facility_candidate_count":counts.get::<_,i64>(0),"api_listable_count":counts.get::<_,i64>(0),"numeric_coordinate_count":counts.get::<_,i64>(1),"city_postal_count":counts.get::<_,i64>(2),"unmapped_candidate_count":counts.get::<_,i64>(3),"default_map_scope_candidate_count":counts.get::<_,i64>(4),"out_of_default_map_scope_candidate_count":counts.get::<_,i64>(5),"map_visible_count":counts.get::<_,i64>(6),"coarse_placeable_count":counts.get::<_,i64>(7)},"meta":{"private_preview":true,"snapshot_id":snapshot_id,"runtime_ledger":runtime_ledger}}),
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
const V2_TAXONOMY_PRIMARY_CATEGORIES: &[&str] = &[
    "animal_keeping_and_production",
    "slaughter",
    "processing_and_preparation",
    "research_and_animal_use",
    "other_regulated_premises",
    "unclassified",
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
    /// Comma-separated taxonomy primaries; multiple values use OR semantics.
    pub category_keys: Option<String>,
    pub source_type: Option<String>,
    pub profile: Option<String>,
    /// Pin every page of a discovery query to the manifest release currently displayed.
    pub release_id: Option<String>,
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
    pub taxonomy_display_category: String,
    pub taxonomy_primary_categories: Vec<String>,
    pub taxonomy_leaf_activities: Value,
    pub taxonomy_assignments: Value,
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
    let category_keys = match params.category_keys.as_deref() {
        None => None,
        Some(value) => {
            let mut keys = value.split(',').map(str::to_owned).collect::<Vec<_>>();
            keys.sort();
            keys.dedup();
            if keys.len() > V2_TAXONOMY_PRIMARY_CATEGORIES.len()
                || keys.iter().any(|key| !V2_TAXONOMY_PRIMARY_CATEGORIES.contains(&key.as_str()))
            {
                return v2_error(StatusCode::BAD_REQUEST, "invalid_category_keys", "category_keys contains an unsupported taxonomy category");
            }
            Some(keys)
        }
    };
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
    let release = transaction.query_opt("SELECT r.release_id, r.ruleset_version, r.created_at, r.profile, (model.release_id IS NOT NULL AND manifest.release_id IS NOT NULL) FROM uec.releases r LEFT JOIN uec.public_discovery_read_models model ON model.release_id=r.release_id LEFT JOIN uec.release_manifests manifest ON manifest.release_id=r.release_id AND manifest.manifest_sha256=model.manifest_sha256 WHERE r.status = 'promoted' AND r.test_only IS NOT TRUE AND r.profile = $1 AND ($2::text IS NULL OR r.release_id = $2) ORDER BY r.created_at DESC, r.release_id DESC LIMIT 1", &[&requested_profile, &params.release_id]).await;
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
        if params.release_id.is_some() {
            return v2_error(StatusCode::GONE, "release_unavailable", "displayed release is no longer eligible");
        }
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
               history.source_rights_status,
               COALESCE(taxonomy.display_category, 'unclassified'),
               COALESCE(taxonomy.primary_categories, ARRAY['unclassified']::text[]),
               COALESCE(taxonomy.leaf_activities, '[]'::jsonb)::text,
               COALESCE(taxonomy.assignments, '[]'::jsonb)::text
        FROM uec.map_facilities_public_discovery_read_model AS history
        LEFT JOIN LATERAL (
          SELECT min(s.display_category) AS display_category,
                 array_agg(DISTINCT a.primary_key ORDER BY a.primary_key) FILTER (WHERE a.primary_key IS NOT NULL) AS primary_categories,
                 COALESCE(jsonb_agg(DISTINCT jsonb_build_object('key', a.leaf_key, 'label', a.leaf_label)) FILTER (WHERE a.leaf_key IS NOT NULL AND a.leaf_label IS NOT NULL AND a.mapping_method IN ('direct','derived') AND a.mapping_status IN ('mapped','partial')), '[]'::jsonb) AS leaf_activities,
                 COALESCE(jsonb_agg(DISTINCT jsonb_build_object('primary_key',a.primary_key,'leaf_key',a.leaf_key,'leaf_label',a.leaf_label,'source_code_reference',a.source_code_reference,'source_label_reference',a.source_label_reference,'source_code',a.source_code,'source_label',a.source_label,'method',a.mapping_method,'status',a.mapping_status,'taxonomy_version',s.taxonomy_version,'crosswalk_version',s.crosswalk_version,'ruleset_version',s.ruleset_version)) FILTER (WHERE a.assignment_set_id IS NOT NULL), '[]'::jsonb) AS assignments
          FROM uec.map_facilities_public_discovery_read_model eligible
          JOIN uec.observation_taxonomy_assignment_sets s ON s.observation_id=eligible.observation_id AND s.taxonomy_version='uec-taxonomy-v1'
            AND NOT EXISTS (SELECT 1 FROM uec.observation_taxonomy_assignment_sets newer WHERE newer.observation_id=s.observation_id AND newer.taxonomy_version=s.taxonomy_version AND (newer.created_at,newer.assignment_set_id)>(s.created_at,s.assignment_set_id))
          LEFT JOIN uec.observation_taxonomy_assignments a ON a.assignment_set_id=s.assignment_set_id
          WHERE eligible.release_id=history.release_id AND eligible.facility_id=history.facility_id AND eligible.observation_id=history.observation_id
        ) taxonomy ON TRUE
        WHERE history.release_id = $1
          AND ($2::uuid IS NULL OR history.facility_id > $2)
          AND ($3::text IS NULL OR history.country_code = $3)
          AND ($4::text IS NULL OR history.city = $4)
          AND ($5::text IS NULL OR history.classification_category = $5)
          AND ($6::text IS NULL OR history.display_precision = $6)
          AND ($7::text IS NULL OR history.lifecycle_status = $7)
          AND ($8::text IS NULL OR history.provenance_origin_type = $8)
          AND ($9::text IS NULL OR lower(coalesce(history.canonical_name, '') || ' ' || coalesce(history.city, '') || ' ' || history.country_code || ' ' || history.classification_category || ' ' || coalesce(history.provenance_source_name, '') || ' ' || coalesce(taxonomy.leaf_activities::text, '') || ' ' || coalesce(taxonomy.assignments::text, '')) LIKE '%' || lower($9) || '%' ESCAPE '\')
          AND ($10::double precision IS NULL OR (history.display_location && ST_MakeEnvelope($10, $11, $12, $13, 4326)::geography AND ST_Intersects(history.display_location::geometry, ST_MakeEnvelope($10, $11, $12, $13, 4326))))
          AND ($14::double precision IS NULL OR ST_DWithin(history.display_location, ST_SetSRID(ST_Point($15, $16), 4326)::geography, $14 * 1000))
          AND ($19::text[] IS NULL OR taxonomy.primary_categories && $19)
        ORDER BY history.facility_id, history.observation_id LIMIT $17 OFFSET $18
    "#, &[&promoted_release_id, &cursor, &params.country_code, &params.region, &params.category, &params.display_precision, &params.lifecycle_status, &params.source_type, &search_text, &min_lon, &min_lat, &max_lon, &max_lat, &radius_km, &longitude, &latitude, &query_limit, &effective_offset, &category_keys]).await {
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
            taxonomy_display_category: row.get(24),
            taxonomy_primary_categories: row.get(25),
            taxonomy_leaf_activities: serde_json::from_str(row.get::<_, String>(26).as_str()).unwrap_or_else(|_| json!([])),
            taxonomy_assignments: serde_json::from_str(row.get::<_, String>(27).as_str()).unwrap_or_else(|_| json!([])),
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
    let release = match transaction.query_opt("SELECT r.release_id, r.ruleset_version, r.created_at, r.profile, (model.release_id IS NOT NULL AND manifest.release_id IS NOT NULL) FROM uec.releases r LEFT JOIN uec.public_discovery_read_models model ON model.release_id=r.release_id LEFT JOIN uec.release_manifests manifest ON manifest.release_id=r.release_id AND manifest.manifest_sha256=model.manifest_sha256 WHERE r.status = 'promoted' AND r.test_only IS NOT TRUE AND r.profile = $1 AND ($2::text IS NULL OR r.release_id=$2) ORDER BY r.created_at DESC, r.release_id DESC LIMIT 1", &[&requested_profile, &params.release_id]).await {
        Ok(release) => release,
        Err(_) => return v2_error(StatusCode::INTERNAL_SERVER_ERROR, "release_query_failed", "V2 release query failed"),
    };
    let Some(release) = release else {
        let _ = transaction.commit().await;
        if params.release_id.is_some() {
            return v2_error(StatusCode::GONE, "release_unavailable", "displayed release is no longer eligible");
        }
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
               history.source_rights_status,
               COALESCE(taxonomy.display_category, 'unclassified'),
               COALESCE(taxonomy.primary_categories, ARRAY['unclassified']::text[]),
               COALESCE(taxonomy.leaf_activities, '[]'::jsonb)::text,
               COALESCE(taxonomy.assignments, '[]'::jsonb)::text
        FROM uec.map_facilities_public_discovery_read_model AS history
        LEFT JOIN LATERAL (
          SELECT min(s.display_category) AS display_category,
                 array_agg(DISTINCT a.primary_key ORDER BY a.primary_key) FILTER (WHERE a.primary_key IS NOT NULL) AS primary_categories,
                 COALESCE(jsonb_agg(DISTINCT jsonb_build_object('key', a.leaf_key, 'label', a.leaf_label)) FILTER (WHERE a.leaf_key IS NOT NULL AND a.leaf_label IS NOT NULL AND a.mapping_method IN ('direct','derived') AND a.mapping_status IN ('mapped','partial')), '[]'::jsonb) AS leaf_activities,
                 COALESCE(jsonb_agg(DISTINCT jsonb_build_object('primary_key',a.primary_key,'leaf_key',a.leaf_key,'leaf_label',a.leaf_label,'source_code_reference',a.source_code_reference,'source_label_reference',a.source_label_reference,'source_code',a.source_code,'source_label',a.source_label,'method',a.mapping_method,'status',a.mapping_status,'taxonomy_version',s.taxonomy_version,'crosswalk_version',s.crosswalk_version,'ruleset_version',s.ruleset_version)) FILTER (WHERE a.assignment_set_id IS NOT NULL), '[]'::jsonb) AS assignments
          FROM uec.map_facilities_public_discovery_read_model eligible
          JOIN uec.observation_taxonomy_assignment_sets s ON s.observation_id=eligible.observation_id AND s.taxonomy_version='uec-taxonomy-v1'
            AND NOT EXISTS (SELECT 1 FROM uec.observation_taxonomy_assignment_sets newer WHERE newer.observation_id=s.observation_id AND newer.taxonomy_version=s.taxonomy_version AND (newer.created_at,newer.assignment_set_id)>(s.created_at,s.assignment_set_id))
          LEFT JOIN uec.observation_taxonomy_assignments a ON a.assignment_set_id=s.assignment_set_id
          WHERE eligible.release_id=history.release_id AND eligible.facility_id=history.facility_id AND eligible.observation_id=history.observation_id
        ) taxonomy ON TRUE
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
        taxonomy_display_category: row.get(24),
        taxonomy_primary_categories: row.get(25),
        taxonomy_leaf_activities: serde_json::from_str(row.get::<_, String>(26).as_str()).unwrap_or_else(|_| json!([])),
        taxonomy_assignments: serde_json::from_str(row.get::<_, String>(27).as_str()).unwrap_or_else(|_| json!([])),
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
    pub release_id: Option<String>,
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

    #[test]
    fn manifest_validator_etag_changes_when_suppression_generation_changes() {
        assert_ne!(release_manifest_etag("abc", 7), release_manifest_etag("abc", 8));
        assert_eq!(release_manifest_etag("abc", 7), "\"abc-7\"");
    }

    #[test]
    fn conditional_etag_matches_lists_and_weak_get_validators() {
        let mut headers = HeaderMap::new();
        headers.insert(axum::http::header::IF_NONE_MATCH, "\"old\", W/\"abc-7\"".parse().unwrap());
        assert!(if_none_match(&headers, "\"abc-7\""));
        headers.insert(axum::http::header::IF_NONE_MATCH, "\"old\"".parse().unwrap());
        assert!(!if_none_match(&headers, "\"abc-7\""));
    }

    #[tokio::test]
    async fn public_map_tile_rejects_out_of_range_coordinates_before_database_access() {
        let state = ApiState {
            database: None,
            dev_preview_token: None,
            dev_test_release_id: None,
            dev_test_release_token: None,
        };
        let response = get_v2_map_tile_handler(
            axum::extract::State(state),
            Path(PublicMapTilePath {
                release_id: "release-a".into(),
                tile_path: "15/0/0.mvt".into(),
            }),
            HeaderMap::new(),
            Query(PublicMapTileParams { profile: None }),
        )
        .await
        .into_response();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[test]
    fn real_preview_source_links_are_https_only_and_uncredentialed() {
        assert_eq!(
            real_preview_https_url(Some("https://example.test/source".into())),
            Some("https://example.test/source".into())
        );
        assert!(real_preview_https_url(Some("http://example.test/source".into())).is_none());
        assert!(real_preview_https_url(Some("https://user@example.test/source".into())).is_none());
        assert!(real_preview_https_url(Some("not a URL".into())).is_none());
    }

    #[test]
    fn fsis_source_coordinates_keep_a_private_unverified_precision_category() {
        assert_eq!(
            real_preview_coordinate_precision("us.fsis", Some("source-provided")),
            "source_provided_unverified"
        );
        assert_ne!(
            real_preview_coordinate_precision("us.fsis", Some("source-provided")),
            "source_numeric_pending_review"
        );
        assert_eq!(
            real_preview_coordinate_precision("other.source", Some("source-provided")),
            "approximate_source_provided_pending_review"
        );
        let source = include_str!("lib.rs");
        assert!(source.matches("CASE WHEN source_id = 'us.fsis' AND coordinate_precision = 'source-provided' THEN 'source_provided_unverified'").count() >= 2);
    }

    #[test]
    fn local_capital_core_reference_is_disclosed_as_coarse_not_facility_or_centroid() {
        assert_eq!(
            real_preview_reference_disclosure(Some(
                "Idescat capital-core point; approximate locality reference; not facility coordinates",
            )),
            (
                "locality_reference_coarse",
                "locality_reference_coarse",
                "locality_reference_not_facility_or_centroid",
            )
        );
        assert_eq!(
            real_preview_reference_disclosure(Some("Etalab commune centre")),
            (
                "city_reference_approximate",
                "administrative-reference-centre-approximate",
                "approximate_city_location_not_facility_point",
            )
        );
    }

    #[test]
    fn real_preview_never_exposes_zero_or_invalid_coordinates_as_points() {
        assert_eq!(
            safe_real_preview_location(
                "numeric_source_coordinate",
                true,
                false,
                Some(0.0),
                Some(0.0)
            ),
            ("city_postal".into(), None, None)
        );
        assert_eq!(
            safe_real_preview_location(
                "numeric_source_coordinate",
                false,
                false,
                Some(0.0),
                Some(0.0)
            ),
            ("unmapped_private_observation".into(), None, None)
        );
        assert_eq!(
            safe_real_preview_location(
                "numeric_source_coordinate",
                false,
                true,
                Some(91.0),
                Some(181.0)
            ),
            ("city_postal".into(), None, None)
        );
        assert_eq!(
            safe_real_preview_location(
                "numeric_source_coordinate",
                false,
                false,
                Some(91.0),
                Some(181.0)
            ),
            ("unmapped_private_observation".into(), None, None)
        );
        assert_eq!(
            safe_real_preview_location(
                "numeric_source_coordinate",
                false,
                false,
                Some(45.0),
                Some(12.0)
            ),
            ("numeric_source_coordinate".into(), Some(45.0), Some(12.0))
        );
        assert_eq!(
            safe_real_preview_location("city_postal", true, false, Some(0.0), Some(0.0)),
            ("city_postal".into(), None, None)
        );
        assert_eq!(
            safe_real_preview_location("city_postal", false, false, None, None),
            ("unmapped_private_observation".into(), None, None)
        );
    }

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

    #[test]
    fn real_preview_taxonomy_category_filter_is_allowlisted_or_semantics() {
        assert_eq!(
            parse_real_preview_taxonomy_categories(Some("slaughter,processing_and_preparation,slaughter")).unwrap(),
            Some(vec!["slaughter".to_string(), "processing_and_preparation".to_string()]),
        );
        assert_eq!(parse_real_preview_taxonomy_categories(None).unwrap(), None);
        assert!(parse_real_preview_taxonomy_categories(Some("slaughter house")).is_err());
        assert!(parse_real_preview_taxonomy_categories(Some(&"x".repeat(513))).is_err());
        assert!(REAL_PREVIEW_TAXONOMY_SELECT_SQL.contains("candidate_taxonomy_assignment_sets"));
        assert!(REAL_PREVIEW_TAXONOMY_SELECT_SQL.contains("candidate_taxonomy_assignments"));
        assert!(REAL_PREVIEW_TAXONOMY_SELECT_SQL.contains("ORDER BY s.created_at DESC,s.assignment_set_id DESC"));
    }

    #[tokio::test]
    async fn real_preview_rejects_invalid_taxonomy_filter_before_database_access() {
        let state = ApiState {
            database: None,
            dev_preview_token: Some("local-test-token-with-at-least-32-characters".into()),
            dev_test_release_id: None,
            dev_test_release_token: None,
        };
        let response = Router::new()
            .route("/dev/real-preview/locations", axum::routing::get(get_real_preview_list_handler))
            .with_state(state)
            .oneshot(Request::builder()
                .uri("/dev/real-preview/locations?category_keys=slaughter%20house")
                .header("host", "127.0.0.1:8000")
                .header("x-uec-dev-preview-token", "local-test-token-with-at-least-32-characters")
                .body(Body::empty()).unwrap()).await.unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn real_preview_map_tiles_reject_invalid_coordinates_and_source_filters() {
        let state = ApiState {
            database: None,
            dev_preview_token: Some("local-test-token-with-at-least-32-characters".into()),
            dev_test_release_id: None,
            dev_test_release_token: None,
        };
        let router = Router::new()
            .route(
                "/dev/real-preview/map/tiles/{z}/{x}/{y}",
                axum::routing::get(get_real_preview_map_tile_handler),
            )
            .with_state(state);
        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/dev/real-preview/map/tiles/2/4/0")
                    .header("host", "127.0.0.1:8000")
                    .header(
                        "x-uec-dev-preview-token",
                        "local-test-token-with-at-least-32-characters",
                    )
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(response.headers().get("cache-control").unwrap(), "no-store");

        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/dev/real-preview/map/tiles/2/1/1?source_id=bad%2Fsource")
                    .header("host", "127.0.0.1:8000")
                    .header(
                        "x-uec-dev-preview-token",
                        "local-test-token-with-at-least-32-characters",
                    )
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);

        let response = router
            .oneshot(
                Request::builder()
                    .uri("/dev/real-preview/map/tiles/2/1/1?cluster_cutoff=7.25")
                    .header("host", "127.0.0.1:8000")
                    .header(
                        "x-uec-dev-preview-token",
                        "local-test-token-with-at-least-32-characters",
                    )
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn real_preview_map_feed_preserves_auth_no_store_and_source_validation() {
        let state = ApiState {
            database: None,
            dev_preview_token: Some("local-test-token-with-at-least-32-characters".into()),
            dev_test_release_id: None,
            dev_test_release_token: None,
        };
        let router = Router::new()
            .route("/dev/real-preview/map/feed", axum::routing::get(get_real_preview_map_feed_handler))
            .with_state(state);
        let request = |uri: &str, token: Option<&str>| {
            let mut builder = Request::builder().uri(uri).header("host", "127.0.0.1:8000");
            if let Some(token) = token {
                builder = builder.header(DEV_PREVIEW_TOKEN_HEADER, token);
            }
            builder.body(Body::empty()).unwrap()
        };
        let missing_auth = router.clone().oneshot(request("/dev/real-preview/map/feed", None)).await.unwrap();
        assert_eq!(missing_auth.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(missing_auth.headers().get("cache-control").unwrap(), "no-store");

        let invalid_source = router.oneshot(request(
            "/dev/real-preview/map/feed?source_id=bad%2Fsource",
            Some("local-test-token-with-at-least-32-characters"),
        )).await.unwrap();
        assert_eq!(invalid_source.status(), StatusCode::BAD_REQUEST);
        assert_eq!(invalid_source.headers().get("cache-control").unwrap(), "no-store");

        let underscore_source = Router::new()
            .route("/dev/real-preview/map/feed", axum::routing::get(get_real_preview_map_feed_handler))
            .with_state(ApiState {
                database: None,
                dev_preview_token: Some("local-test-token-with-at-least-32-characters".into()),
                dev_test_release_id: None,
                dev_test_release_token: None,
            })
            .oneshot(request(
                "/dev/real-preview/map/feed?source_id=fss_approved_establishments",
                Some("local-test-token-with-at-least-32-characters"),
            ))
            .await
            .unwrap();
        assert_eq!(underscore_source.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    #[test]
    fn compact_map_units_conserve_weight_at_every_cluster_zoom() {
        // A numeric point contributes one; a coarse reference contributes its
        // grouped member count. Any z0–14 cluster partition must preserve sum.
        let units = [("us.fsis", 1_i64), ("us.fsis", 7), ("it.853-2004", 3)];
        let expected: i64 = units.iter().map(|(_, weight)| weight).sum();
        for zoom in 0..=14 {
            let mut clusters = std::collections::BTreeMap::<(&str, i64), i64>::new();
            for (source, weight) in units {
                // The cell id models any deterministic partition at this zoom;
                // source remains part of the key to prevent cross-source merges.
                let cell = (zoom as i64 + weight) % (i64::from(zoom) + 1);
                *clusters.entry((source, cell)).or_default() += weight;
            }
            assert_eq!(clusters.values().sum::<i64>(), expected);
            assert_eq!(
                clusters
                    .iter()
                    .filter(|((source, _), _)| *source == "us.fsis")
                    .map(|(_, weight)| *weight)
                    .sum::<i64>(),
                8
            );
            assert_eq!(
                clusters
                    .iter()
                    .filter(|((source, _), _)| *source == "it.853-2004")
                    .map(|(_, weight)| *weight)
                    .sum::<i64>(),
                3
            );
        }
    }

    #[test]
    fn real_preview_mvt_tile_cache_separates_snapshot_filter_and_coordinates() {
        let cache = RealPreviewMvtTileCache::default();
        let key = RealPreviewMvtTileCacheKey {
            contract_version: REAL_PREVIEW_MVT_CONTRACT_VERSION,
            snapshot_boundary: "snapshot-a".into(),
            source_id: None,
            cluster_cutoff_half_steps: 15,
            z: 4,
            x: 3,
            y: 5,
        };
        cache.insert(key.clone(), vec![1, 2, 3]);
        assert_eq!(cache.get(&key).as_deref(), Some(&[1, 2, 3][..]));

        let changed_snapshot = RealPreviewMvtTileCacheKey {
            snapshot_boundary: "snapshot-b".into(),
            ..key.clone()
        };
        let source_filtered = RealPreviewMvtTileCacheKey {
            source_id: Some("us.fsis".into()),
            ..key.clone()
        };
        let changed_cutoff = RealPreviewMvtTileCacheKey {
            cluster_cutoff_half_steps: 16,
            ..key.clone()
        };
        let adjacent_tile = RealPreviewMvtTileCacheKey { x: 4, ..key };
        assert!(cache.get(&changed_snapshot).is_none());
        assert!(cache.get(&source_filtered).is_none());
        assert!(cache.get(&changed_cutoff).is_none());
        assert!(cache.get(&adjacent_tile).is_none());
    }

    #[test]
    fn real_preview_cluster_cutoff_accepts_only_half_zoom_steps() {
        assert!(valid_real_preview_cluster_cutoff(4.0));
        assert!(valid_real_preview_cluster_cutoff(7.5));
        assert!(valid_real_preview_cluster_cutoff(14.0));
        assert!(!valid_real_preview_cluster_cutoff(3.5));
        assert!(!valid_real_preview_cluster_cutoff(14.5));
        assert!(!valid_real_preview_cluster_cutoff(7.25));
        assert!(!valid_real_preview_cluster_cutoff(f64::NAN));
    }

    #[test]
    fn real_preview_density_clusters_cross_old_cell_boundaries_and_are_stable() {
        let members = vec![
            RealPreviewClusterMember { feature_key: "a".into(), kind: "source_coordinate".into(), source_id: Some("us.fsis".into()), precision: "source-provided".into(), weight: 1, x: 999.0, y: 1000.0 },
            RealPreviewClusterMember { feature_key: "b".into(), kind: "source_coordinate".into(), source_id: Some("us.fsis".into()), precision: "source-provided".into(), weight: 1, x: 1001.0, y: 1000.0 },
            RealPreviewClusterMember { feature_key: "c".into(), kind: "source_coordinate".into(), source_id: Some("us.fsis".into()), precision: "source-provided".into(), weight: 1, x: 1004.0, y: 1001.0 },
            RealPreviewClusterMember { feature_key: "city".into(), kind: "city_reference".into(), source_id: None, precision: "locality_reference_coarse".into(), weight: 4, x: 1003.0, y: 1002.0 },
            RealPreviewClusterMember { feature_key: "sparse".into(), kind: "source_coordinate".into(), source_id: Some("us.fsis".into()), precision: "source-provided".into(), weight: 1, x: 2000.0, y: 2000.0 },
        ];
        let first = real_preview_build_cluster_features(members.clone(), 10.0, 2);
        let second = real_preview_build_cluster_features(members.into_iter().rev().collect(), 10.0, 2);
        let first_cluster = first.iter().find(|feature| feature.kind == "cluster").unwrap();
        let second_cluster = second.iter().find(|feature| feature.kind == "cluster").unwrap();
        assert_eq!(first_cluster.feature_key, second_cluster.feature_key);
        assert_eq!(first_cluster.count, 7, "city references contribute their represented weight");
        assert!((first_cluster.x - 1001.75).abs() < 0.001);
        assert!(first.iter().any(|feature| feature.feature_key == "sparse" && feature.kind == "source_coordinate"));
        assert_eq!(first.len(), 2);
    }

    #[test]
    fn real_preview_hierarchy_tile_selection_is_bounded_and_wraps_the_antimeridian() {
        let half_world = std::f64::consts::PI * 6_378_137.0;
        let features = vec![
            RealPreviewHierarchyFeature { feature_key: "near-west-edge".into(), parent_key: None,
                kind: "cluster".into(), count: 3, precision: "mixed_location_cluster".into(),
                next_zoom: 3, x: half_world - 1000.0, y: 0.0 },
            RealPreviewHierarchyFeature { feature_key: "far-away".into(), parent_key: None,
                kind: "cluster".into(), count: 3, precision: "mixed_location_cluster".into(),
                next_zoom: 3, x: 0.0, y: 0.0 },
        ];
        let selected = real_preview_hierarchy_tile_features(&features, 2, 0, 2);
        assert_eq!(selected.len(), 1);
        assert_eq!(selected[0].feature_key, "near-west-edge");
        assert!(selected[0].x < -half_world, "wrapped copy must clip into the westmost tile");
    }

    #[tokio::test]
    async fn real_preview_reference_rejects_non_opaque_keys_before_database_access() {
        let state = ApiState {
            database: None,
            dev_preview_token: Some("local-test-token-with-at-least-32-characters".into()),
            dev_test_release_id: None,
            dev_test_release_token: None,
        };
        let router = Router::new()
            .route(
                "/dev/real-preview/map/references/{reference_key}",
                axum::routing::get(get_real_preview_reference_handler),
            )
            .with_state(state);
        let response = router
            .oneshot(
                Request::builder()
                    .uri("/dev/real-preview/map/references/not-an-opaque-key")
                    .header("host", "127.0.0.1:8000")
                    .header(
                        "x-uec-dev-preview-token",
                        "local-test-token-with-at-least-32-characters",
                    )
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
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

    #[test]
    fn map_artifact_accepts_legacy_and_compact_taxonomy_feature_schemas() {
        let v1 = json!({"feature_schema_version":"uec-map-feature-v1","feature_properties":["feature_key","kind","count","exact_count","coarse_count","next_zoom","record_id","category_key"]});
        let v2 = json!({"feature_schema_version":"uec-map-feature-v2","feature_properties":["feature_key","kind","count","exact_count","coarse_count","next_zoom","record_id","category_key","category_keys_compact"]});
        assert!(map_artifact_feature_schema_valid(&v1));
        assert!(map_artifact_feature_schema_valid(&v2));
        let invalid = json!({"feature_schema_version":"uec-map-feature-v2","feature_properties":["feature_key","category_keys_compact"]});
        assert!(!map_artifact_feature_schema_valid(&invalid));
    }

    #[tokio::test]
    async fn taxonomy_category_filters_validate_keys_before_database_access() {
        let state = ApiState {
            database: None,
            dev_preview_token: None,
            dev_test_release_id: None,
            dev_test_release_token: None,
        };
        let app = || Router::new()
            .route("/api/v2/locations", axum::routing::get(get_v2_locations_handler))
            .with_state(state.clone());
        let invalid = app().oneshot(Request::builder().uri("/api/v2/locations?category_keys=slaughter%20house").body(Body::empty()).unwrap()).await.unwrap();
        assert_eq!(invalid.status(), StatusCode::BAD_REQUEST);
        let body = axum::body::to_bytes(invalid.into_body(), usize::MAX).await.unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["error"]["code"], "invalid_category_keys");
        assert_eq!(V2_TAXONOMY_PRIMARY_CATEGORIES.len(), 6);
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
            taxonomy_display_category: "slaughter".into(),
            taxonomy_primary_categories: vec!["slaughter".into()],
            taxonomy_leaf_activities: json!([]),
            taxonomy_assignments: json!([]),
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
        assert_eq!(json["taxonomy_display_category"], "slaughter");
        assert_eq!(json["taxonomy_primary_categories"][0], "slaughter");
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
