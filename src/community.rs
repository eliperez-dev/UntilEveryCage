//! Account-free community intake. Submitted material stays restricted; the
//! public endpoints can only expose operator-linked rows in the live release
//! projection, which rechecks the current privacy and publication gates.
use crate::{v2_error, ApiState};
use axum::{
    extract::rejection::{JsonRejection, PathRejection, QueryRejection},
    extract::{DefaultBodyLimit, Extension, Path, Query, State},
    http::{HeaderMap, HeaderValue, StatusCode},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::{NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use uuid::Uuid;

const MAX_BODY: usize = 12 * 1024;
const WARNING: &str = "Community-submitted claim — unreviewed and not verified or project-approved by Until Every Cage.";
const ISO_3166_ALPHA2: &str = "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW";

#[derive(Clone)]
pub struct CommunityConfig {
    pub enabled: bool,
    pub public_enabled: bool,
    pub retention_days: i64,
    pub contact_retention_days: i64,
    pub receipt_days: i64,
    pub daily_intake_cap: i64,
    pub pending_cap: i64,
    operator_token: Option<String>,
}

impl CommunityConfig {
    pub fn disabled() -> Self {
        Self {
            enabled: false,
            public_enabled: false,
            retention_days: 0,
            contact_retention_days: 0,
            receipt_days: 0,
            daily_intake_cap: 0,
            pending_cap: 0,
            operator_token: None,
        }
    }

    /// Construct an injected local-pilot configuration for tests and callers
    /// that already parsed their settings; no process environment mutation is
    /// needed.
    pub fn local_pilot(
        public_enabled: bool,
        retention_days: i64,
        contact_retention_days: i64,
        receipt_days: i64,
        daily_intake_cap: i64,
        pending_cap: i64,
        operator_token: String,
    ) -> Result<Self, String> {
        if retention_days <= 0
            || contact_retention_days <= 0
            || receipt_days <= 0
            || daily_intake_cap <= 0
            || pending_cap <= 0
        {
            return Err("community retention and capacity values must be positive".into());
        }
        if contact_retention_days > retention_days
            || receipt_days > retention_days
            || retention_days > 365
            || contact_retention_days > 365
            || daily_intake_cap > 1000
            || pending_cap > 10000
        {
            return Err("community limits exceed the configured safe maximum".into());
        }
        if !(32..=512).contains(&operator_token.len()) {
            return Err("UEC_COMMUNITY_OPERATOR_TOKEN must be 32 to 512 bytes".into());
        }
        Ok(Self {
            enabled: true,
            public_enabled,
            retention_days,
            contact_retention_days,
            receipt_days,
            daily_intake_cap,
            pending_cap,
            operator_token: Some(operator_token),
        })
    }

    /// Parse configuration once at startup. The disabled default needs no
    /// secrets. This sprint deliberately fails closed in production.
    pub fn from_env(mode: &str) -> Result<Self, String> {
        fn bool_env(name: &str, default: bool) -> Result<bool, String> {
            match std::env::var(name) {
                Err(std::env::VarError::NotPresent) => Ok(default),
                Err(_) => Err(format!("{name} is not valid UTF-8")),
                Ok(value) => match value.as_str() {
                    "true" => Ok(true),
                    "false" => Ok(false),
                    _ => Err(format!("{name} must be true or false")),
                },
            }
        }
        fn positive(name: &str) -> Result<i64, String> {
            let value = std::env::var(name)
                .map_err(|_| format!("{name} is required when community intake is enabled"))?;
            let parsed = value
                .parse::<i64>()
                .map_err(|_| format!("{name} must be a positive integer"))?;
            if parsed <= 0 {
                return Err(format!("{name} must be a positive integer"));
            }
            Ok(parsed)
        }
        let enabled = bool_env("UEC_COMMUNITY_ENABLED", false)?;
        let public_enabled = bool_env("UEC_COMMUNITY_PUBLIC_ENABLED", false)?;
        if !enabled {
            if public_enabled {
                return Err("public community claims require enabled intake".into());
            }
            return Ok(Self::disabled());
        }
        if mode.eq_ignore_ascii_case("production") {
            return Err("community intake is disabled in production for this release".into());
        }
        let retention_days = positive("UEC_COMMUNITY_RETENTION_DAYS")?;
        let contact_retention_days = positive("UEC_COMMUNITY_CONTACT_RETENTION_DAYS")?;
        let receipt_days = positive("UEC_COMMUNITY_RECEIPT_DAYS")?;
        let daily_intake_cap = positive("UEC_COMMUNITY_DAILY_INTAKE_CAP")?;
        let pending_cap = positive("UEC_COMMUNITY_PENDING_CAP")?;
        let token = std::env::var("UEC_COMMUNITY_OPERATOR_TOKEN").map_err(|_| {
            "UEC_COMMUNITY_OPERATOR_TOKEN is required when community intake is enabled".to_string()
        })?;
        Self::local_pilot(
            public_enabled,
            retention_days,
            contact_retention_days,
            receipt_days,
            daily_intake_cap,
            pending_cap,
            token,
        )
    }
}

pub fn routes(config: CommunityConfig) -> Router<ApiState> {
    Router::new()
        .route("/api/community/submissions", post(create_submission))
        .route("/api/community/status", post(submission_status))
        .route("/api/private/community/submissions", get(queue))
        .route(
            "/api/private/community/submissions/{submission_id}/disposition",
            post(disposition),
        )
        .route("/api/private/community/maintenance", post(maintenance))
        .route("/api/community/claims", get(public_claims))
        .route("/api/community/claims/{submission_id}", get(public_claim))
        .layer(DefaultBodyLimit::max(MAX_BODY))
        .layer(Extension(CommunityState { config }))
        .layer(middleware::from_fn(no_store))
}

#[derive(Clone)]
struct CommunityState {
    config: CommunityConfig,
}

async fn no_store(request: axum::extract::Request, next: Next) -> Response {
    let mut response = next.run(request).await;
    response.headers_mut().insert(
        "cache-control",
        HeaderValue::from_static("no-store, max-age=0"),
    );
    response
        .headers_mut()
        .insert("pragma", HeaderValue::from_static("no-cache"));
    response
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SubmissionInput {
    pub kind: String,
    pub target_record_id: Option<Uuid>,
    pub duplicate_record_id: Option<Uuid>,
    pub label: Option<String>,
    pub country_code: Option<String>,
    pub locality: Option<String>,
    pub claimed_activity: Option<String>,
    pub location_text: Option<String>,
    pub claimed_latitude: Option<f64>,
    pub claimed_longitude: Option<f64>,
    pub claimed_precision: Option<String>,
    pub location_input_method: Option<String>,
    pub source_url: Option<String>,
    pub observed_on: Option<String>,
    pub description: Option<String>,
    pub contact_email: Option<String>,
    pub consent: bool,
}

fn nonblank(value: &Option<String>, max: usize) -> bool {
    value
        .as_ref()
        .is_some_and(|s| !s.trim().is_empty() && s.len() <= max)
}
fn valid_url(value: &str) -> bool {
    if value.len() > 2048
        || value.trim() != value
        || value.chars().any(|c| c.is_control() || c.is_whitespace())
    {
        return false;
    }
    let Ok(url) = reqwest::Url::parse(value) else {
        return false;
    };
    matches!(url.scheme(), "http" | "https")
        && url.host_str().is_some_and(|host| !host.is_empty())
        && url.username().is_empty()
        && url.password().is_none()
}
fn valid_email(value: &str) -> bool {
    value.len() <= 254
        && !value.chars().any(char::is_control)
        && value.split_once('@').is_some_and(|(local, domain)| {
            !local.is_empty()
                && local.len() <= 64
                && domain.contains('.')
                && !domain.starts_with('.')
                && !domain.ends_with('.')
                && !value.contains(' ')
        })
}
fn validate(input: &SubmissionInput) -> Result<(), &'static str> {
    if ![
        "facility",
        "evidence",
        "correction",
        "duplicate",
        "privacy_removal",
    ]
    .contains(&input.kind.as_str())
    {
        return Err("kind is invalid");
    }
    if !input.consent {
        return Err("consent must be true");
    }
    if input.label.as_ref().is_some_and(|v| v.len() > 160)
        || input.locality.as_ref().is_some_and(|v| v.len() > 160)
        || input
            .claimed_activity
            .as_ref()
            .is_some_and(|v| v.len() > 160)
        || input.location_text.as_ref().is_some_and(|v| v.len() > 1000)
        || input.description.as_ref().is_some_and(|v| v.len() > 2000)
    {
        return Err("one or more fields exceed their length limit");
    }
    if input.country_code.as_ref().is_some_and(|v| {
        v != "unknown" && !ISO_3166_ALPHA2.split_whitespace().any(|code| code == v)
    }) {
        return Err("country_code must be an uppercase two-letter code");
    }
    if input.claimed_latitude.is_some() != input.claimed_longitude.is_some() {
        return Err("latitude and longitude must be provided together");
    }
    if input
        .claimed_latitude
        .is_some_and(|v| !v.is_finite() || !(-90.0..=90.0).contains(&v))
        || input
            .claimed_longitude
            .is_some_and(|v| !v.is_finite() || !(-180.0..=180.0).contains(&v))
    {
        return Err("claimed coordinates are out of range");
    }
    if input
        .claimed_precision
        .as_ref()
        .is_some_and(|v| !["unknown", "exact", "coarse", "unmapped"].contains(&v.as_str()))
    {
        return Err("claimed_precision is invalid");
    }
    if input.claimed_latitude.is_some() && input.claimed_precision.as_deref() == Some("unmapped") {
        return Err("unmapped precision cannot include coordinates");
    }
    if input
        .location_input_method
        .as_ref()
        .is_some_and(|v| !["manual_pin", "text", "unknown"].contains(&v.as_str()))
    {
        return Err("location_input_method is invalid");
    }
    if input.location_input_method.as_deref() == Some("manual_pin")
        && input.claimed_latitude.is_none()
    {
        return Err("manual_pin requires a claimed coordinate pair");
    }
    if input.source_url.as_ref().is_some_and(|v| !valid_url(v)) {
        return Err("source_url must be an http(s) URL without credentials");
    }
    if input
        .observed_on
        .as_ref()
        .is_some_and(|v| NaiveDate::parse_from_str(v, "%Y-%m-%d").is_err())
    {
        return Err("observed_on must be an ISO date");
    }
    if input
        .contact_email
        .as_ref()
        .is_some_and(|v| !valid_email(v))
    {
        return Err("contact_email is invalid");
    }
    match input.kind.as_str() {
        "facility" if !nonblank(&input.label, 160) => Err("facility requires a label"),
        "evidence"
            if input.target_record_id.is_none()
                || (input.source_url.is_none() && !nonblank(&input.description, 2000)) =>
        {
            Err("evidence requires target_record_id and a description or source_url")
        }
        "correction" | "privacy_removal"
            if input.target_record_id.is_none() || !nonblank(&input.description, 2000) =>
        {
            Err("this submission requires target_record_id and description")
        }
        "duplicate"
            if input.target_record_id.is_none()
                || input.duplicate_record_id.is_none()
                || input.target_record_id == input.duplicate_record_id =>
        {
            Err("duplicate requires two distinct record IDs")
        }
        _ => Ok(()),
    }
}

fn restricted_claim(input: &SubmissionInput) -> Result<Value, serde_json::Error> {
    let mut claim = serde_json::to_value(input)?;
    if let Some(fields) = claim.as_object_mut() {
        fields.retain(|name, value| name != "contact_email" && !value.is_null());
        if fields.get("country_code").and_then(Value::as_str) == Some("unknown") {
            fields.remove("country_code");
        }
    }
    Ok(claim)
}

fn disabled() -> Response {
    v2_error(
        StatusCode::NOT_FOUND,
        "community_unavailable",
        "community intake unavailable",
    )
}
fn unavailable() -> Response {
    v2_error(
        StatusCode::SERVICE_UNAVAILABLE,
        "community_unavailable",
        "community service unavailable",
    )
}
fn bad(message: &'static str) -> Response {
    v2_error(
        StatusCode::BAD_REQUEST,
        "invalid_community_submission",
        message,
    )
}
fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    let n = a.len().max(b.len());
    let mut difference = a.len() ^ b.len();
    for i in 0..n {
        difference |= (a.get(i).copied().unwrap_or(0) ^ b.get(i).copied().unwrap_or(0)) as usize;
    }
    difference == 0
}
fn operator_ok(config: &CommunityConfig, headers: &HeaderMap) -> bool {
    let Some(expected) = config.operator_token.as_deref() else {
        return false;
    };
    let Some(got) = headers
        .get(axum::http::header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
    else {
        return false;
    };
    constant_time_eq(expected.as_bytes(), got.as_bytes())
}
async fn pool(state: &ApiState) -> Result<deadpool_postgres::Client, Response> {
    state
        .database
        .as_ref()
        .ok_or_else(unavailable)?
        .get()
        .await
        .map_err(|_| unavailable())
}

async fn create_submission(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    body: Result<Json<SubmissionInput>, JsonRejection>,
) -> Response {
    if !cs.config.enabled {
        return disabled();
    }
    let Ok(Json(input)) = body else {
        return bad("request body is invalid or too large");
    };
    if let Err(message) = validate(&input) {
        return bad(message);
    }
    let Ok(mut client) = pool(&api).await else {
        return unavailable();
    };
    let Ok(tx) = client.transaction().await else {
        return unavailable();
    };
    if tx
        .query_one("SELECT pg_advisory_xact_lock(638217, 4)", &[])
        .await
        .is_err()
    {
        return unavailable();
    }
    let _ = tx
        .execute(
            "DELETE FROM uec.community_submission_contacts WHERE expires_at <= now()",
            &[],
        )
        .await;
    let counts = tx.query_one("SELECT count(*) FILTER (WHERE created_at >= current_date)::bigint, count(*) FILTER (WHERE status IN ('received','held'))::bigint FROM uec.community_submissions", &[]).await;
    let Ok(counts) = counts else {
        return unavailable();
    };
    if counts.get::<_, i64>(0) >= cs.config.daily_intake_cap
        || counts.get::<_, i64>(1) >= cs.config.pending_cap
    {
        return (StatusCode::TOO_MANY_REQUESTS, Json(json!({"error":{"code":"community_intake_limited","message":"community intake is temporarily at capacity"}}))).into_response();
    }
    let submission_id = Uuid::new_v4();
    let receipt = Uuid::new_v4().to_string();
    let receipt_hash = digest(receipt.as_bytes());
    let claim = match restricted_claim(&input) {
        Ok(v) => v,
        Err(_) => return unavailable(),
    };
    let claim_text = claim.to_string();
    let insert = tx.execute("INSERT INTO uec.community_submissions(submission_id,kind,status,claim,receipt_secret_sha256,receipt_expires_at) VALUES($1,$2,'received',$3::text::jsonb,$4,now()+($5::bigint*interval '1 day'))", &[&submission_id,&input.kind,&claim_text,&receipt_hash,&cs.config.receipt_days]).await;
    if insert.is_err() {
        return unavailable();
    }
    if let Some(email) = input.contact_email.as_deref() {
        if tx.execute("INSERT INTO uec.community_submission_contacts(submission_id,email,expires_at) VALUES($1,$2,now()+($3::bigint*interval '1 day'))", &[&submission_id,&email,&cs.config.contact_retention_days]).await.is_err() { return unavailable(); }
    }
    if tx.execute("INSERT INTO uec.community_submission_events(submission_id,action,reason_code,actor_role) VALUES($1,'received','intake_received','system')", &[&submission_id]).await.is_err() || tx.commit().await.is_err() { return unavailable(); }
    (
        StatusCode::CREATED,
        Json(json!({"submission_id":submission_id,"receipt_secret":receipt,"status":"received"})),
    )
        .into_response()
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReceiptRequest {
    submission_id: Uuid,
    receipt_secret: String,
}
async fn submission_status(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    body: Result<Json<ReceiptRequest>, JsonRejection>,
) -> Response {
    if !cs.config.enabled {
        return disabled();
    }
    let Ok(Json(req)) = body else {
        return receipt_not_found();
    };
    if req.receipt_secret.len() > 80 {
        return receipt_not_found();
    }
    let Ok(client) = pool(&api).await else {
        return unavailable();
    };
    let row = client.query_opt("SELECT status, receipt_secret_sha256, receipt_expires_at, linked_source_record_id, linked_release_id FROM uec.community_submissions WHERE submission_id=$1", &[&req.submission_id]).await;
    let Ok(Some(row)) = row else {
        return receipt_not_found();
    };
    let status: String = row.get(0);
    let expected: Option<String> = row.get(1);
    let expires: chrono::DateTime<Utc> = row.get(2);
    if expires <= Utc::now()
        || expected.as_deref().is_none_or(|hash| {
            !constant_time_eq(
                hash.as_bytes(),
                digest(req.receipt_secret.as_bytes()).as_bytes(),
            )
        })
    {
        return receipt_not_found();
    }
    let mut body = json!({"submission_id":req.submission_id,"status":status});
    if cs.config.public_enabled && status == "published" {
        let source: Option<Uuid> = row.get(3);
        let release: Option<String> = row.get(4);
        if let (Some(source), Some(release)) = (source, release) {
            if let Some(claim) = eligible_claim(&client, req.submission_id, &source, &release).await
            {
                body["public_record_url"] = json!(claim.public_record_url);
            }
        }
    }
    Json(body).into_response()
}
fn receipt_not_found() -> Response {
    v2_error(
        StatusCode::NOT_FOUND,
        "community_receipt_not_found",
        "submission status unavailable",
    )
}

#[derive(Deserialize)]
struct QueueQuery {
    limit: Option<i64>,
    status: Option<String>,
}
async fn queue(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    headers: HeaderMap,
    query: Result<Query<QueueQuery>, QueryRejection>,
) -> Response {
    if !cs.config.enabled || !operator_ok(&cs.config, &headers) {
        return disabled();
    }
    let Ok(Query(q)) = query else {
        return bad("query parameters are invalid");
    };
    let limit = q.limit.unwrap_or(50);
    if !(1..=50).contains(&limit) {
        return bad("limit must be between 1 and 50");
    }
    if q.status.as_ref().is_some_and(|s| {
        ![
            "received",
            "held",
            "screened",
            "rejected",
            "restricted",
            "removed",
            "published",
        ]
        .contains(&s.as_str())
    }) {
        return bad("status is invalid");
    }
    let Ok(client) = pool(&api).await else {
        return unavailable();
    };
    let rows=client.query("SELECT submission_id,kind,status,claim::text,created_at,updated_at FROM uec.community_submissions WHERE (($1::text IS NOT NULL AND status=$1) OR ($1::text IS NULL AND status IN ('received','held'))) ORDER BY created_at,submission_id LIMIT $2", &[&q.status,&limit]).await;
    let Ok(rows) = rows else { return unavailable() };
    let pending: i64 = client
        .query_one(
            "SELECT count(*) FROM uec.community_submissions WHERE status IN ('received','held')",
            &[],
        )
        .await
        .map(|r| r.get(0))
        .unwrap_or(0);
    let submissions:Vec<Value>=rows.iter().map(|r|{let text:String=r.get(3);let claim:Value=serde_json::from_str(&text).unwrap_or_else(|_|json!({}));let mut item=json!({"submission_id":r.get::<_,Uuid>(0),"kind":r.get::<_,String>(1),"status":r.get::<_,String>(2),"created_at":r.get::<_,chrono::DateTime<Utc>>(4),"updated_at":r.get::<_,chrono::DateTime<Utc>>(5)});if let (Some(fields),Value::Object(claim_fields))=(item.as_object_mut(),claim){fields.extend(claim_fields);}item}).collect();
    Json(json!({"submissions":submissions,"pending_count":pending})).into_response()
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Disposition {
    action: String,
    reason_code: String,
    community_record_id: Option<Uuid>,
    release_id: Option<String>,
}
fn allowed_reason(reason: &str) -> bool {
    [
        "privacy",
        "abuse",
        "duplicate",
        "out_of_scope",
        "eligible",
        "other",
        "privacy_screened",
        "insufficient_information",
        "duplicate_claim",
        "abuse_or_targeting",
        "privacy_or_safety_concern",
        "operator_review",
        "eligible_existing_community_record",
        "removed_by_request",
    ]
    .contains(&reason)
}
async fn disposition(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    headers: HeaderMap,
    path: Result<Path<Uuid>, PathRejection>,
    body: Result<Json<Disposition>, JsonRejection>,
) -> Response {
    if !cs.config.enabled || !operator_ok(&cs.config, &headers) {
        return disabled();
    }
    let Ok(Path(id)) = path else {
        return bad("submission ID is invalid");
    };
    let Ok(Json(d)) = body else {
        return bad("disposition body is invalid or too large");
    };
    if !allowed_reason(&d.reason_code) {
        return bad("reason_code is invalid");
    }
    if ![
        "hold",
        "screen",
        "reject",
        "restrict",
        "remove",
        "link_community",
    ]
    .contains(&d.action.as_str())
    {
        return bad("action is invalid");
    }
    if (d.action == "link_community") != (d.community_record_id.is_some() && d.release_id.is_some())
    {
        return bad("link_community requires community_record_id and release_id");
    }
    if d.release_id.as_ref().is_some_and(|v| {
        v.is_empty()
            || v.len() > 160
            || !v
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
    }) {
        return bad("release_id is invalid");
    }
    let Ok(mut client) = pool(&api).await else {
        return unavailable();
    };
    let Ok(tx) = client.transaction().await else {
        return unavailable();
    };
    let current = tx
        .query_opt(
            "SELECT status,kind FROM uec.community_submissions WHERE submission_id=$1 FOR UPDATE",
            &[&id],
        )
        .await;
    let Ok(Some(row)) = current else {
        return receipt_not_found();
    };
    let old: String = row.get(0);
    let kind: String = row.get(1);
    if old == "removed" || (old == "restricted" && d.action != "remove") {
        return bad("restricted submissions cannot be changed through ordinary disposition");
    }
    if d.action == "link_community" && kind == "privacy_removal" {
        return bad(
            "privacy removal requests remain private and cannot be linked to public claims",
        );
    }
    if d.action == "link_community" && old != "screened" {
        return bad("submission must pass privacy screening before it can be linked");
    }
    let status = match d.action.as_str() {
        "hold" => "held",
        "screen" => "screened",
        "reject" => "rejected",
        "restrict" => "restricted",
        "remove" => "removed",
        "link_community" => "published",
        _ => unreachable!(),
    };
    if d.action == "link_community" {
        let source = d.community_record_id.unwrap();
        let release = d.release_id.as_ref().unwrap();
        let eligible=tx.query_opt("SELECT 1 FROM uec.map_facilities_public_discovery_read_model p JOIN uec.releases r ON r.release_id=p.release_id AND r.profile='community' AND r.status='promoted' AND r.test_only IS NOT TRUE JOIN uec.public_discovery_read_models m ON m.release_id=r.release_id JOIN uec.release_manifests manifest ON manifest.release_id=r.release_id AND manifest.manifest_sha256=m.manifest_sha256 WHERE p.source_record_id=$1 AND p.release_id=$2 AND p.provenance_origin_type='user_submitted' AND p.factual_review_status='unreviewed' AND p.privacy_screening_status='passed' AND p.maintainer_approval='pending' LIMIT 1",&[&source,&release]).await;
        if !matches!(eligible, Ok(Some(_))) {
            return bad("record must already be eligible in the selected community release");
        }
        if tx.execute("UPDATE uec.community_submissions SET status=$2,updated_at=now(),linked_source_record_id=$3,linked_release_id=$4 WHERE submission_id=$1",&[&id,&status,&source,&release]).await.is_err(){return unavailable()}
    } else {
        if d.action=="restrict" || d.action=="remove" {
            // Revoke links before removing submitted content. The exceptional
            // action explicitly deletes sensitive claim/contact data.
            if tx.execute("UPDATE uec.community_submissions SET status=$2,updated_at=now(),claim='{}'::jsonb,receipt_secret_sha256=NULL,linked_source_record_id=NULL,linked_release_id=NULL WHERE submission_id=$1",&[&id,&status]).await.is_err() || tx.execute("DELETE FROM uec.community_submission_contacts WHERE submission_id=$1",&[&id]).await.is_err(){return unavailable()}
        } else if tx.execute("UPDATE uec.community_submissions SET status=$2,updated_at=now() WHERE submission_id=$1",&[&id,&status]).await.is_err(){return unavailable()}
    }
    if tx.execute("INSERT INTO uec.community_submission_events(submission_id,action,reason_code,actor_role,release_id,source_record_id) VALUES($1,$2,$3,'operator',$4,$5)",&[&id,&d.action,&d.reason_code,&d.release_id,&d.community_record_id]).await.is_err()||tx.commit().await.is_err(){return unavailable()}
    Json(json!({"submission_id":id,"status":status})).into_response()
}

/// Explicit bounded retention maintenance. Returns aggregate counts only; it
/// clears expired contact/payload data, nulls receipt hashes, and keeps a
/// minimal tombstone plus payload-free decision history.
async fn maintenance(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    headers: HeaderMap,
) -> Response {
    if !cs.config.enabled || !operator_ok(&cs.config, &headers) {
        return disabled();
    }
    let Ok(mut client) = pool(&api).await else {
        return unavailable();
    };
    let Ok(tx) = client.transaction().await else {
        return unavailable();
    };
    let contacts = tx
        .execute(
            "DELETE FROM uec.community_submission_contacts WHERE expires_at<=now()",
            &[],
        )
        .await;
    let old_contacts=tx.execute("DELETE FROM uec.community_submission_contacts c USING uec.community_submissions s WHERE c.submission_id=s.submission_id AND s.created_at<now()-($1::bigint*interval '1 day')",&[&cs.config.retention_days]).await;
    let receipts=tx.execute("UPDATE uec.community_submissions SET receipt_secret_sha256=NULL WHERE receipt_secret_sha256 IS NOT NULL AND receipt_expires_at<=now()",&[]).await;
    let event_insert=tx.execute("INSERT INTO uec.community_submission_events(submission_id,action,reason_code,actor_role) SELECT submission_id,'expire','retention_expired','system' FROM uec.community_submissions WHERE created_at<now()-($1::bigint*interval '1 day') AND claim<>'{}'::jsonb",&[&cs.config.retention_days]).await;
    let submissions=tx.execute("UPDATE uec.community_submissions SET status='removed',claim='{}'::jsonb,receipt_secret_sha256=NULL,linked_source_record_id=NULL,linked_release_id=NULL,updated_at=now() WHERE created_at<now()-($1::bigint*interval '1 day') AND claim<>'{}'::jsonb",&[&cs.config.retention_days]).await;
    let (Ok(contacts), Ok(old_contacts), Ok(receipts), Ok(_), Ok(submissions)) =
        (contacts, old_contacts, receipts, event_insert, submissions)
    else {
        return unavailable();
    };
    if tx.commit().await.is_err() {
        return unavailable();
    }
    Json(json!({"contacts_expired":contacts+old_contacts,"receipts_expired":receipts,"submissions_expired":submissions})).into_response()
}

#[derive(Deserialize)]
struct PublicQuery {
    profile: Option<String>,
    release_id: Option<String>,
}
#[derive(Serialize)]
struct PublicClaim {
    submission_id: Uuid,
    kind: String,
    record_id: Uuid,
    release_id: String,
    public_record_url: String,
    origin: &'static str,
    factual_review_status: &'static str,
    project_approval: &'static str,
    warning: &'static str,
}
async fn eligible_claim(
    client: &deadpool_postgres::Client,
    id: Uuid,
    source: &Uuid,
    release: &str,
) -> Option<PublicClaim> {
    let row=client.query_opt("SELECT p.facility_id FROM uec.community_submissions s JOIN uec.map_facilities_public_discovery_read_model p ON p.source_record_id=s.linked_source_record_id AND p.release_id=s.linked_release_id JOIN uec.releases r ON r.release_id=p.release_id AND r.profile='community' AND r.status='promoted' AND r.test_only IS NOT TRUE JOIN uec.public_discovery_read_models m ON m.release_id=r.release_id JOIN uec.release_manifests manifest ON manifest.release_id=r.release_id AND manifest.manifest_sha256=m.manifest_sha256 WHERE s.submission_id=$1 AND s.status='published' AND s.linked_source_record_id=$2 AND s.linked_release_id=$3 AND p.provenance_origin_type='user_submitted' AND p.factual_review_status='unreviewed' AND p.privacy_screening_status='passed' AND p.maintainer_approval='pending' LIMIT 1",&[&id,source,&release]).await.ok()??;
    let facility: Uuid = row.get(0);
    let kind = client
        .query_one(
            "SELECT kind FROM uec.community_submissions WHERE submission_id=$1",
            &[&id],
        )
        .await
        .ok()?
        .get::<_, String>(0);
    Some(PublicClaim {
        submission_id: id,
        kind,
        record_id: facility,
        release_id: release.to_owned(),
        public_record_url: format!(
            "/api/v2/locations/{facility}?profile=community&release_id={release}"
        ),
        origin: "community-submitted",
        factual_review_status: "unreviewed",
        project_approval: "not-approved",
        warning: WARNING,
    })
}
fn valid_public_query(q: &PublicQuery) -> bool {
    q.profile.as_deref() == Some("community")
        && q.release_id.as_ref().is_some_and(|r| {
            !r.is_empty()
                && r.len() <= 160
                && r.bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
        })
}
async fn public_claims(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    query: Result<Query<PublicQuery>, QueryRejection>,
) -> Response {
    let Ok(Query(q)) = query else {
        return bad("query parameters are invalid");
    };
    if !cs.config.enabled || !cs.config.public_enabled {
        return disabled();
    };
    if !valid_public_query(&q) {
        return bad("profile=community and a release_id are required");
    }
    let Ok(client) = pool(&api).await else {
        return unavailable();
    };
    let release = q.release_id.unwrap();
    let ids=client.query("SELECT s.submission_id,s.linked_source_record_id FROM uec.community_submissions s WHERE s.status='published' AND s.linked_release_id=$1 ORDER BY s.updated_at,s.submission_id LIMIT 501",&[&release]).await;
    let Ok(ids) = ids else { return unavailable() };
    // This pilot intentionally caps the full linked candidate set at 500.
    // Fail closed instead of returning an incomplete list or count.
    if ids.len() > 500 {
        return unavailable();
    }
    let mut claims = Vec::new();
    for row in &ids {
        let id: Uuid = row.get(0);
        let source: Option<Uuid> = row.get(1);
        if let Some(source) = source {
            if let Some(c) = eligible_claim(&client, id, &source, &release).await {
                claims.push(c)
            }
        }
    }
    let count = claims.len();
    Json(json!({"claims":claims,"claim_count":count,"warning":WARNING})).into_response()
}
async fn public_claim(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    path: Result<Path<Uuid>, PathRejection>,
    query: Result<Query<PublicQuery>, QueryRejection>,
) -> Response {
    let Ok(Path(id)) = path else {
        return receipt_not_found();
    };
    let Ok(Query(q)) = query else {
        return bad("query parameters are invalid");
    };
    if !cs.config.enabled || !cs.config.public_enabled {
        return disabled();
    };
    if !valid_public_query(&q) {
        return bad("profile=community and a release_id are required");
    }
    let Ok(client) = pool(&api).await else {
        return unavailable();
    };
    let release = q.release_id.unwrap();
    let row=client.query_opt("SELECT linked_source_record_id FROM uec.community_submissions WHERE submission_id=$1 AND status='published' AND linked_release_id=$2",&[&id,&release]).await;
    let Ok(Some(row)) = row else {
        return receipt_not_found();
    };
    let source: Option<Uuid> = row.get(0);
    let Some(source) = source else {
        return receipt_not_found();
    };
    match eligible_claim(&client, id, &source, &release).await {
        Some(c) => Json(json!(c)).into_response(),
        None => receipt_not_found(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn sample(kind: &str) -> SubmissionInput {
        SubmissionInput {
            kind: kind.into(),
            target_record_id: None,
            duplicate_record_id: None,
            label: None,
            country_code: None,
            locality: None,
            claimed_activity: None,
            location_text: None,
            claimed_latitude: None,
            claimed_longitude: None,
            claimed_precision: None,
            location_input_method: None,
            source_url: None,
            observed_on: None,
            description: None,
            contact_email: None,
            consent: true,
        }
    }
    #[test]
    fn rejects_credentials_and_malformed_urls() {
        assert!(!valid_url("file:///etc/passwd"));
        assert!(!valid_url("https://user:secret@example.org/x"));
        assert!(!valid_url("https://example.org:invalid"));
        assert!(!valid_url("https://example.org:80:90/path"));
        assert!(!valid_url("https://example.org/has space"));
        assert!(valid_url("https://example.org/evidence"));
        assert!(valid_url("https://[2001:db8::1]:443/evidence"));
    }
    #[test]
    fn location_pairs_ranges_and_manual_pin_are_strict() {
        let mut x = sample("facility");
        x.label = Some("Synthetic facility".into());
        x.country_code = Some("DK".into());
        x.source_url = Some("https://example.org/source".into());
        x.claimed_latitude = Some(56.0);
        x.location_input_method = Some("manual_pin".into());
        assert!(validate(&x).is_err());
        x.claimed_longitude = Some(10.0);
        x.claimed_precision = Some("exact".into());
        assert!(validate(&x).is_ok());
        x.claimed_longitude = Some(181.0);
        assert!(validate(&x).is_err());
    }
    #[test]
    fn restricted_claim_omits_absent_fields_and_contact_but_keeps_precision() {
        let mut x = sample("facility");
        x.claimed_precision = Some("unmapped".into());
        x.contact_email = Some("synthetic@example.org".into());
        let claim = restricted_claim(&x).expect("serializes claim");
        let fields = claim.as_object().expect("claim object");
        assert!(!fields.contains_key("label"));
        assert!(!fields.contains_key("contact_email"));
        assert_eq!(
            fields.get("claimed_precision").and_then(Value::as_str),
            Some("unmapped")
        );
        assert_eq!(fields.get("consent").and_then(Value::as_bool), Some(true));
    }
    #[test]
    fn unmapped_precision_is_allowed_without_coordinates_only() {
        let mut x = sample("facility");
        x.label = Some("Synthetic facility".into());
        x.country_code = Some("DK".into());
        x.source_url = Some("https://example.org/source".into());
        x.claimed_precision = Some("unmapped".into());
        assert!(validate(&x).is_ok());

        x.claimed_latitude = Some(56.0);
        x.claimed_longitude = Some(10.0);
        assert!(validate(&x).is_err());

        x.claimed_precision = Some("coarse".into());
        assert!(validate(&x).is_ok());
    }
    #[test]
    fn all_submission_kinds_require_their_type_specific_fields() {
        let mut x = sample("facility");
        assert!(validate(&x).is_err());
        x.label = Some("Synthetic".into());
        x.country_code = Some("DK".into());
        x.source_url = Some("https://example.org".into());
        assert!(validate(&x).is_ok());
        let mut e = sample("evidence");
        e.target_record_id = Some(Uuid::nil());
        assert!(validate(&e).is_err());
        e.description = Some("Synthetic context without a source link".into());
        assert!(validate(&e).is_ok());
        e.description = None;
        e.source_url = Some("https://example.org/evidence".into());
        assert!(validate(&e).is_ok());
        let mut c = sample("correction");
        c.target_record_id = Some(Uuid::nil());
        c.description = Some("Synthetic correction".into());
        assert!(validate(&c).is_ok());
        let mut d = sample("duplicate");
        d.target_record_id = Some(Uuid::nil());
        d.duplicate_record_id = Some(Uuid::nil());
        assert!(validate(&d).is_err());
        d.duplicate_record_id = Some(Uuid::from_u128(2));
        assert!(validate(&d).is_ok());
        let mut p = sample("privacy_removal");
        p.target_record_id = Some(Uuid::nil());
        p.description = Some("Synthetic request".into());
        assert!(validate(&p).is_ok());
    }
    #[test]
    fn facility_country_and_source_are_optional_but_supplied_values_are_checked() {
        let mut x = sample("facility");
        x.label = Some("Synthetic facility".into());
        assert!(validate(&x).is_ok());

        x.country_code = Some("unknown".into());
        assert!(validate(&x).is_ok());
        let claim = restricted_claim(&x).expect("serializes unknown country as absent");
        assert!(!claim.as_object().unwrap().contains_key("country_code"));
        x.country_code = Some("DK".into());
        assert!(validate(&x).is_ok());
        x.country_code = Some("dk".into());
        assert!(validate(&x).is_err());
        x.country_code = None;

        x.source_url = Some("https://example.org/source".into());
        assert!(validate(&x).is_ok());
        x.source_url = Some("javascript:alert(1)".into());
        assert!(validate(&x).is_err());
        x.source_url = None;
        assert!(validate(&x).is_ok());
    }
    #[test]
    fn evidence_without_source_needs_target_and_nonblank_description() {
        let mut x = sample("evidence");
        x.target_record_id = Some(Uuid::nil());
        assert!(validate(&x).is_err());
        x.description = Some("   ".into());
        assert!(validate(&x).is_err());
        x.description = Some("Synthetic supporting context".into());
        assert!(validate(&x).is_ok());
        x.source_url = Some("https://example.org/evidence".into());
        x.description = None;
        assert!(validate(&x).is_ok());
        x.source_url = Some("file:///private".into());
        assert!(validate(&x).is_err());
    }
    #[test]
    fn credentials_contact_and_unknown_fields_are_separate_or_rejected() {
        let mut x = sample("facility");
        x.label = Some("Synthetic".into());
        x.country_code = Some("DK".into());
        x.source_url = Some("https://example.org".into());
        x.contact_email = Some("person@example.org".into());
        assert!(validate(&x).is_ok());
        assert!(serde_json::from_value::<SubmissionInput>(
            json!({"kind":"facility","consent":true,"operator_token":"secret"})
        )
        .is_err());
    }
    #[test]
    fn receipt_comparison_is_constant_work_over_longer_length() {
        assert!(constant_time_eq(b"abc", b"abc"));
        assert!(!constant_time_eq(b"abc", b"abd"));
        assert!(!constant_time_eq(b"abc", b"ab"));
    }
    #[test]
    fn public_profile_and_release_are_mandatory() {
        assert!(!valid_public_query(&PublicQuery {
            profile: None,
            release_id: Some("r1".into())
        }));
        assert!(!valid_public_query(&PublicQuery {
            profile: Some("official".into()),
            release_id: Some("r1".into())
        }));
        assert!(valid_public_query(&PublicQuery {
            profile: Some("community".into()),
            release_id: Some("r1".into())
        }));
    }
    #[test]
    fn injected_config_is_bounded_without_environment_mutation() {
        assert!(!CommunityConfig::disabled().enabled);
        assert!(CommunityConfig::local_pilot(
            false,
            30,
            7,
            14,
            20,
            100,
            "a sufficiently long operator token".into()
        )
        .is_ok());
        assert!(CommunityConfig::local_pilot(
            false,
            5,
            7,
            14,
            20,
            100,
            "a sufficiently long operator token".into()
        )
        .is_err());
        assert!(CommunityConfig::local_pilot(false, 30, 7, 14, 20, 100, "short".into()).is_err());
    }
    #[test]
    fn receipt_secret_cannot_authorize_operator_routes() {
        let config = CommunityConfig {
            enabled: true,
            public_enabled: false,
            retention_days: 30,
            contact_retention_days: 7,
            receipt_days: 14,
            daily_intake_cap: 5,
            pending_cap: 25,
            operator_token: Some("operator-secret-which-is-not-a-receipt".into()),
        };
        let mut headers = HeaderMap::new();
        headers.insert(
            axum::http::header::AUTHORIZATION,
            HeaderValue::from_static("Bearer contributor-receipt-secret"),
        );
        assert!(!operator_ok(&config, &headers));
        headers.insert(
            axum::http::header::AUTHORIZATION,
            HeaderValue::from_static("Bearer operator-secret-which-is-not-a-receipt"),
        );
        assert!(operator_ok(&config, &headers));
    }
    #[test]
    fn request_body_is_bounded() {
        assert!(MAX_BODY >= 10 * 1024 && MAX_BODY <= 16 * 1024);
    }
}
