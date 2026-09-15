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

mod private_environment;

pub fn app(state: uec_api::ApiState, proxy: private_environment::ProxyConfig) -> Router {
    let cors = cors_layer().expect("CORS configuration must be validated before app startup");
    Router::new()
        .route("/health/live", get(liveness))
        .route("/health/ready", get(readiness))
        .route("/health/diagnostics", get(diagnostics))
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
            "/api/dev/preview/candidates",
            get(uec_api::get_dev_candidate_preview_handler),
        )
        .route(
            "/api/dev/preview/test-release/locations",
            get(uec_api::get_dev_test_release_locations_handler),
        )
        .route(
            "/api/dev/preview/test-release/locations/{facility_id}",
            get(uec_api::get_dev_test_release_location_detail_handler),
        )
        .route(
            "/api/dev/preview/test-release/discovery/facets",
            get(uec_api::get_dev_test_release_facets_handler),
        )
        .route(
            "/api/dev/preview/test-release/locations.csv",
            get(uec_api::get_dev_test_release_export_handler),
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
                proxy,
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
        .allow_headers([
            axum::http::header::CONTENT_TYPE,
            axum::http::header::ACCEPT,
            axum::http::HeaderName::from_static("x-uec-dev-preview-token"),
        ]))
}

fn preview_config(
    mode: &str,
    opt_in: Option<&str>,
    bind_host: &str,
    token: Option<&str>,
    cors_origins: Option<&str>,
    legacy_cors_origin: Option<&str>,
) -> Result<Option<String>, &'static str> {
    let enabled = match opt_in.unwrap_or("false") {
        "true" => true,
        "false" | "" => false,
        _ => return Err("UEC_DEV_PREVIEW must be true or false"),
    };
    let host = bind_host
        .parse::<IpAddr>()
        .map_err(|_| "UEC_BIND_HOST must be a valid IP address")?;
    let token = token.filter(|value| !value.is_empty());
    if mode == "production" && (enabled || token.is_some()) {
        return Err("development candidate preview is unavailable in production");
    }
    if !enabled {
        if token.is_some() {
            return Err("UEC_DEV_PREVIEW_TOKEN requires UEC_DEV_PREVIEW=true");
        }
        return Ok(None);
    }
    if mode != "development" {
        return Err("candidate preview requires development runtime mode");
    }
    if !host.is_loopback() {
        return Err("candidate preview requires an exact loopback bind host");
    }
    let token = token.ok_or("UEC_DEV_PREVIEW_TOKEN is required when preview is enabled")?;
    let cors = cors_origins
        .or(legacy_cors_origin)
        .unwrap_or("http://localhost:3000");
    for origin in cors
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        let uri = origin
            .parse::<axum::http::Uri>()
            .map_err(|_| "candidate preview CORS origin is invalid")?;
        let origin_host = uri
            .host()
            .ok_or("candidate preview CORS origin must have a host")?;
        let origin_ip = origin_host.parse::<IpAddr>().ok();
        if !matches!(origin_host, "localhost") && !origin_ip.is_some_and(|ip| ip.is_loopback()) {
            return Err("candidate preview CORS origins must be loopback only");
        }
    }
    Ok(Some(token.to_owned()))
}

const RATE_WINDOW: Duration = Duration::from_secs(60);
const RATE_LIMIT: u32 = 60;
#[derive(Clone, Default)]
struct Limiter(Arc<Mutex<HashMap<String, (Instant, u32)>>>);

