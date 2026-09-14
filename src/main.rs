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
use axum::extract::{ConnectInfo, State};
use axum::http::{HeaderValue, Method};
use axum::http::{Request, Response, header};
use axum::{Json, http::StatusCode, response::IntoResponse};
use axum::{Router, routing::get};
use std::collections::HashMap;
use std::net::{IpAddr, SocketAddr};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tower_http::compression::CompressionLayer;
use tower_http::cors::{AllowOrigin, CorsLayer};

use deadpool_postgres::{Config, ManagerConfig, RecyclingMethod, Runtime};
use tokio_postgres::NoTls;
use tokio_postgres_rustls::MakeRustlsConnect;
use tower_http::services::ServeDir;

pub fn app(state: uec_api::ApiState) -> Router {
    let cors = cors_layer().expect("CORS configuration must be validated before app startup");
    Router::new()
        .route("/health/live", get(liveness))
        .route("/health/ready", get(readiness))
        .route("/api/locations", get(uec_api::get_locations_handler))
        .route("/api/v2/locations", get(uec_api::get_v2_locations_handler))
        .route(
            "/api/v2/releases/manifest",
            get(uec_api::get_v2_release_manifest_handler),
        )
        .route(
            "/api/v2/locations.csv",
            get(uec_api::get_v2_locations_export_handler),
        )
        .route(
            "/api/v2/discovery/filters",
            get(uec_api::get_v2_filter_metadata_handler),
        )
        .route(
            "/api/v2/discovery/facets",
            get(uec_api::get_v2_facets_handler),
        )
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
        .layer(axum::middleware::from_fn_with_state(
            RateLimitState {
                limiter: Limiter::default(),
                trust_proxy: std::env::var("UEC_TRUST_PROXY").as_deref() == Ok("true"),
            },
            rate_limit,
        ))
        .layer(cors)
        .with_state(state)
}

fn parse_cors_origins(
    mode: &str,
    configured: Option<&str>,
    legacy: Option<&str>,
) -> Result<Vec<HeaderValue>, &'static str> {
    let value = configured.or(legacy).unwrap_or(if mode == "development" {
        "http://localhost:3000"
    } else {
        ""
    });
    if mode == "production" && value.trim().is_empty() {
        return Err("UEC_CORS_ORIGINS is required in production");
    }
    let mut origins = Vec::new();
    for raw in value.split(',').map(str::trim).filter(|v| !v.is_empty()) {
        if raw == "*" || raw.contains('*') {
            return Err("UEC_CORS_ORIGINS must not contain wildcards");
        }
        let uri = raw
            .parse::<axum::http::Uri>()
            .map_err(|_| "UEC_CORS_ORIGINS contains a malformed origin")?;
        if !matches!(uri.scheme_str(), Some("http") | Some("https"))
            || uri.host().is_none()
            || !uri.path().is_empty() && uri.path() != "/"
            || uri.query().is_some()
            || raw.contains('#')
        {
            return Err("UEC_CORS_ORIGINS must contain bare http(s) origins");
        }
        origins.push(
            raw.parse::<HeaderValue>()
                .map_err(|_| "UEC_CORS_ORIGINS contains an invalid header value")?,
        );
    }
    if origins.is_empty() {
        return Err("UEC_CORS_ORIGINS must contain at least one origin");
    }
    Ok(origins)
}

fn cors_layer() -> Result<CorsLayer, &'static str> {
    let mode = std::env::var("UEC_RUNTIME_MODE").unwrap_or_else(|_| "development".into());
    let origins = parse_cors_origins(
        mode.as_str(),
        std::env::var("UEC_CORS_ORIGINS").ok().as_deref(),
        std::env::var("UEC_CORS_ORIGIN").ok().as_deref(),
    )?;
    Ok(CorsLayer::new()
        .allow_origin(AllowOrigin::list(origins))
        .allow_methods([Method::GET, Method::OPTIONS])
        .allow_headers([axum::http::header::CONTENT_TYPE, axum::http::header::ACCEPT]))
}

const RATE_WINDOW: Duration = Duration::from_secs(60);
const RATE_LIMIT: u32 = 60;
#[derive(Clone, Default)]
struct Limiter(Arc<Mutex<HashMap<String, (Instant, u32)>>>);

