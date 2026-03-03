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
use axum::extract::Query;
use axum::{Json, http::StatusCode, response::IntoResponse};
use include_dir::{Dir, include_dir};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::error::Error;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;
use once_cell::sync::Lazy;

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
