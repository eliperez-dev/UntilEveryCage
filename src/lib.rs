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
use axum::extract::{Query, State};
use axum::{Json, http::StatusCode, response::IntoResponse};
use include_dir::{Dir, include_dir};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::error::Error;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;
use once_cell::sync::Lazy;
use deadpool_postgres::Pool;

#[derive(Clone)]
pub struct ApiState { pub database: Option<Pool> }

mod location;
use crate::location::*;

pub use location::Location;

const DATA_DIR: Dir = include_dir!("./static_data");

static CACHED_LOCATIONS: Lazy<Result<Vec<LocationResponse>, String>> = Lazy::new(|| {
    parse_all_locations().map_err(|e| e.to_string())
});

static CACHED_APHIS: Lazy<Result<Vec<AphisReport>, String>> = Lazy::new(|| {
    parse_aphis_reports().map_err(|e| e.to_string())
});

static CACHED_INSPECTION: Lazy<Result<Vec<InspectionReport>, String>> = Lazy::new(|| { 
    parse_inspection_reports().map_err(|e| e.to_string())
});

pub async fn get_locations_handler(Query(params): Query<LocationParams>) -> impl IntoResponse {
    match CACHED_LOCATIONS.as_ref() {
        Ok(all_locations) => {
            let filtered = if let Some(country) = params.country_code {
                all_locations.iter().filter(|loc| loc.country == country).cloned().collect()
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

#[derive(Deserialize)]
pub struct V2LocationParams {
    pub country_code: Option<String>,
    pub category: Option<String>,
    pub source_type: Option<String>,
    pub display_precision: Option<String>,
    pub lifecycle_status: Option<String>,
    pub limit: Option<String>,
    pub offset: Option<String>,
}

#[derive(Serialize)]
pub struct V2Location {
    pub facility_id: uuid::Uuid,
    pub canonical_name: Option<String>,
    pub country_code: String,
    pub city: Option<String>,
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

pub async fn get_v2_locations_handler(State(state): State<ApiState>, Query(params): Query<V2LocationParams>) -> impl IntoResponse {
    const PRECISIONS: &[&str] = &["exact", "city", "unmapped"];
    const LIFECYCLES: &[&str] = &["active_observed", "explicitly_closed", "not_seen_recently", "status_unknown"];
    if params.display_precision.as_deref().is_some_and(|v| !PRECISIONS.contains(&v)) {
        return (StatusCode::BAD_REQUEST, "invalid display_precision").into_response();
    }
    if params.lifecycle_status.as_deref().is_some_and(|v| !LIFECYCLES.contains(&v)) {
        return (StatusCode::BAD_REQUEST, "invalid lifecycle_status").into_response();
    }
    if params.category.as_deref().is_some_and(|v| v.trim().is_empty()) || params.country_code.as_deref().is_some_and(|v| v.len() != 2) {
        return (StatusCode::BAD_REQUEST, "invalid filter").into_response();
    }
    if params.source_type.as_deref().is_some_and(|v| !["official", "secondary", "user_submitted"].contains(&v)) {
        return (StatusCode::BAD_REQUEST, "invalid source_type").into_response();
    }
    let limit = match params.limit.as_deref().map(str::parse::<i64>).transpose() {
        Ok(value) => value.unwrap_or(100).clamp(1, 1000),
        Err(_) => return (StatusCode::BAD_REQUEST, "limit must be an integer").into_response(),
    };
    let offset = match params.offset.as_deref().map(str::parse::<i64>).transpose() {
        Ok(value) => value.unwrap_or(0).clamp(0, 1_000_000),
        Err(_) => return (StatusCode::BAD_REQUEST, "offset must be an integer").into_response(),
    };
    let client = match state.database.as_ref() { Some(pool) => match pool.get().await { Ok(client) => client, Err(_) => return (StatusCode::SERVICE_UNAVAILABLE, "Database pool unavailable").into_response() }, None => return (StatusCode::SERVICE_UNAVAILABLE, "V2 database is not configured").into_response() };
    let release = client.query_opt("SELECT release_id, ruleset_version, created_at FROM uec.releases WHERE status = 'promoted' ORDER BY created_at DESC, release_id DESC LIMIT 1", &[]).await;
    let release = match release {
        Ok(release) => release,
        Err(_) => return (StatusCode::INTERNAL_SERVER_ERROR, "V2 release query failed").into_response(),
    };
    let Some(release) = release else {
        return Json(serde_json::json!({"data": [], "api_version": "v2", "meta": {"release_id": null, "profile": "official", "coverage_note": "No promoted release is currently available."}})).into_response();
    };
    let promoted_release_id: String = release.get(0);
    let promoted_ruleset: String = release.get(1);
    let promoted_created_at: chrono::DateTime<chrono::Utc> = release.get(2);
    let rows = match client.query(r#"
        SELECT facility_id, canonical_name, country_code, city, display_precision,
               ST_Y(display_location::geometry), ST_X(display_location::geometry),
               first_observed_at, last_observed_at, observation_count, lifecycle_status,
               provenance_origin_type, release_id, release_ruleset_version,
               provenance_source_id, provenance_source_name, provenance_source_url, provenance_retrieved_at
        FROM uec.map_facilities_display_history
        WHERE release_id = $1
          AND ($2::text IS NULL OR country_code = $2)
          AND ($3::text IS NULL OR classification_category = $3)
          AND ($4::text IS NULL OR display_precision = $4)
          AND ($5::text IS NULL OR lifecycle_status = $5)
          AND ($6::text IS NULL OR provenance_origin_type = $6)
        ORDER BY facility_id LIMIT $7 OFFSET $8
    "#, &[&promoted_release_id, &params.country_code, &params.category, &params.display_precision, &params.lifecycle_status, &params.source_type, &limit, &offset]).await {
        Ok(rows) => rows,
        Err(_) => return (StatusCode::INTERNAL_SERVER_ERROR, "V2 location query failed").into_response(),
    };
    let data = rows.into_iter().map(|row| V2Location {
        facility_id: row.get(0), canonical_name: row.get(1), country_code: row.get(2), city: row.get(3),
        display_precision: row.get(4), latitude: row.get(5), longitude: row.get(6),
        first_observed_at: row.get(7), last_observed_at: row.get(8), observation_count: row.get(9),
        lifecycle_status: row.get(10), source_type: row.get(11),
        release_id: row.get(12), release_ruleset_version: row.get(13), provenance_source_id: row.get(14),
        provenance_source: row.get(15), provenance_source_name: row.get(15), provenance_source_url: row.get(16), provenance_retrieved_at: row.get(17),
    }).collect::<Vec<_>>();
    let metadata = serde_json::json!({
        "release_id": promoted_release_id,
        "ruleset_version": promoted_ruleset,
        "release_created_at": promoted_created_at,
        "profile": "official",
        "coverage_note": "Results are limited to the selected promoted release and public-access policy."
    });
    Json(serde_json::json!({"data": data, "api_version": "v2", "meta": metadata})).into_response()
}

#[cfg(test)]
mod v2_api_tests {
    use super::*;
    use axum::{body::Body, http::{Request, StatusCode}, Router};
    use tower::ServiceExt;
    use tokio_postgres::NoTls;

    async fn test_state() -> ApiState {
        let mut config = deadpool_postgres::Config::new();
        config.url = Some(std::env::var("UEC_DATABASE_URL").unwrap_or_else(|_| "postgresql://uec:uec-local-development-only@localhost:5433/uec".into()));
        ApiState { database: Some(config.create_pool(Some(deadpool_postgres::Runtime::Tokio1), NoTls).unwrap()) }
    }

    #[tokio::test]
    async fn v2_response_is_json_when_database_is_configured() {
        let url = std::env::var("UEC_DATABASE_URL").unwrap_or_else(|_| "postgresql://uec:uec-local-development-only@localhost:5433/uec".into());
        unsafe { std::env::set_var("UEC_DATABASE_URL", url); }
        let response = Router::new().route("/api/v2/locations", axum::routing::get(get_v2_locations_handler)).with_state(test_state().await)
            .oneshot(Request::builder().uri("/api/v2/locations?country_code=DK").body(Body::empty()).unwrap()).await.unwrap();
        let status = response.status();
        if status != StatusCode::OK {
            let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
            panic!("unexpected status {status}: {}", String::from_utf8_lossy(&body));
        }
        assert_eq!(response.headers().get("content-type").unwrap(), "application/json");
        let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["api_version"], "v2");
        assert!(json["data"].is_array());
        assert!(json["meta"]["coverage_note"].is_string());
    }

    #[tokio::test]
    async fn v2_filters_are_accepted_without_bypassing_public_release_gate() {
        let url = std::env::var("UEC_DATABASE_URL").unwrap_or_else(|_| "postgresql://uec:uec-local-development-only@localhost:5433/uec".into());
        unsafe { std::env::set_var("UEC_DATABASE_URL", url); }
        for uri in [
            "/api/v2/locations?country_code=DK&category=retail_and_prepared_food",
            "/api/v2/locations?display_precision=city&lifecycle_status=active_observed",
        ] {
            let response = Router::new().route("/api/v2/locations", axum::routing::get(get_v2_locations_handler)).with_state(test_state().await)
                .oneshot(Request::builder().uri(uri).body(Body::empty()).unwrap()).await.unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
            let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
            assert_eq!(json["api_version"], "v2");
            assert!(json["data"].as_array().unwrap().is_empty());
        }
    }

    #[tokio::test]
    async fn v2_default_and_opt_in_profiles_remain_empty_until_promotion() {
        let url = std::env::var("UEC_DATABASE_URL").unwrap_or_else(|_| "postgresql://uec:uec-local-development-only@localhost:5433/uec".into());
        unsafe { std::env::set_var("UEC_DATABASE_URL", url); }
        for uri in [
            "/api/v2/locations",
            "/api/v2/locations?category=logistics_and_storage",
            "/api/v2/locations?category=retail_and_prepared_food&display_precision=exact",
            "/api/v2/locations?lifecycle_status=explicitly_closed",
        ] {
            let response = Router::new().route("/api/v2/locations", axum::routing::get(get_v2_locations_handler)).with_state(test_state().await)
                .oneshot(Request::builder().uri(uri).body(Body::empty()).unwrap()).await.unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
            let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
            assert!(json["data"].as_array().unwrap().is_empty());
        }
    }

    #[tokio::test]
    async fn v2_response_cannot_contain_raw_evidence_fields() {
        let url = std::env::var("UEC_DATABASE_URL").unwrap_or_else(|_| "postgresql://uec:uec-local-development-only@localhost:5433/uec".into());
        unsafe { std::env::set_var("UEC_DATABASE_URL", url); }
        let response = Router::new().route("/api/v2/locations", axum::routing::get(get_v2_locations_handler)).with_state(test_state().await)
            .oneshot(Request::builder().uri("/api/v2/locations?country_code=DK").body(Body::empty()).unwrap()).await.unwrap();
        let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let text = String::from_utf8(body.to_vec()).unwrap();
        for forbidden in ["raw_fields", "street_address", "phone", "private_address"] {
            assert!(!text.contains(forbidden), "public response contained forbidden field {forbidden}");
        }
    }

    #[tokio::test]
    async fn v2_handles_concurrent_requests_through_shared_pool() {
        let state = test_state().await;
        let router = Router::new().route("/api/v2/locations", axum::routing::get(get_v2_locations_handler)).with_state(state);
        let requests = (0..12).map(|_| {
            let router = router.clone();
            async move {
                router.oneshot(Request::builder().uri("/api/v2/locations?country_code=DK&limit=1").body(Body::empty()).unwrap()).await.unwrap().status()
            }
        });
        let statuses = futures_util::future::join_all(requests).await;
        assert!(statuses.iter().all(|status| *status == StatusCode::OK));
    }

    #[test]
    fn v2_schema_serializes_history_and_lifecycle_fields() {
        let item = V2Location {
            facility_id: uuid::Uuid::nil(), canonical_name: Some("Example".into()), country_code: "DK".into(),
            city: Some("Testby".into()), display_precision: "city".into(), latitude: Some(55.0), longitude: Some(10.0),
            first_observed_at: None, last_observed_at: None, observation_count: Some(2),
            lifecycle_status: "active_observed".into(), source_type: "official".into(), provenance_source: None,
            release_id: "test".into(), release_ruleset_version: "test".into(), provenance_source_id: "test".into(),
            provenance_source_name: "test".into(), provenance_source_url: "https://example.invalid".into(), provenance_retrieved_at: chrono::Utc::now(),
        };
        let json = serde_json::to_value(item).unwrap();
        assert_eq!(json["display_precision"], "city");
        assert_eq!(json["observation_count"], 2);
        assert_eq!(json["lifecycle_status"], "active_observed");
        assert_eq!(json["source_type"], "official");
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
                        println!("[ERROR] Failed to deserialize row {} in {}: {}", idx, dir_name, e);
                        return Err(Box::new(e));
                    }
                }
            }
            println!("[DEBUG] Parsed {} records from country: {}", country_count, dir_name);
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

    let inline_pos = html.find("/inline.js")
        .ok_or("inline.js not found in APHIS page")?;
    let l_marker = "/sfsites/l/";
    let l_pos = html[..inline_pos].rfind(l_marker)
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

    Ok(AphisContext { fwuid, loaded_version, fetched_at: Instant::now() })
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
    let action_name = if is_annual { "doARSearch" } else { "doIRSearch_UI" };
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
    let results = if results.is_array() { results } else { Value::Array(vec![]) };
    Json(results).into_response()
}