#[derive(Clone)]
struct RateLimitState {
    limiter: Limiter,
    trust_proxy: bool,
}

impl Limiter {
    fn allow(&self, key: String, now: Instant) -> bool {
        let mut entries = self.0.lock().expect("rate limiter mutex poisoned");
        entries.retain(|_, (started, _)| now.duration_since(*started) < RATE_WINDOW);
        let entry = entries.entry(key).or_insert((now, 0));
        if now.duration_since(entry.0) >= RATE_WINDOW {
            *entry = (now, 0);
        }
        entry.1 += 1;
        entry.1 <= RATE_LIMIT
    }
}

fn client_key(request: &Request<axum::body::Body>, trust_proxy: bool) -> Option<String> {
    if trust_proxy {
        if let Some(ip) = request
            .headers()
            .get("x-forwarded-for")
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.split(',').next())
            .and_then(|value| value.trim().parse::<IpAddr>().ok())
        {
            return Some(format!("proxy:{ip}"));
        }
    }
    request
        .extensions()
        .get::<ConnectInfo<SocketAddr>>()
        .map(|ConnectInfo(peer)| format!("peer:{}", peer.ip()))
}

async fn rate_limit(
    State(config): State<RateLimitState>,
    request: Request<axum::body::Body>,
    next: axum::middleware::Next,
) -> Response<axum::body::Body> {
    if request.uri().path().starts_with("/health/") {
        return next.run(request).await;
    }
    let Some(key) = client_key(&request, config.trust_proxy) else {
        return StatusCode::SERVICE_UNAVAILABLE.into_response();
    };
    if !config.limiter.allow(key, Instant::now()) {
        return Response::builder()
            .status(StatusCode::TOO_MANY_REQUESTS)
            .header(header::RETRY_AFTER, RATE_WINDOW.as_secs().to_string())
            .header(header::CONTENT_TYPE, "application/json")
            .body(axum::body::Body::from(
                r#"{"api_version":"v2","error":{"code":"rate_limited","message":"request rate limit exceeded"}}"#,
            ))
            .unwrap();
    }
    next.run(request).await
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
    if let Err(error) = parse_cors_origins(
        mode.as_str(),
        std::env::var("UEC_CORS_ORIGINS").ok().as_deref(),
        std::env::var("UEC_CORS_ORIGIN").ok().as_deref(),
    ) {
        eprintln!(
            "{{\"event\":\"configuration_error\",\"reason\":\"{}\"}}",
            error
        );
        std::process::exit(2);
    }
    let database = database_url.and_then(|url| {
        let mut config = Config::new();
        config.url = Some(url);
        config.manager = Some(ManagerConfig {
            recycling_method: RecyclingMethod::Fast,
        });
        let pool = if mode == "production" {
            let _ = rustls::crypto::ring::default_provider().install_default();
            match config.create_pool(
                Some(Runtime::Tokio1),
                MakeRustlsConnect::with_webpki_roots(),
            ) {
                Ok(pool) => Ok(pool),
                Err(error) => Err(error),
            }
        } else {
            config.create_pool(Some(Runtime::Tokio1), NoTls)
        };
        match pool {
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
    axum::serve(
        listener,
        app(uec_api::ApiState { database }).into_make_service_with_connect_info::<SocketAddr>(),
    )
    .await
    .unwrap();
}

#[cfg(test)]
mod config_tests {
    use super::{parse_cors_origins, validate_runtime};
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
    #[test]
    fn cors_requires_narrow_production_allowlist() {
        assert!(parse_cors_origins("production", None, None).is_err());
        assert!(parse_cors_origins("production", Some("*"), None).is_err());
        assert!(parse_cors_origins("production", Some("https://example.test/path"), None).is_err());
        assert_eq!(
            parse_cors_origins(
                "production",
                Some("https://example.test,https://research.test"),
                None
            )
            .unwrap()
            .len(),
            2
        );
        assert_eq!(
            parse_cors_origins("development", None, None).unwrap().len(),
            1
        );
    }
}

#[cfg(test)]
mod rate_limit_tests {
    use super::*;
    use tower::ServiceExt;
    #[test]
    fn enforces_limit_and_resets_window() {
        let limiter = Limiter::default();
        let start = Instant::now();
        for _ in 0..RATE_LIMIT {
            assert!(limiter.allow("synthetic".into(), start));
        }
        assert!(!limiter.allow("synthetic".into(), start));
        assert!(limiter.allow(
            "synthetic".into(),
            start + RATE_WINDOW + Duration::from_secs(1)
        ));
    }
    #[test]
    fn separate_keys_are_independent_and_expired_entries_cleanup() {
        let limiter = Limiter::default();
        let start = Instant::now();
        assert!(limiter.allow("a".into(), start));
        assert!(limiter.allow("b".into(), start));
        let later = start + RATE_WINDOW + Duration::from_secs(1);
        assert!(limiter.allow("c".into(), later));
        assert_eq!(limiter.0.lock().unwrap().len(), 1);
    }

    #[tokio::test]
    async fn distinct_socket_peers_do_not_share_default_allowance() {
        let router = Router::new()
            .route("/asset.js", get(|| async { StatusCode::OK }))
            .layer(axum::middleware::from_fn_with_state(
                RateLimitState {
                    limiter: Limiter::default(),
                    trust_proxy: false,
                },
                rate_limit,
            ));
        let first: SocketAddr = "192.0.2.10:41000".parse().unwrap();
        let second: SocketAddr = "192.0.2.11:41000".parse().unwrap();
        for _ in 0..RATE_LIMIT {
            let mut request = Request::builder()
                .uri("/asset.js")
                .header("x-forwarded-for", "203.0.113.99")
                .body(axum::body::Body::empty())
                .unwrap();
            request.extensions_mut().insert(ConnectInfo(first));
            assert_eq!(
                router.clone().oneshot(request).await.unwrap().status(),
                StatusCode::OK
            );
        }
        let mut first_request = Request::builder()
            .uri("/asset.js")
            .body(axum::body::Body::empty())
            .unwrap();
        first_request.extensions_mut().insert(ConnectInfo(first));
        assert_eq!(
            router
                .clone()
                .oneshot(first_request)
                .await
                .unwrap()
                .status(),
            StatusCode::TOO_MANY_REQUESTS
        );
        let mut second_request = Request::builder()
            .uri("/asset.js")
            .header("x-forwarded-for", "203.0.113.99")
            .body(axum::body::Body::empty())
            .unwrap();
        second_request.extensions_mut().insert(ConnectInfo(second));
        assert_eq!(
            router.oneshot(second_request).await.unwrap().status(),
            StatusCode::OK
        );
    }

    #[test]
    fn proxy_header_requires_explicit_trust_and_valid_ip() {
        let peer: SocketAddr = "192.0.2.10:41000".parse().unwrap();
        let mut request = Request::builder()
            .uri("/asset.js")
            .header("x-forwarded-for", "198.51.100.20, 192.0.2.10")
            .body(axum::body::Body::empty())
            .unwrap();
        request.extensions_mut().insert(ConnectInfo(peer));
        assert_eq!(
            client_key(&request, false).as_deref(),
            Some("peer:192.0.2.10")
        );
        assert_eq!(
            client_key(&request, true).as_deref(),
            Some("proxy:198.51.100.20")
        );

        request.headers_mut().insert(
            "x-forwarded-for",
            HeaderValue::from_static("invalid, 198.51.100.20"),
        );
        assert_eq!(
            client_key(&request, true).as_deref(),
            Some("peer:192.0.2.10")
        );
    }

    #[tokio::test]
    async fn missing_peer_does_not_create_a_shared_allowance() {
        let router = Router::new()
            .route("/asset.js", get(|| async { StatusCode::OK }))
            .layer(axum::middleware::from_fn_with_state(
                RateLimitState {
                    limiter: Limiter::default(),
                    trust_proxy: false,
                },
                rate_limit,
            ));
        let request = Request::builder()
            .uri("/asset.js")
            .header("x-forwarded-for", "198.51.100.20")
            .body(axum::body::Body::empty())
            .unwrap();
        assert_eq!(
            router.oneshot(request).await.unwrap().status(),
            StatusCode::SERVICE_UNAVAILABLE
        );
    }
}
