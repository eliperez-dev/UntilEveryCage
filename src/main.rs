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
use axum::{Json, http::StatusCode, response::IntoResponse};
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
        .route("/health/live", get(liveness))
        .route("/health/ready", get(readiness))
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

async fn liveness() -> impl IntoResponse {
    Json(serde_json::json!({"status": "ok", "service": "uec-api"}))
}

async fn readiness(
    axum::extract::State(state): axum::extract::State<uec_api::ApiState>,
) -> impl IntoResponse {
    let Some(pool) = state.database else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({"status": "not_ready", "reason": "database_not_configured"})),
        )
            .into_response();
    };
    match pool.get().await {
        Ok(client) => match client.query_one("SELECT 1", &[]).await {
            Ok(_) => Json(serde_json::json!({"status": "ready", "database": "ok"})).into_response(),
            Err(_) => (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({"status": "not_ready", "reason": "database_query_failed"})),
            )
                .into_response(),
        },
        Err(_) => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({"status": "not_ready", "reason": "database_pool_unavailable"})),
        )
            .into_response(),
    }
}

fn validate_runtime(
    mode: &str,
    database_url: Option<&str>,
    port: &str,
) -> Result<u16, &'static str> {
    if mode == "production" && database_url.is_none() {
        return Err("UEC_DATABASE_URL is required in production");
    }
    if !matches!(mode, "development" | "production") {
        return Err("UEC_RUNTIME_MODE must be development or production");
    }
    match port.parse::<u16>() {
        Ok(port) if port > 0 => Ok(port),
        _ => Err("PORT must be a valid non-zero TCP port"),
    }
}

#[tokio::main]
async fn main() {
    let mode = std::env::var("UEC_RUNTIME_MODE").unwrap_or_else(|_| "development".to_string());
    let database_url = std::env::var("UEC_DATABASE_URL").ok();
    let port = std::env::var("PORT").unwrap_or_else(|_| "8000".to_string());
    let port = validate_runtime(&mode, database_url.as_deref(), &port).unwrap_or_else(|error| {
        eprintln!(
            "{{\"event\":\"configuration_error\",\"reason\":\"{}\"}}",
            error
        );
        std::process::exit(2)
    });
    let database = database_url.and_then(|url| {
        let mut config = Config::new();
        config.url = Some(url);
        config.manager = Some(ManagerConfig {
            recycling_method: RecyclingMethod::Fast,
        });
        match config.create_pool(Some(Runtime::Tokio1), NoTls) {
            Ok(pool) => Some(pool),
            Err(_) => {
                eprintln!(
                    "{}",
                    "{\"event\":\"database_pool_error\",\"reason\":\"pool_creation_failed\"}"
                );
                if mode == "production" {
                    std::process::exit(2);
                }
                None
            }
        }
    });
    let addr = format!("0.0.0.0:{}", port);
    println!(
        "{{\"event\":\"server_starting\",\"service\":\"uec-api\",\"mode\":\"{}\",\"port\":{}}}",
        mode, port
    );

    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app(uec_api::ApiState { database }))
        .await
        .unwrap();
}

#[cfg(test)]
mod config_tests {
    use super::validate_runtime;
    #[test]
    fn development_allows_local_defaults() {
        assert_eq!(validate_runtime("development", None, "8000"), Ok(8000));
    }
    #[test]
    fn production_requires_database() {
        assert_eq!(
            validate_runtime("production", None, "8000"),
            Err("UEC_DATABASE_URL is required in production")
        );
    }
    #[test]
    fn invalid_mode_and_port_are_rejected() {
        assert!(validate_runtime("test", Some("redacted"), "8000").is_err());
        assert!(validate_runtime("production", Some("redacted"), "bad").is_err());
        assert!(validate_runtime("production", Some("redacted"), "0").is_err());
    }
}
