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
use std::error::Error;

mod location;
use crate::location::*;

pub use location::Location;

const DATA_DIR: Dir = include_dir!("./static_data");

pub async fn get_locations_handler(Query(params): Query<LocationParams>) -> impl IntoResponse {
    match read_locations_from_csv(params.country_code).await {
        Ok(locations) => Json(locations).into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Failed to read location data: {}", e),
        )
            .into_response(),
    }
}

pub async fn get_aphis_reports_handler() -> impl IntoResponse {
    match read_aphis_reports_from_csv().await {
        Ok(reports) => Json(reports).into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Failed to read APHIS data: {}", e),
        )
            .into_response(),
    }
}

pub async fn get_inspection_reports_handler() -> impl IntoResponse {
    match read_inspection_reports_from_csv().await {
        Ok(reports) => Json(reports).into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Failed to read inspection reports data: {}", e),
        )
            .into_response(),
    }
}

async fn read_locations_from_csv(
    country: Option<String>,
) -> Result<Vec<LocationResponse>, Box<dyn Error>> {
    let mut locations = Vec::new();

    // Process each country directory
    for locale_dir in DATA_DIR.dirs() {
        let dir_name = locale_dir
            .path()
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();

        // Skip the country directory if it doesn't match the country code
        if let Some(country) = &country {
            if dir_name != *country {
                continue;
            }
        }

        // Read the CSV file for this country
        let csv_path = format!("{}/locations.csv", dir_name);
        if let Some(csv_data) = DATA_DIR.get_file(&csv_path) {
            let mut reader = csv::Reader::from_reader(csv_data.contents());

            for result in reader.deserialize() {
                let record: Location = result?;
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
            }
        }
    }
    Ok(locations)
}

pub async fn read_aphis_reports_from_csv() -> Result<Vec<AphisReport>, Box<dyn Error>> {
    // Embed the APHIS data at compile time
    let csv_data = include_str!("../static_data/us/aphis_data_final.csv");

    // Read directly from the string data
    let mut reader = csv::Reader::from_reader(csv_data.as_bytes());

    let mut reports = Vec::new();
    for mut record in reader.deserialize::<AphisReport>().flatten() {
        record.animals_tested = Some(get_tested_animals(&record));
        reports.push(record);
    }
    Ok(reports)
}

pub async fn read_inspection_reports_from_csv() -> Result<Vec<InspectionReport>, Box<dyn Error>> {
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

#[derive(Serialize, Debug)]
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