#[derive(Clone)]
struct RateLimitState {
    limiter: Limiter,
    proxy: private_environment::ProxyConfig,
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

fn client_key(
    request: &Request<axum::body::Body>,
    proxy: &private_environment::ProxyConfig,
) -> Option<String> {
    let trusted_peer = request
        .extensions()
        .get::<ConnectInfo<SocketAddr>>()
        .is_some_and(|ConnectInfo(peer)| {
            private_environment::peer_is_trusted_proxy(peer.ip(), proxy)
        });
    if proxy.trust_forwarded_for && trusted_peer {
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
    let Some(key) = client_key(&request, &config.proxy) else {
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

async fn diagnostics() -> impl IntoResponse {
    let mode = std::env::var("UEC_RUNTIME_MODE").unwrap_or_else(|_| "development".into());
    let database_configured = std::env::var("UEC_DATABASE_URL")
        .ok()
        .is_some_and(|url| !url.trim().is_empty());
    let proxy_trust = match std::env::var("UEC_TRUST_PROXY").as_deref() {
        Ok("true") => "enabled_with_configured_boundary",
        Ok("false") | Err(_) => "disabled",
        Ok(_) => "invalid_configuration",
    };
    Json(serde_json::json!({
        "status": "ok",
        "service": "uec-api",
        "runtime_mode": mode,
        "database_configured": database_configured,
        "proxy_trust": proxy_trust,
        "startup_gates": {
            "restriction_ledger": if mode == "production" { "verified" } else { "not_required_development" },
            "release_manifest": if mode == "production" { "verified" } else { "not_required_development" }
        },
        "privacy": {
            "request_payloads": "not_reported",
            "visitor_location": "not_reported",
            "diagnostic_identifiers": "excluded"
        }
    }))
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
        Ok(client) => match client.query_one(r#"
            WITH required_relations(name) AS (
                VALUES ('uec.releases'), ('uec.release_manifests'),
                       ('uec.map_facilities_display_history'),
                       ('uec.publication_review_release_current'),
                       ('uec.public_access_restricted')
            ), required_columns(schema_name, table_name, column_name) AS (
                VALUES ('uec','releases','release_id'), ('uec','releases','status'),
                       ('uec','releases','test_only'), ('uec','releases','profile'),
                       ('uec','releases','ruleset_version'), ('uec','releases','created_at'),
                       ('uec','release_manifests','release_id'), ('uec','release_manifests','manifest'),
                       ('uec','release_manifests','manifest_sha256'),
                       ('uec','map_facilities_display_history','facility_id'),
                       ('uec','map_facilities_display_history','release_id'),
                       ('uec','map_facilities_display_history','release_ruleset_version'),
                       ('uec','map_facilities_display_history','provenance_origin_type'),
                       ('uec','publication_review_release_current','source_record_id'),
                       ('uec','publication_review_release_current','release_id'),
                       ('uec','publication_review_release_current','factual_review_status'),
                       ('uec','publication_review_release_current','privacy_screening_status'),
                       ('uec','publication_review_release_current','maintainer_approval'),
                       ('uec','publication_review_release_current','publication_eligible'),
                       ('uec','public_access_restricted','source_record_id')
            )
            SELECT NOT EXISTS (
                SELECT 1 FROM required_relations
                WHERE to_regclass(name) IS NULL
            ) AND NOT EXISTS (
                SELECT 1 FROM required_columns required
                WHERE NOT EXISTS (
                    SELECT 1 FROM information_schema.columns found
                    WHERE found.table_schema = required.schema_name
                      AND found.table_name = required.table_name
                      AND found.column_name = required.column_name
                )
            )
        "#, &[]).await {
            Ok(row) if row.get::<_, bool>(0) => {
                Json(serde_json::json!({"status": "ready", "database": "ok", "schema": "migrated"})).into_response()
            }
            Ok(_) => (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({"status": "not_ready", "reason": "database_schema_not_migrated"})),
            )
                .into_response(),
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
    if mode == "production"
        && database_url
            .map(|url| url.trim().is_empty())
            .unwrap_or(true)
    {
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
    let bind_host = std::env::var("UEC_BIND_HOST").unwrap_or_else(|_| {
        if mode == "development" {
            "127.0.0.1".into()
        } else {
            "0.0.0.0".into()
        }
    });
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
    let proxy = private_environment::parse_proxy_config(
        mode.as_str(),
        std::env::var("UEC_TRUST_PROXY").ok().as_deref(),
        std::env::var("UEC_TRUSTED_PROXY_CIDRS").ok().as_deref(),
    )
    .unwrap_or_else(|error| {
        eprintln!(
            "{{\"event\":\"configuration_error\",\"reason\":\"{}\"}}",
            error
        );
        std::process::exit(2)
    });
    let startup_gate = private_environment::validate_startup(
        mode.as_str(),
        std::env::var("UEC_RESTRICTION_LEDGER_PATH").ok().as_deref(),
        std::env::var("UEC_RESTORED_RESTRICTION_SNAPSHOT_PATH")
            .ok()
            .as_deref(),
        std::env::var("UEC_RELEASE_MANIFEST_PATH").ok().as_deref(),
        std::env::var("UEC_RELEASE_MANIFEST_SHA256").ok().as_deref(),
    )
    .unwrap_or_else(|error| {
        eprintln!(
            "{{\"event\":\"configuration_error\",\"reason\":\"{}\"}}",
            error
        );
        std::process::exit(2)
    });
    let dev_preview_token = preview_config(
        mode.as_str(),
        std::env::var("UEC_DEV_PREVIEW").ok().as_deref(),
        &bind_host,
        std::env::var("UEC_DEV_PREVIEW_TOKEN").ok().as_deref(),
        std::env::var("UEC_CORS_ORIGINS").ok().as_deref(),
        std::env::var("UEC_CORS_ORIGIN").ok().as_deref(),
    )
    .unwrap_or_else(|error| {
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
    let addr = format!("{}:{}", bind_host, port);
    println!(
        "{{\"event\":\"server_starting\",\"service\":\"uec-api\",\"mode\":\"{}\",\"port\":{},\"restriction_ledger\":\"{}\",\"release_manifest\":\"{}\"}}",
        mode, port, startup_gate.restriction_ledger, startup_gate.release_manifest
    );
    let (dev_test_release_id, dev_test_release_token) = match (
        std::env::var("UEC_TEST_RELEASE_ID").ok(),
        std::env::var("UEC_TEST_RELEASE_TOKEN").ok(),
    ) {
        (None, None) => (None, None),
        (Some(id), Some(token))
            if mode == "development"
                && bind_host
                    .parse::<IpAddr>()
                    .map(|ip| ip.is_loopback())
                    .unwrap_or(false)
                && !id.is_empty()
                && !token.is_empty() =>
        {
            (Some(id), Some(token))
        }
        _ => {
            eprintln!(
                "{{\"event\":\"configuration_error\",\"reason\":\"test release requires development loopback mode and both UEC_TEST_RELEASE_ID/UEC_TEST_RELEASE_TOKEN\"}}"
            );
            std::process::exit(2);
        }
    };

    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(
        listener,
        app(
            uec_api::ApiState {
                database,
                dev_preview_token,
                dev_test_release_id,
                dev_test_release_token,
            },
            proxy,
        )
        .into_make_service_with_connect_info::<SocketAddr>(),
    )
    .await
    .unwrap();
}

#[cfg(test)]
mod config_tests {
    use super::{parse_cors_origins, preview_config, validate_runtime};
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
        assert_eq!(
            validate_runtime("production", Some("  "), "8000"),
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

    #[test]
    fn candidate_preview_requires_loopback_opt_in_and_token() {
        assert!(
            preview_config("development", Some("true"), "127.0.0.1", None, None, None).is_err()
        );
        assert!(
            preview_config(
                "development",
                Some("true"),
                "0.0.0.0",
                Some("secret"),
                None,
                None
            )
            .is_err()
        );
        assert!(
            preview_config(
                "production",
                Some("true"),
                "127.0.0.1",
                Some("secret"),
                None,
                None
            )
            .is_err()
        );
        assert!(
            preview_config(
                "development",
                Some("true"),
                "127.0.0.1",
                Some("secret"),
                Some("https://remote.example"),
                None
            )
            .is_err()
        );
        assert_eq!(
            preview_config(
                "development",
                Some("true"),
                "127.0.0.1",
                Some("secret"),
                None,
                None
            )
            .unwrap()
            .as_deref(),
            Some("secret")
        );
        assert_eq!(
            preview_config("development", None, "127.0.0.1", None, None, None).unwrap(),
            None
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
                    proxy: private_environment::parse_proxy_config("development", None, None)
                        .unwrap(),
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
            client_key(
                &request,
                &private_environment::parse_proxy_config("development", None, None).unwrap(),
            )
            .as_deref(),
            Some("peer:192.0.2.10")
        );
        assert_eq!(
            client_key(
                &request,
                &private_environment::parse_proxy_config(
                    "production",
                    Some("true"),
                    Some("192.0.2.0/24"),
                )
                .unwrap(),
            )
            .as_deref(),
            Some("proxy:198.51.100.20")
        );

        request.headers_mut().insert(
            "x-forwarded-for",
            HeaderValue::from_static("invalid, 198.51.100.20"),
        );
        assert_eq!(
            client_key(
                &request,
                &private_environment::parse_proxy_config(
                    "production",
                    Some("true"),
                    Some("192.0.2.0/24"),
                )
                .unwrap(),
            )
            .as_deref(),
            Some("peer:192.0.2.10")
        );

        let untrusted_peer: SocketAddr = "203.0.113.10:41000".parse().unwrap();
        request.extensions_mut().remove::<ConnectInfo<SocketAddr>>();
        request.extensions_mut().insert(ConnectInfo(untrusted_peer));
        request
            .headers_mut()
            .insert("x-forwarded-for", HeaderValue::from_static("198.51.100.20"));
        assert_eq!(
            client_key(
                &request,
                &private_environment::parse_proxy_config(
                    "production",
                    Some("true"),
                    Some("192.0.2.0/24"),
                )
                .unwrap(),
            )
            .as_deref(),
            Some("peer:203.0.113.10")
        );
    }

    #[tokio::test]
    async fn missing_peer_does_not_create_a_shared_allowance() {
        let router = Router::new()
            .route("/asset.js", get(|| async { StatusCode::OK }))
            .layer(axum::middleware::from_fn_with_state(
                RateLimitState {
                    limiter: Limiter::default(),
                    proxy: private_environment::parse_proxy_config("development", None, None)
                        .unwrap(),
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
