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
use axum::{Router, routing::get};
use tower_http::compression::CompressionLayer;
use tower_http::cors::CorsLayer;

#[shuttle_runtime::main]
async fn main() -> shuttle_axum::ShuttleAxum {
    let cors = CorsLayer::very_permissive();
    let app = Router::new()
        .route(
            "/api/locations",
            get(heatmap_backend::get_locations_handler),
        )
        .route(
            "/api/aphis-reports",
            get(heatmap_backend::get_aphis_reports_handler),
        )
        .route(
            "/api/inspection-reports",
            get(heatmap_backend::get_inspection_reports_handler),
        )
        .layer(CompressionLayer::new().br(true))
        .layer(cors);
 
    Ok(app.into())
}
