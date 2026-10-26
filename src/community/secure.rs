//! Experimental, local-only encrypted contribution inbox. This stores only
//! OpenPGP message armor and public keys; clients own encryption and signature
//! verification. Armor checks below are framing checks, not crypto validation.
use super::{CommunityState, constant_time_eq, no_store, operator_ok, pool};
use crate::{ApiState, v2_error};
use axum::{
    Json, Router,
    extract::{DefaultBodyLimit, Extension, State},
    http::{HeaderMap, StatusCode},
    middleware,
    response::{IntoResponse, Response},
    routing::{get, post},
};
use chrono::{DateTime, Utc};
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use uuid::Uuid;

const BODY_LIMIT: usize = 128 * 1024;
const MAX_KEY: usize = 16 * 1024;
const MAX_CIPHER: usize = 98_304;
const TOTAL_CIPHER_LIMIT: i64 = 64 * 1024 * 1024;
const MESSAGE_LIMIT: i64 = 32;
const LOCK_A: i32 = 638217;
const LOCK_B: i32 = 4;

#[derive(Clone)]
pub struct Config {
    pub(super) enabled: bool,
    reviewer_public_key: String,
    reviewer_fingerprint: String,
}

impl Config {
    pub fn disabled() -> Self {
        Self {
            enabled: false,
            reviewer_public_key: String::new(),
            reviewer_fingerprint: String::new(),
        }
    }

    pub fn from_env(mode: &str) -> Result<Self, String> {
        let enabled = match std::env::var("UEC_COMMUNITY_SECURE_ENABLED") {
            Err(std::env::VarError::NotPresent) => false,
            Err(_) => return Err("UEC_COMMUNITY_SECURE_ENABLED is not valid UTF-8".into()),
            Ok(v) if v == "true" => true,
            Ok(v) if v == "false" => false,
            Ok(_) => return Err("UEC_COMMUNITY_SECURE_ENABLED must be true or false".into()),
        };
        if !enabled {
            return Ok(Self::disabled());
        }
        require_local_mode(mode)?;
        let key = std::env::var("UEC_COMMUNITY_SECURE_REVIEWER_PUBLIC_KEY")
            .map_err(|_| "UEC_COMMUNITY_SECURE_REVIEWER_PUBLIC_KEY is required".to_string())?;
        let fp = std::env::var("UEC_COMMUNITY_SECURE_REVIEWER_FINGERPRINT")
            .map_err(|_| "UEC_COMMUNITY_SECURE_REVIEWER_FINGERPRINT is required".to_string())?;
        if !valid_public_key(&key) {
            return Err("reviewer key must be bounded public OpenPGP armor".into());
        }
        if !valid_fingerprint(&fp) {
            return Err(
                "reviewer fingerprint must be 40 or 64 lowercase hexadecimal characters".into(),
            );
        }
        Ok(Self {
            enabled,
            reviewer_public_key: key,
            reviewer_fingerprint: fp,
        })
    }
}

fn require_local_mode(mode: &str) -> Result<(), String> {
    if mode == "development" {
        Ok(())
    } else {
        Err(
            "secure community intake is experimental and unavailable outside local development"
                .into(),
        )
    }
}

pub fn routes() -> Router<ApiState> {
    Router::new()
        .route("/api/community/secure/capabilities", get(capabilities))
        .route("/api/community/secure/submissions", post(create_submission))
        .route("/api/community/secure/inbox", post(read_inbox))
        .route("/api/community/secure/messages", post(contributor_message))
        .route(
            "/api/private/community/secure/messages",
            post(reviewer_message),
        )
        .route("/api/private/community/secure/queue", get(queue))
        .route("/api/private/community/secure/inbox", post(reviewer_inbox))
        .route(
            "/api/private/community/secure/disposition",
            post(disposition),
        )
        .route(
            "/api/private/community/secure/maintenance",
            post(maintenance),
        )
        .layer(DefaultBodyLimit::max(BODY_LIMIT))
        .layer(middleware::from_fn(no_store))
}

