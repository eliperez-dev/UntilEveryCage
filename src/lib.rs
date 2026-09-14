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
use axum::http::HeaderMap;
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
    let release = match client.query_opt("SELECT r.release_id, m.manifest_sha256 FROM uec.releases r JOIN uec.release_manifests m ON m.release_id=r.release_id WHERE r.status='promoted' AND r.test_only IS NOT TRUE AND r.profile=$1 ORDER BY r.created_at DESC, r.release_id DESC LIMIT 1", &[&profile]).await {
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
    let rows = match client.query("SELECT h.facility_id, h.canonical_name, h.country_code, h.city, h.classification_category, h.display_precision, r.factual_review_status, r.privacy_screening_status, r.maintainer_approval, r.reviewer_role, h.provenance_origin_type, h.provenance_source_id, h.provenance_source_name, h.provenance_source_url, h.provenance_retrieved_at, h.release_id FROM uec.map_facilities_display_history h JOIN uec.publication_review_release_current r ON r.source_record_id=h.source_record_id AND r.release_id=h.release_id WHERE h.release_id=$1 AND r.publication_eligible=true AND r.privacy_screening_status='passed' AND ($2='community' OR r.maintainer_approval='approved') ORDER BY h.facility_id LIMIT 1001", &[&release_id, &profile]).await {
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
                canonical_name: row.get(1),
                country_code: row.get(2),
                city: row.get(3),
                category: row.get(4),
                display_precision: row.get(5),
                factual_review_status: factual_review_status.clone(),
                privacy_screening_status: row.get(7),
                project_approval: row.get(8),
                reviewer_role: row.get(9),
                source_type: row.get(10),
                provenance_source_id: row.get(11),
                provenance_source_name: row.get(12),
                provenance_source_url: row.get(13),
                provenance_retrieved_at: row.get(14),
                release_id: row.get(15),
                release_profile: profile.to_string(),
                profile_notice: export_profile_notice(profile).to_string(),
                publication_warning: export_publication_warning(profile, &factual_review_status),
                manifest_sha256: manifest_sha256.clone(),
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
    let rows = match client.query(r#"SELECT f.facility_id,f.canonical_name,f.country_code,f.city,o.classification_category,
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
        ORDER BY f.facility_id LIMIT $4"#, &[&release_id,&params.country_code,&params.category,&limit]).await {
        Ok(rows)=>rows, Err(_)=>return v2_error(StatusCode::SERVICE_UNAVAILABLE,"test_release_query_failed","test release unavailable")
    };
    let data = rows.into_iter().map(|row| json!({"facility_id":row.get::<_,uuid::Uuid>(0),"canonical_name":row.get::<_,Option<String>>(1),"country_code":row.get::<_,String>(2),"city":row.get::<_,Option<String>>(3),"category":row.get::<_,String>(4),"publication_profile":profile,"factual_review_status":row.get::<_,Option<String>>(8).unwrap_or("unreviewed".into()),"privacy_screening_status":row.get::<_,Option<String>>(9).unwrap_or("pending".into()),"project_approval":"not-approved","reviewer_role":row.get::<_,Option<String>>(11),"publication_warning":"Disposable test release — not project-approved or published","display_precision":row.get::<_,String>(5),"latitude":row.get::<_,Option<f64>>(6),"longitude":row.get::<_,Option<f64>>(7),"first_observed_at":null,"last_observed_at":null,"observation_count":null,"lifecycle_status":"status_unknown","source_type":row.get::<_,String>(12),"release_id":release_id,"release_ruleset_version":row.get::<_,String>(16),"provenance_source_id":row.get::<_,String>(13),"provenance_source_name":row.get::<_,String>(14),"provenance_source_url":row.get::<_,String>(15),"provenance_retrieved_at":row.get::<_,chrono::DateTime<chrono::Utc>>(17)})).collect::<Vec<_>>();
    let mut meta = test_release_meta(release_id, profile);
    meta["result_count"] = json!(data.len());
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

fn constant_time_token_matches(expected: &str, provided: &str) -> bool {
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
                "latitude": row.get::<_, Option<f64>>(8),
                "longitude": row.get::<_, Option<f64>>(9),
                "source_type": row.get::<_, String>(10),
                "provenance_source_id": row.get::<_, String>(11),
                "provenance_source_name": row.get::<_, String>(12),
                "provenance_source_url": row.get::<_, String>(13),
                "provenance_retrieved_at": row.get::<_, chrono::DateTime<chrono::Utc>>(14),
                "factual_review_status": row.get::<_, String>(15),
                "privacy_screening_status": row.get::<_, String>(16),
                "project_approval": false,
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
        "country_code":{"values":V2_COUNTRIES}, "category":{"values":V2_CATEGORIES},
        "source_type":{"values":V2_SOURCE_TYPES}, "profile":{"values":V2_PROFILES,"default":"official"},
        "display_precision":{"values":V2_PRECISIONS}, "lifecycle_status":{"values":V2_LIFECYCLES}
    }, "pagination":{"limit_max":1000,"cursor":"facility_id"}, "privacy":"Filters operate only on eligible records in the selected promoted release; filters never override suppression or publication review."})).into_response()
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
    let release = match client.query_opt("SELECT release_id, ruleset_version, created_at FROM uec.releases WHERE status='promoted' AND test_only IS NOT TRUE AND profile=$1 ORDER BY created_at DESC, release_id DESC LIMIT 1", &[&profile]).await { Ok(row) => row, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "release_query_failed", "release query failed") };
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
    let rows = match client.query("SELECT country_code, classification_category, display_precision, lifecycle_status, provenance_origin_type FROM uec.map_facilities_display_history WHERE release_id=$1 AND ($2::text IS NULL OR country_code=$2) AND ($3::text IS NULL OR classification_category=$3) AND ($4::text IS NULL OR provenance_origin_type=$4) AND ($5::text IS NULL OR display_precision=$5) AND ($6::text IS NULL OR lifecycle_status=$6)", &[&release_id, &params.country_code, &params.category, &params.source_type, &params.display_precision, &params.lifecycle_status]).await { Ok(rows) => rows, Err(_) => return v2_error(StatusCode::SERVICE_UNAVAILABLE, "facets_query_failed", "public facets unavailable") };
    let mut dimensions = serde_json::Map::new();
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
            "lifecycle_status",
            rows.iter().map(|r| r.get::<_, String>(3)).collect(),
        ),
        (
            "source_type",
            rows.iter().map(|r| r.get::<_, String>(4)).collect(),
        ),
    ] {
        let mut counts = std::collections::BTreeMap::<String, usize>::new();
        for value in values {
            *counts.entry(value).or_default() += 1;
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
    Json(json!({"api_version":"v2", "meta":{"profile":profile,"release_id":release_id,"ruleset_version":ruleset_version,"release_created_at":release_created_at,"coverage_scope":"selected_promoted_release_public_facilities","count_semantics":"Counts are eligible public facility projection rows after current suppression; they are not story-wide or animal counts.","filters":{"country_code":params.country_code,"category":params.category,"source_type":params.source_type,"display_precision":params.display_precision,"lifecycle_status":params.lifecycle_status}}, "dimensions":dimensions})).into_response()
}

#[derive(Deserialize)]
pub struct V2LocationParams {
    pub country_code: Option<String>,
    pub category: Option<String>,
    pub source_type: Option<String>,
    pub profile: Option<String>,
    pub display_precision: Option<String>,
    pub lifecycle_status: Option<String>,
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
    let release = transaction.query_opt("SELECT release_id, ruleset_version, created_at, profile FROM uec.releases WHERE status = 'promoted' AND test_only IS NOT TRUE AND profile = $1 ORDER BY created_at DESC, release_id DESC LIMIT 1", &[&requested_profile]).await;
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
    let query_limit = limit + 1;
    let rows = match transaction.query(r#"
        SELECT facility_id, canonical_name, country_code, city, classification_category, display_precision,
               review.factual_review_status, review.privacy_screening_status, review.maintainer_approval, review.reviewer_role,
               ST_Y(display_location::geometry), ST_X(display_location::geometry),
               first_observed_at, last_observed_at, observation_count, lifecycle_status,
               provenance_origin_type, map_facilities_display_history.release_id, release_ruleset_version,
               provenance_source_id, provenance_source_name, provenance_source_url, provenance_retrieved_at
        FROM uec.map_facilities_display_history
        JOIN uec.publication_review_release_current AS review
          ON review.source_record_id = map_facilities_display_history.source_record_id
         AND review.release_id = map_facilities_display_history.release_id
        WHERE map_facilities_display_history.release_id = $1
          AND ($2::uuid IS NULL OR facility_id > $2)
          AND ($3::text IS NULL OR country_code = $3)
          AND ($4::text IS NULL OR classification_category = $4)
          AND ($5::text IS NULL OR display_precision = $5)
          AND ($6::text IS NULL OR lifecycle_status = $6)
          AND ($7::text IS NULL OR provenance_origin_type = $7)
        ORDER BY facility_id LIMIT $8 OFFSET $9
    "#, &[&promoted_release_id, &cursor, &params.country_code, &params.category, &params.display_precision, &params.lifecycle_status, &params.source_type, &query_limit, &effective_offset]).await {
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
        "release_created_at": promoted_created_at,
        "profile": promoted_profile,
        "next_cursor": next_cursor,
        "coverage_note": "Results are eligible public facility projection rows from the selected promoted release after current suppression; they are not story-wide or animal counts.",
        "coverage_scope": "selected_promoted_release_public_facilities",
        "count_semantics": "Each row represents a public facility projection, not an animal count."
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
    let release = match transaction.query_opt("SELECT release_id, ruleset_version, created_at, profile FROM uec.releases WHERE status = 'promoted' AND test_only IS NOT TRUE AND profile = $1 ORDER BY created_at DESC, release_id DESC LIMIT 1", &[&requested_profile]).await {
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
    let row = match transaction.query_opt(r#"
        SELECT facility_id, canonical_name, country_code, city, classification_category, display_precision,
               review.factual_review_status, review.privacy_screening_status, review.maintainer_approval, review.reviewer_role,
               ST_Y(display_location::geometry), ST_X(display_location::geometry),
               first_observed_at, last_observed_at, observation_count, lifecycle_status,
               provenance_origin_type, map_facilities_display_history.release_id, release_ruleset_version,
               provenance_source_id, provenance_source_name, provenance_source_url, provenance_retrieved_at
        FROM uec.map_facilities_display_history
        JOIN uec.publication_review_release_current AS review
          ON review.source_record_id = map_facilities_display_history.source_record_id
         AND review.release_id = map_facilities_display_history.release_id
        WHERE facility_id = $1 AND map_facilities_display_history.release_id = $2
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
    Json(serde_json::json!({"data": item, "api_version": "v2", "meta": {"release_id": release_id, "ruleset_version": ruleset, "release_created_at": created_at, "profile": profile, "coverage_scope": "selected_promoted_release_public_facilities", "count_semantics": "This record is a public facility projection, not an animal count."}})).into_response()
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
    async fn filter_metadata_is_versioned_and_allowlisted() {
        let response = get_v2_filter_metadata_handler().await.into_response();
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(V2_CATEGORIES.len(), 4);
        assert!(!V2_COUNTRIES.contains(&"ZZ"));
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
