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
use axum::http::{HeaderValue, Method};
use axum::{Router, routing::get};
use tower_http::compression::CompressionLayer;
use tower_http::cors::CorsLayer;

use deadpool_postgres::{Config, ManagerConfig, RecyclingMethod, Runtime};
use tokio_postgres::NoTls;
use tower_http::services::ServeDir;

pub fn app(state: uec_api::ApiState) -> Router {
    let origin =
        std::env::var("UEC_CORS_ORIGIN").unwrap_or_else(|_| "http://localhost:3000".to_string());
    let origin = origin
        .parse::<HeaderValue>()
        .expect("UEC_CORS_ORIGIN must be a valid origin");
    let cors = CorsLayer::new()
        .allow_origin(origin)
        .allow_methods([Method::GET]);
    Router::new()
        .route("/api/locations", get(uec_api::get_locations_handler))
        .route("/api/v2/locations", get(uec_api::get_v2_locations_handler))
        .route(
            "/api/v2/locations/{facility_id}",
            get(uec_api::get_v2_location_detail_handler),
        )
        .route(
            "/api/aphis-reports",
            get(uec_api::get_aphis_reports_handler),
        )
        .route(
            "/api/inspection-reports",
            get(uec_api::get_inspection_reports_handler),
        )
        .route("/api/aphis-query", get(uec_api::get_aphis_query_handler))
        .fallback_service(ServeDir::new("static"))
        .layer(CompressionLayer::new().br(true))
        .layer(cors)
        .with_state(state)
}

#[tokio::main]
async fn main() {
    let database = std::env::var("UEC_DATABASE_URL").ok().and_then(|url| {
        let mut config = Config::new();
        config.url = Some(url);
        config.manager = Some(ManagerConfig {
            recycling_method: RecyclingMethod::Fast,
        });
        config.create_pool(Some(Runtime::Tokio1), NoTls).ok()
    });
    let port = std::env::var("PORT").unwrap_or_else(|_| "8000".to_string());
    let addr = format!("0.0.0.0:{}", port);
    println!("Listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app(uec_api::ApiState { database }))
        .await
        .unwrap();
}