fn enabled(cs: &CommunityState) -> bool {
    cs.config.enabled && cs.config.secure.enabled
}
fn fail(status: StatusCode, code: &'static str, message: &'static str) -> Response {
    v2_error(status, code, message)
}
fn off() -> Response {
    fail(
        StatusCode::NOT_FOUND,
        "community_unavailable",
        "community intake unavailable",
    )
}
fn unavailable_secure() -> Response {
    fail(
        StatusCode::SERVICE_UNAVAILABLE,
        "service_unavailable",
        "community service unavailable",
    )
}
fn bad_secure() -> Response {
    fail(
        StatusCode::BAD_REQUEST,
        "invalid_secure_submission",
        "encrypted submission is invalid",
    )
}
fn rejected_json(error: axum::extract::rejection::JsonRejection) -> Response {
    if error.status() == StatusCode::PAYLOAD_TOO_LARGE {
        fail(
            StatusCode::PAYLOAD_TOO_LARGE,
            "secure_payload_too_large",
            "encrypted request is too large",
        )
    } else {
        bad_secure()
    }
}
fn not_found() -> Response {
    fail(
        StatusCode::NOT_FOUND,
        "secure_inbox_not_found",
        "encrypted inbox unavailable",
    )
}
fn conflict() -> Response {
    fail(
        StatusCode::CONFLICT,
        "secure_inbox_conflict",
        "encrypted inbox request conflicts with existing state",
    )
}
fn limited() -> Response {
    fail(
        StatusCode::TOO_MANY_REQUESTS,
        "secure_inbox_limited",
        "encrypted inbox capacity reached",
    )
}
fn allowed_kind(s: &str) -> bool {
    matches!(
        s,
        "facility" | "evidence" | "correction" | "duplicate" | "privacy_removal" | "bug"
    )
}
fn valid_fingerprint(s: &str) -> bool {
    (s.len() == 40 || s.len() == 64)
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn valid_armor(s: &str, label: &str, max: usize) -> bool {
    s.len() >= 64
        && s.len() <= max
        && s.is_ascii()
        && !s.contains("PRIVATE KEY")
        && s.starts_with(&format!("-----BEGIN PGP {label}-----\n"))
        && s.ends_with(&format!("\n-----END PGP {label}-----\n"))
        && s.matches("-----BEGIN PGP ").count() == 1
        && s.matches("-----END PGP ").count() == 1
}
fn valid_public_key(s: &str) -> bool {
    valid_armor(s, "PUBLIC KEY BLOCK", MAX_KEY)
}
fn valid_cipher(s: &str) -> bool {
    valid_armor(s, "MESSAGE", MAX_CIPHER)
}
fn valid_secret(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn valid_id(id: Uuid) -> bool {
    (1..=8).contains(&id.get_version_num()) && id.get_variant() == uuid::Variant::RFC4122
}
fn active(status: &str) -> bool {
    matches!(status, "received" | "in_review" | "needs_information")
}
fn valid_status(s: &str) -> bool {
    matches!(s, "in_review" | "needs_information" | "closed" | "removed")
}
fn hash_secret(s: &str) -> String {
    format!("{:x}", Sha256::digest(s.as_bytes()))
}
fn hash_eq(a: &str, b: &str) -> bool {
    constant_time_eq(a.as_bytes(), b.as_bytes())
}

async fn capabilities(Extension(cs): Extension<CommunityState>) -> Response {
    if !cs.config.enabled {
        return off();
    }
    if !cs.config.secure.enabled {
        return Json(json!({"enabled":false})).into_response();
    }
    Json(json!({"enabled":true,"mode":"embedded_sdk","provider":"openpgpjs-self-hosted","protocol":"uec-openpgp-inbox-v1","security_status":"experimental_local_only","reviewer_public_key":cs.config.secure.reviewer_public_key,"reviewer_fingerprint":cs.config.secure.reviewer_fingerprint,"replies":true,"email_alerts":false,"max_ciphertext_bytes":MAX_CIPHER})).into_response()
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Submission {
    case_id: Uuid,
    initial_message_id: Uuid,
    kind: String,
    protocol: String,
    access_secret: String,
    contributor_public_key: String,
    contributor_fingerprint: String,
    reviewer_fingerprint: String,
    ciphertext: String,
}
fn valid_submission(x: &Submission, cs: &CommunityState) -> bool {
    valid_id(x.case_id)
        && valid_id(x.initial_message_id)
        && x.protocol == "uec-openpgp-inbox-v1"
        && allowed_kind(&x.kind)
        && valid_secret(&x.access_secret)
        && valid_public_key(&x.contributor_public_key)
        && valid_fingerprint(&x.contributor_fingerprint)
        && valid_fingerprint(&x.reviewer_fingerprint)
        && x.contributor_fingerprint != x.reviewer_fingerprint
        && hash_eq(
            &x.reviewer_fingerprint,
            &cs.config.secure.reviewer_fingerprint,
        )
        && valid_cipher(&x.ciphertext)
}

async fn create_submission(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    body: Result<Json<Submission>, axum::extract::rejection::JsonRejection>,
) -> Response {
    if !enabled(&cs) {
        return off();
    }
    let x = match body {
        Ok(Json(x)) => x,
        Err(e) => return rejected_json(e),
    };
    if !valid_submission(&x, &cs) {
        return bad_secure();
    }
    let Ok(mut client) = pool(&api).await else {
        return unavailable_secure();
    };
    let Ok(tx) = client.transaction().await else {
        return unavailable_secure();
    };
    if tx
        .query_one("SELECT pg_advisory_xact_lock($1,$2)", &[&LOCK_A, &LOCK_B])
        .await
        .is_err()
    {
        return unavailable_secure();
    }
    let secret_hash = hash_secret(&x.access_secret);
    let existing = tx.query_opt("SELECT i.kind,i.protocol,i.access_secret_sha256,i.contributor_public_key,i.contributor_fingerprint,i.reviewer_fingerprint,i.status,i.created_at,i.expires_at,m.message_id,m.ciphertext FROM uec.community_secure_inboxes i JOIN uec.community_secure_messages m ON m.case_id=i.case_id AND m.ordinal=1 WHERE i.case_id=$1", &[&x.case_id]).await;
    let Ok(existing) = existing else {
        return unavailable_secure();
    };
    if let Some(r) = existing {
        let same = r.get::<_, String>(0) == x.kind
            && r.get::<_, String>(1) == x.protocol
            && r.get::<_, Option<String>>(2)
                .as_deref()
                .is_some_and(|h| hash_eq(h, &secret_hash))
            && r.get::<_, String>(3) == x.contributor_public_key
            && r.get::<_, String>(4) == x.contributor_fingerprint
            && r.get::<_, String>(5) == x.reviewer_fingerprint
            && r.get::<_, Uuid>(9) == x.initial_message_id
            && r.get::<_, String>(10) == x.ciphertext;
        let status: String = r.get(6);
        let expires: DateTime<Utc> = r.get(8);
        if !same || !active(&status) || expires <= Utc::now() {
            return conflict();
        }
        let created: DateTime<Utc> = r.get(7);
        if tx.commit().await.is_err() {
            return unavailable_secure();
        }
        return (StatusCode::OK, Json(json!({"case_id":x.case_id,"status":status,"created_at":created,"expires_at":expires}))).into_response();
    }
    if expire_cases(&tx, cs.config.retention_days).await.is_err() {
        return unavailable_secure();
    }
    let counts = tx.query_one("SELECT (SELECT count(*) FROM uec.community_submissions WHERE created_at>=current_date)+(SELECT count(*) FROM uec.community_secure_inboxes WHERE created_at>=current_date), (SELECT count(*) FROM uec.community_submissions WHERE status IN ('received','held'))+(SELECT count(*) FROM uec.community_secure_inboxes WHERE status IN ('received','in_review','needs_information') AND expires_at>now())", &[]).await;
    let Ok(counts) = counts else {
        return unavailable_secure();
    };
    if counts.get::<_, i64>(0) >= cs.config.daily_intake_cap
        || counts.get::<_, i64>(1) >= cs.config.pending_cap
    {
        return limited();
    }
    let bytes = tx.query_one("SELECT COALESCE(sum(octet_length(ciphertext)),0)::bigint FROM uec.community_secure_messages", &[]).await;
    let Ok(bytes) = bytes else {
        return unavailable_secure();
    };
    if bytes.get::<_, i64>(0) + x.ciphertext.len() as i64 > TOTAL_CIPHER_LIMIT {
        return limited();
    }
    let inserted = tx.execute("INSERT INTO uec.community_secure_inboxes(case_id,kind,protocol,access_secret_sha256,contributor_public_key,contributor_fingerprint,reviewer_public_key,reviewer_fingerprint,status,expires_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,'received',now()+($9::bigint*interval '1 day'))", &[&x.case_id,&x.kind,&x.protocol,&secret_hash,&x.contributor_public_key,&x.contributor_fingerprint,&cs.config.secure.reviewer_public_key,&x.reviewer_fingerprint,&cs.config.receipt_days]).await;
    if let Err(e) = inserted {
        return if e.code() == Some(&tokio_postgres::error::SqlState::UNIQUE_VIOLATION) {
            conflict()
        } else {
            unavailable_secure()
        };
    }
    let msg = tx.execute("INSERT INTO uec.community_secure_messages(case_id,message_id,ordinal,author,ciphertext) VALUES($1,$2,1,'contributor',$3)", &[&x.case_id,&x.initial_message_id,&x.ciphertext]).await;
    if msg.is_err() || tx.execute("INSERT INTO uec.community_secure_events(case_id,action,actor_role,status) VALUES($1,'received','contributor','received')", &[&x.case_id]).await.is_err() { return unavailable_secure(); }
    let row = tx
        .query_one(
            "SELECT created_at,expires_at FROM uec.community_secure_inboxes WHERE case_id=$1",
            &[&x.case_id],
        )
        .await;
    let Ok(row) = row else {
        return unavailable_secure();
    };
    let created: DateTime<Utc> = row.get(0);
    let expires: DateTime<Utc> = row.get(1);
    if tx.commit().await.is_err() {
        return unavailable_secure();
    }
    (StatusCode::CREATED,Json(json!({"case_id":x.case_id,"status":"received","created_at":created,"expires_at":expires}))).into_response()
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AuthCase {
    case_id: Uuid,
    access_secret: String,
}
struct InboxRow {
    kind: String,
    status: String,
    contributor_public_key: String,
    contributor_fingerprint: String,
    reviewer_public_key: String,
    reviewer_fingerprint: String,
    created: DateTime<Utc>,
    updated: DateTime<Utc>,
    expires: DateTime<Utc>,
}
async fn authenticated(
    tx: &tokio_postgres::Transaction<'_>,
    id: Uuid,
    secret: Option<&str>,
) -> Result<Option<InboxRow>, ()> {
    let row=tx.query_opt("SELECT kind,status,contributor_public_key,contributor_fingerprint,reviewer_public_key,reviewer_fingerprint,created_at,updated_at,expires_at,access_secret_sha256 FROM uec.community_secure_inboxes WHERE case_id=$1 FOR SHARE", &[&id]).await.map_err(|_|())?;
    let Some(r) = row else {
        return Ok(None);
    };
    let got: Option<String> = r.get(9);
    if secret.is_some_and(|s| !got.as_deref().is_some_and(|h| hash_eq(h, &hash_secret(s)))) {
        return Ok(None);
    }
    let expires: DateTime<Utc> = r.get(8);
    if expires <= Utc::now() || r.get::<_, String>(1) == "removed" {
        return Ok(None);
    }
    Ok(Some(InboxRow {
        kind: r.get(0),
        status: r.get(1),
        contributor_public_key: r.get(2),
        contributor_fingerprint: r.get(3),
        reviewer_public_key: r.get(4),
        reviewer_fingerprint: r.get(5),
        created: r.get(6),
        updated: r.get(7),
        expires,
    }))
}
async fn read_inbox(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    body: Result<Json<AuthCase>, axum::extract::rejection::JsonRejection>,
) -> Response {
    if !enabled(&cs) {
        return off();
    }
    let x = match body {
        Ok(Json(x)) => x,
        Err(e) => return rejected_json(e),
    };
    if !valid_secret(&x.access_secret) {
        return not_found();
    }
    read_case(&api, x.case_id, Some(&x.access_secret)).await
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReviewerCase {
    case_id: Uuid,
}

async fn reviewer_inbox(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    headers: HeaderMap,
    body: Result<Json<ReviewerCase>, axum::extract::rejection::JsonRejection>,
) -> Response {
    if !enabled(&cs) {
        return off();
    }
    if !operator_ok(&cs.config, &headers) {
        return not_found();
    }
    let x = match body {
        Ok(Json(x)) => x,
        Err(e) => return rejected_json(e),
    };
    read_case(&api, x.case_id, None).await
}

async fn read_case(api: &ApiState, id: Uuid, secret: Option<&str>) -> Response {
    let Ok(mut c) = pool(&api).await else {
        return unavailable_secure();
    };
    let Ok(tx) = c.transaction().await else {
        return unavailable_secure();
    };
    let inbox = match authenticated(&tx, id, secret).await {
        Ok(Some(v)) => v,
        Ok(None) => return not_found(),
        Err(_) => return unavailable_secure(),
    };
    let rows=tx.query("SELECT message_id,ordinal,author,ciphertext,created_at FROM uec.community_secure_messages WHERE case_id=$1 ORDER BY ordinal", &[&id]).await;
    let Ok(rows) = rows else {
        return unavailable_secure();
    };
    let messages:Vec<Value>=rows.iter().map(|r|json!({"message_id":r.get::<_,Uuid>(0),"ordinal":r.get::<_,i32>(1),"author":r.get::<_,String>(2),"ciphertext":r.get::<_,String>(3),"created_at":r.get::<_,DateTime<Utc>>(4)})).collect();
    if tx.commit().await.is_err() {
        return unavailable_secure();
    }
    Json(json!({"case_id":id,"kind":inbox.kind,"status":inbox.status,"contributor_public_key":inbox.contributor_public_key,"contributor_fingerprint":inbox.contributor_fingerprint,"reviewer_public_key":inbox.reviewer_public_key,"reviewer_fingerprint":inbox.reviewer_fingerprint,"created_at":inbox.created,"updated_at":inbox.updated,"expires_at":inbox.expires,"messages":messages})).into_response()
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ContributorMessage {
    case_id: Uuid,
    access_secret: String,
    message_id: Uuid,
    ciphertext: String,
}
async fn contributor_message(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    body: Result<Json<ContributorMessage>, axum::extract::rejection::JsonRejection>,
) -> Response {
    if !enabled(&cs) {
        return off();
    }
    let x = match body {
        Ok(Json(x)) => x,
        Err(e) => return rejected_json(e),
    };
    if !valid_id(x.case_id)
        || !valid_id(x.message_id)
        || !valid_secret(&x.access_secret)
        || !valid_cipher(&x.ciphertext)
    {
        return bad_secure();
    }
    add_message(
        &api,
        &cs,
        x.case_id,
        x.message_id,
        &x.ciphertext,
        "contributor",
        Some(&x.access_secret),
        None,
    )
    .await
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReviewerMessage {
    case_id: Uuid,
    message_id: Uuid,
    reviewer_fingerprint: String,
    ciphertext: String,
}
async fn reviewer_message(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    headers: HeaderMap,
    body: Result<Json<ReviewerMessage>, axum::extract::rejection::JsonRejection>,
) -> Response {
    if !enabled(&cs) {
        return off();
    }
    if !operator_ok(&cs.config, &headers) {
        return not_found();
    }
    let x = match body {
        Ok(Json(x)) => x,
        Err(e) => return rejected_json(e),
    };
    if !valid_id(x.case_id)
        || !valid_id(x.message_id)
        || !valid_fingerprint(&x.reviewer_fingerprint)
        || !valid_cipher(&x.ciphertext)
    {
        return bad_secure();
    }
    add_message(
        &api,
        &cs,
        x.case_id,
        x.message_id,
        &x.ciphertext,
        "reviewer",
        None,
        Some(&x.reviewer_fingerprint),
    )
    .await
}
async fn add_message(
    api: &ApiState,
    cs: &CommunityState,
    id: Uuid,
    message_id: Uuid,
    cipher: &str,
    author: &str,
    secret: Option<&str>,
    fingerprint: Option<&str>,
) -> Response {
    let Ok(mut c) = pool(api).await else {
        return unavailable_secure();
    };
    let Ok(tx) = c.transaction().await else {
        return unavailable_secure();
    };
    if tx
        .query_one("SELECT pg_advisory_xact_lock($1,$2)", &[&LOCK_A, &LOCK_B])
        .await
        .is_err()
    {
        return unavailable_secure();
    }
    let row=tx.query_opt("SELECT status,access_secret_sha256,reviewer_fingerprint,expires_at FROM uec.community_secure_inboxes WHERE case_id=$1 FOR UPDATE", &[&id]).await;
    let row = match row {
        Ok(Some(row)) => row,
        Ok(None) => return not_found(),
        Err(_) => return unavailable_secure(),
    };
    let status: String = row.get(0);
    let stored_secret: Option<String> = row.get(1);
    let stored_fp: String = row.get(2);
    let expires: DateTime<Utc> = row.get(3);
    if !active(&status) || expires <= Utc::now() {
        return not_found();
    }
    if let Some(s) = secret {
        if !stored_secret
            .as_deref()
            .is_some_and(|h| hash_eq(h, &hash_secret(s)))
        {
            return not_found();
        }
    }
    if let Some(fp) = fingerprint {
        if !hash_eq(fp, &stored_fp) {
            return not_found();
        }
    }
    if expire_cases(&tx, cs.config.retention_days).await.is_err() {
        return unavailable_secure();
    }
    let old=tx.query_opt("SELECT author,ciphertext FROM uec.community_secure_messages WHERE case_id=$1 AND message_id=$2", &[&id,&message_id]).await;
    let Ok(old) = old else {
        return unavailable_secure();
    };
    if let Some(old) = old {
        if old.get::<_, String>(0) == author && old.get::<_, String>(1) == cipher {
            if tx.commit().await.is_err() {
                return unavailable_secure();
            }
            return (
                StatusCode::OK,
                Json(json!({"case_id":id,"message_id":message_id,"status":"stored"})),
            )
                .into_response();
        }
        return conflict();
    }
    let count = tx
        .query_one(
            "SELECT count(*) FROM uec.community_secure_messages WHERE case_id=$1",
            &[&id],
        )
        .await;
    let Ok(count) = count else {
        return unavailable_secure();
    };
    if count.get::<_, i64>(0) >= MESSAGE_LIMIT {
        return limited();
    }
    let bytes=tx.query_one("SELECT COALESCE(sum(octet_length(ciphertext)),0)::bigint FROM uec.community_secure_messages", &[]).await;
    let Ok(bytes) = bytes else {
        return unavailable_secure();
    };
    if bytes.get::<_, i64>(0) + cipher.len() as i64 > TOTAL_CIPHER_LIMIT {
        return limited();
    }
    let ordinal = tx
        .query_one(
            "SELECT COALESCE(max(ordinal),0)+1 FROM uec.community_secure_messages WHERE case_id=$1",
            &[&id],
        )
        .await;
    let Ok(ordinal) = ordinal else {
        return unavailable_secure();
    };
    let ordinal: i32 = ordinal.get(0);
    if let Err(e) = tx.execute("INSERT INTO uec.community_secure_messages(case_id,message_id,ordinal,author,ciphertext) VALUES($1,$2,$3,$4,$5)", &[&id,&message_id,&ordinal,&author,&cipher]).await {
        return if e.code() == Some(&tokio_postgres::error::SqlState::UNIQUE_VIOLATION) { conflict() } else { unavailable_secure() };
    }
    if tx.execute("INSERT INTO uec.community_secure_events(case_id,action,actor_role,status) VALUES($1,'message_added',$2,NULL)", &[&id,&author]).await.is_err() || tx.execute("UPDATE uec.community_secure_inboxes SET updated_at=now() WHERE case_id=$1", &[&id]).await.is_err(){return unavailable_secure();}
    if tx.commit().await.is_err() {
        return unavailable_secure();
    }
    (
        StatusCode::CREATED,
        Json(json!({"case_id":id,"message_id":message_id,"status":"stored"})),
    )
        .into_response()
}

async fn queue(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    headers: HeaderMap,
) -> Response {
    if !enabled(&cs) {
        return off();
    }
    if !operator_ok(&cs.config, &headers) {
        return not_found();
    }
    let Ok(c) = pool(&api).await else {
        return unavailable_secure();
    };
    let rows=c.query("SELECT case_id,kind,status,contributor_fingerprint,reviewer_fingerprint,created_at,updated_at,expires_at FROM uec.community_secure_inboxes WHERE status IN ('received','in_review','needs_information') AND expires_at>now() ORDER BY created_at,case_id LIMIT 20", &[]).await;
    let Ok(rows) = rows else {
        return unavailable_secure();
    };
    let cases:Vec<Value>=rows.iter().map(|r|json!({"case_id":r.get::<_,Uuid>(0),"kind":r.get::<_,String>(1),"status":r.get::<_,String>(2),"contributor_fingerprint":r.get::<_,String>(3),"reviewer_fingerprint":r.get::<_,String>(4),"created_at":r.get::<_,DateTime<Utc>>(5),"updated_at":r.get::<_,DateTime<Utc>>(6),"expires_at":r.get::<_,DateTime<Utc>>(7)})).collect();
    Json(json!({"cases":cases})).into_response()
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Disposition {
    case_id: Uuid,
    status: String,
}
async fn disposition(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    headers: HeaderMap,
    body: Result<Json<Disposition>, axum::extract::rejection::JsonRejection>,
) -> Response {
    if !enabled(&cs) {
        return off();
    }
    if !operator_ok(&cs.config, &headers) {
        return not_found();
    }
    let x = match body {
        Ok(Json(x)) => x,
        Err(e) => return rejected_json(e),
    };
    if !valid_status(&x.status) {
        return bad_secure();
    }
    let Ok(mut c) = pool(&api).await else {
        return unavailable_secure();
    };
    let Ok(tx) = c.transaction().await else {
        return unavailable_secure();
    };
    if tx
        .query_one("SELECT pg_advisory_xact_lock($1,$2)", &[&LOCK_A, &LOCK_B])
        .await
        .is_err()
    {
        return unavailable_secure();
    }
    let row = tx
        .query_opt(
            "SELECT status FROM uec.community_secure_inboxes WHERE case_id=$1 FOR UPDATE",
            &[&x.case_id],
        )
        .await;
    let row = match row {
        Ok(Some(row)) => row,
        Ok(None) => return not_found(),
        Err(_) => return unavailable_secure(),
    };
    if row.get::<_, String>(0) == "removed" {
        return not_found();
    }
    if x.status == "removed" {
        if tx.execute("UPDATE uec.community_secure_inboxes SET status='removed',access_secret_sha256=NULL,contributor_public_key='',contributor_fingerprint='',reviewer_public_key='',reviewer_fingerprint='',updated_at=now() WHERE case_id=$1", &[&x.case_id]).await.is_err()||tx.execute("DELETE FROM uec.community_secure_messages WHERE case_id=$1", &[&x.case_id]).await.is_err(){return unavailable_secure();}
    } else if tx
        .execute(
            "UPDATE uec.community_secure_inboxes SET status=$2,updated_at=now() WHERE case_id=$1",
            &[&x.case_id, &x.status],
        )
        .await
        .is_err()
    {
        return unavailable_secure();
    }
    if tx.execute("INSERT INTO uec.community_secure_events(case_id,action,actor_role,status) VALUES($1,'status_changed','reviewer',$2)", &[&x.case_id,&x.status]).await.is_err()||tx.commit().await.is_err(){return unavailable_secure();}
    Json(json!({"case_id":x.case_id,"status":x.status})).into_response()
}
async fn maintenance(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    headers: HeaderMap,
) -> Response {
    if !enabled(&cs) {
        return off();
    }
    if !operator_ok(&cs.config, &headers) {
        return not_found();
    }
    let Ok(mut c) = pool(&api).await else {
        return unavailable_secure();
    };
    let Ok(tx) = c.transaction().await else {
        return unavailable_secure();
    };
    if tx
        .query_one("SELECT pg_advisory_xact_lock($1,$2)", &[&LOCK_A, &LOCK_B])
        .await
        .is_err()
    {
        return unavailable_secure();
    }
    let Ok((count, purged)) = expire_cases(&tx, cs.config.retention_days).await else {
        return unavailable_secure();
    };
    if tx.commit().await.is_err() {
        return unavailable_secure();
    }
    Json(json!({"expired":count,"purged":purged})).into_response()
}

// Called under the shared admission lock. Expired ciphertext never becomes
// readable; metadata/events survive only for the configured post-removal
// retention period, then cascade-delete. Idle enforcement still needs a caller.
async fn expire_cases(tx: &tokio_postgres::Transaction<'_>, days: i64) -> Result<(usize, u64), ()> {
    let rows = tx.query("UPDATE uec.community_secure_inboxes SET status='removed',access_secret_sha256=NULL,contributor_public_key='',contributor_fingerprint='',reviewer_public_key='',reviewer_fingerprint='',updated_at=now() WHERE expires_at<=now() AND status<>'removed' RETURNING case_id", &[]).await.map_err(|_| ())?;
    for row in &rows {
        let id: Uuid = row.get(0);
        tx.execute(
            "DELETE FROM uec.community_secure_messages WHERE case_id=$1",
            &[&id],
        )
        .await
        .map_err(|_| ())?;
        tx.execute("INSERT INTO uec.community_secure_events(case_id,action,actor_role,status) VALUES($1,'expired','system','removed')", &[&id]).await.map_err(|_| ())?;
    }
    let purged = tx.execute("DELETE FROM uec.community_secure_inboxes WHERE status='removed' AND updated_at<now()-($1::bigint*interval '1 day')", &[&days]).await.map_err(|_| ())?;
    Ok((rows.len(), purged))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn key() -> String {
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\nsynthetic\n-----END PGP PUBLIC KEY BLOCK-----\n"
            .into()
    }
    fn cipher() -> String {
        "-----BEGIN PGP MESSAGE-----\nsynthetic\n-----END PGP MESSAGE-----\n".into()
    }
    fn local_config() -> super::super::CommunityConfig {
        let mut config =
            super::super::CommunityConfig::local_pilot(false, 30, 7, 14, 20, 100, "o".repeat(48))
                .unwrap();
        config.secure = Config {
            enabled: true,
            reviewer_public_key: key(),
            reviewer_fingerprint: "b".repeat(40),
        };
        config
    }
    #[test]
    fn framing_limits_and_secrets_are_strict() {
        assert!(valid_public_key(&key()));
        assert!(valid_cipher(&cipher()));
        assert!(!valid_cipher("plain text"));
        assert!(!valid_public_key(
            "-----BEGIN PGP PRIVATE KEY BLOCK-----\nx\n-----END PGP PRIVATE KEY BLOCK-----\n"
        ));
        assert!(valid_secret(&"a".repeat(64)));
        assert!(!valid_secret(&"A".repeat(64)));
        assert!(!valid_fingerprint(&"g".repeat(40)));
        assert!(valid_id(Uuid::new_v4()));
        assert!(!valid_id(Uuid::nil()));
        assert!(!valid_id(Uuid::from_bytes([255; 16])));
        assert!(!valid_cipher(
            &cipher().replace("END PGP MESSAGE", "END PGP PUBLIC KEY BLOCK")
        ));
        assert!(!valid_cipher(&format!("{}{}", cipher(), cipher())));
        assert!(!valid_cipher(&format!(
            "-----BEGIN PGP MESSAGE-----\n{}\n-----END PGP MESSAGE-----\n",
            "a".repeat(MAX_CIPHER)
        )));
    }
    #[test]
    fn config_disabled_needs_no_key() {
        assert!(!Config::disabled().enabled);
        assert!(require_local_mode("development").is_ok());
        assert!(require_local_mode("production").is_err());
        assert!(require_local_mode("unknown").is_err());
    }
    #[test]
    fn submission_is_exact_and_unknown_fields_fail() {
        let raw = json!({"case_id":Uuid::new_v4(),"initial_message_id":Uuid::new_v4(),"kind":"bug","protocol":"uec-openpgp-inbox-v1","access_secret":"a".repeat(64),"contributor_public_key":key(),"contributor_fingerprint":"a".repeat(40),"reviewer_fingerprint":"b".repeat(40),"ciphertext":cipher()});
        let x: Submission = serde_json::from_value(raw.clone()).unwrap();
        let cs = CommunityState {
            config: super::super::CommunityConfig::disabled(),
        };
        let mut c = cs.clone();
        c.config.enabled = true;
        c.config.secure = Config {
            enabled: true,
            reviewer_public_key: key(),
            reviewer_fingerprint: "b".repeat(40),
        };
        assert!(valid_submission(&x, &c));
        let mut unknown = raw;
        unknown["plaintext"] = json!("no");
        assert!(serde_json::from_value::<Submission>(unknown).is_err());
    }
    #[test]
    fn route_limits_are_bounded() {
        assert_eq!(BODY_LIMIT, 128 * 1024);
        assert_eq!(MAX_CIPHER, 98_304);
        assert_eq!(MESSAGE_LIMIT, 32);
    }
    #[tokio::test]
    async fn secure_body_limit_and_default_off_do_not_change_legacy_capabilities() {
        use axum::body::{Body, to_bytes};
        use axum::http::Request;
        use tower::ServiceExt;
        let app = |config| {
            super::super::routes(config).with_state(ApiState {
                database: None,
                community_database: None,
                dev_preview_token: None,
                dev_test_release_id: None,
                dev_test_release_token: None,
            })
        };
        let mut config = local_config();
        let response = app(config.clone())
            .oneshot(
                Request::builder()
                    .uri("/api/community/secure/submissions")
                    .method("POST")
                    .header("content-type", "application/json")
                    .body(Body::from("x".repeat(BODY_LIMIT + 1)))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
        assert!(
            response.headers()["cache-control"]
                .to_str()
                .unwrap()
                .starts_with("no-store")
        );
        // Referrer-Policy is applied by the binary's outer security middleware
        // and is checked by the HTTP/database acceptance suite.
        config.secure = Config::disabled();
        let response = app(config.clone())
            .oneshot(
                Request::builder()
                    .uri("/api/community/secure/capabilities")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let bytes = to_bytes(response.into_body(), BODY_LIMIT).await.unwrap();
        assert_eq!(
            serde_json::from_slice::<Value>(&bytes).unwrap(),
            json!({"enabled": false})
        );
        let response = app(config)
            .oneshot(
                Request::builder()
                    .uri("/api/community/secure/inbox")
                    .method("POST")
                    .header("content-type", "application/json")
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        let response = app(super::super::CommunityConfig::disabled())
            .oneshot(
                Request::builder()
                    .uri("/api/community/secure/capabilities")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }
}
