use super::{
    CommunityState, bad, disabled, operator_ok, pool, receipt_not_found, unavailable, valid_email,
};
use crate::ApiState;
use axum::{
    Json,
    extract::rejection::{JsonRejection, PathRejection},
    extract::{Extension, Path, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
};
use serde::Deserialize;
use serde_json::json;
use std::time::Duration;
use tokio_postgres::Error;
use uuid::Uuid;

#[derive(Clone)]
pub(super) struct Config {
    api_key: String,
    sender: String,
    reviewer: String,
    site_origin: String,
}

impl Config {
    pub(super) fn from_env() -> Result<Self, String> {
        fn required(name: &str) -> Result<String, String> {
            std::env::var(name)
                .ok()
                .filter(|value| !value.is_empty() && !value.chars().any(char::is_control))
                .ok_or_else(|| format!("{name} is required for community email"))
        }
        let sender = required("UEC_COMMUNITY_EMAIL_FROM")?;
        let reviewer = required("UEC_COMMUNITY_EMAIL_INBOX")?;
        if !valid_email(&sender) || !valid_email(&reviewer) {
            return Err("community email sender and inbox must be email addresses".into());
        }
        let site = required("UEC_COMMUNITY_EMAIL_SITE_URL")?;
        let site = reqwest::Url::parse(&site)
            .ok()
            .filter(|url| {
                url.scheme() == "https"
                    && url.host_str().is_some()
                    && url.username().is_empty()
                    && url.password().is_none()
                    && url.path() == "/"
                    && url.query().is_none()
                    && url.fragment().is_none()
            })
            .ok_or("UEC_COMMUNITY_EMAIL_SITE_URL must be an HTTPS origin")?;
        Ok(Self {
            api_key: required("UEC_COMMUNITY_EMAIL_API_KEY")?,
            sender,
            reviewer,
            site_origin: site.origin().ascii_serialization(),
        })
    }
}

pub(super) async fn enqueue(
    tx: &deadpool_postgres::Transaction<'_>,
    id: Uuid,
    submission: Uuid,
    kind: &str,
    content: Option<&str>,
) -> Result<u64, Error> {
    tx.execute(
        "INSERT INTO uec.community_email_outbox (id, submission_id, contact_submission_id, kind, content)
         SELECT $1::uuid, $2::uuid, CASE WHEN $3::text = 'reviewer_alert' THEN NULL ELSE $2::uuid END, $3::text, $4::text
         WHERE $3 = 'reviewer_alert' OR EXISTS (
             SELECT 1 FROM uec.community_submission_contacts
             WHERE submission_id = $2 AND email_updates AND expires_at > now()
         )
         ON CONFLICT (id) DO NOTHING",
        &[&id, &submission, &kind, &content],
    ).await
}

pub(super) fn status_message(status: &str) -> Option<&'static str> {
    match status {
        "screened" => Some("The privacy review of your submission is complete."),
        "rejected" => Some("Your submission was not accepted."),
        "published" => Some("Your submission was linked to a published community record."),
        _ => None,
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Reply {
    request_id: Uuid,
    message: String,
}

pub(super) async fn reply(
    State(api): State<ApiState>,
    Extension(cs): Extension<CommunityState>,
    headers: HeaderMap,
    path: Result<Path<Uuid>, PathRejection>,
    body: Result<Json<Reply>, JsonRejection>,
) -> Response {
    if cs.config.email.is_none() || !operator_ok(&cs.config, &headers) {
        return disabled();
    }
    let Ok(Path(submission)) = path else {
        return bad("submission ID is invalid");
    };
    let Ok(Json(reply)) = body else {
        return bad("reply is invalid");
    };
    let message = reply.message.trim();
    if message.is_empty() || message.len() > 2000 || message.contains('\0') {
        return bad("reply must contain 1 to 2000 bytes");
    }
    let Ok(mut client) = pool(&api).await else {
        return unavailable();
    };
    let Ok(tx) = client.transaction().await else {
        return unavailable();
    };
    let row = tx
        .query_opt(
            "SELECT 1 FROM uec.community_submissions
         WHERE submission_id = $1 AND status NOT IN ('restricted','removed')
          AND claim <> '{}'::jsonb FOR UPDATE",
            &[&submission],
        )
        .await;
    match row {
        Ok(Some(_)) => {}
        Ok(None) => return receipt_not_found(),
        Err(_) => return unavailable(),
    }
    match enqueue(&tx, reply.request_id, submission, "reply", Some(message)).await {
        Ok(1) => {}
        Ok(_) => match tx
            .query_opt(
                "SELECT 1 FROM uec.community_email_outbox
             WHERE id = $1 AND submission_id = $2 AND kind = 'reply'",
                &[&reply.request_id, &submission],
            )
            .await
        {
            Ok(Some(_)) => {}
            Ok(None) => return bad("email follow-up is unavailable for this submission"),
            Err(_) => return unavailable(),
        },
        Err(_) => return unavailable(),
    }
    if tx.commit().await.is_err() {
        return unavailable();
    }
    (StatusCode::ACCEPTED, Json(json!({"queued":true}))).into_response()
}

#[derive(Debug, PartialEq, Eq)]
enum Delivery {
    Accepted,
    Retry,
    Failed,
}

fn classify_delivery(status: Result<reqwest::StatusCode, reqwest::Error>) -> Delivery {
    match status {
        Ok(code) if code.is_success() => Delivery::Accepted,
        Ok(code) if code.is_server_error() || matches!(code.as_u16(), 408 | 409 | 429) => {
            Delivery::Retry
        }
        Ok(_) => Delivery::Failed,
        Err(_) => Delivery::Retry,
    }
}

async fn deliver_next(
    pool: &deadpool_postgres::Pool,
    http: &reqwest::Client,
    config: &Config,
    endpoint: &str,
) -> Result<bool, ()> {
    let mut client = pool.get().await.map_err(|_| ())?;
    let tx = client.transaction().await.map_err(|_| ())?;
    // Each worker holds the submission lock while delivering its next message.
    // A disposition cannot revoke the contact between the eligibility check and send.
    let row = tx
        .query_opt(
            "SELECT o.id, o.submission_id, o.kind, o.content, o.attempts, c.email
         FROM uec.community_email_outbox o
         JOIN uec.community_submissions s USING (submission_id)
         LEFT JOIN uec.community_submission_contacts c ON c.submission_id = o.contact_submission_id
             AND c.email_updates AND c.expires_at > now()
         WHERE o.finished_at IS NULL AND o.next_attempt_at <= now() AND o.expires_at > now()
             AND s.status NOT IN ('restricted', 'removed') AND s.claim <> '{}'::jsonb
         ORDER BY o.next_attempt_at, o.id LIMIT 1 FOR UPDATE OF s SKIP LOCKED",
            &[],
        )
        .await
        .map_err(|_| ())?;
    let Some(row) = row else { return Ok(false) };
    let id: Uuid = row.get(0);
    let attempts: i32 = row.get(4);
    if tx.query_opt("SELECT 1 FROM uec.community_email_outbox WHERE id=$1 AND attempts=$2 AND finished_at IS NULL AND next_attempt_at <= now() AND expires_at > now() FOR UPDATE SKIP LOCKED", &[&id, &attempts]).await.map_err(|_| ())?.is_none() {
        return Ok(false);
    }
    let reference: Uuid = row.get(1);
    let kind: String = row.get(2);
    let content: Option<String> = row.get(3);
    let contact: Option<String> = row.get(5);
    let message = if kind == "reviewer_alert" {
        Some((
            config.reviewer.as_str(),
            format!("New contribution {reference}"),
            format!(
                "Open the review queue: {}/#/contribution-review\n\nReference: {reference}",
                config.site_origin
            ),
        ))
    } else {
        contact.as_deref().zip(content).map(|(to, content)| {
            (
                to,
                format!("Contribution {reference}"),
                format!("{content}\n\nReference: {reference}"),
            )
        })
    };
    let delivery = if let Some((to, subject, text)) = message {
        let status = http
            .post(endpoint)
            .bearer_auth(&config.api_key)
            .header("Idempotency-Key", id.to_string())
            .json(
                &json!({"from":config.sender,"to":[to],"reply_to":config.reviewer,
                "subject":subject,"text":text}),
            )
            .send()
            .await
            .map(|response| response.status());
        classify_delivery(status)
    } else {
        Delivery::Failed
    };
    let retry = delivery == Delivery::Retry && attempts < 4;
    if retry {
        let delay = 30 * 2_i32.pow(attempts as u32);
        tx.execute(
            "UPDATE uec.community_email_outbox SET attempts = attempts + 1,
             next_attempt_at = now() + ($2::int * interval '1 second') WHERE id = $1",
            &[&id, &delay],
        )
        .await
        .map_err(|_| ())?;
    } else {
        tx.execute(
            "UPDATE uec.community_email_outbox SET attempts = attempts + 1,
             finished_at = now(), content = NULL WHERE id = $1",
            &[&id],
        )
        .await
        .map_err(|_| ())?;
    }
    tx.commit().await.map_err(|_| ())?;
    println!(
        "{}",
        json!({"event":"community_email_delivery","kind":kind,
        "outcome":if retry {"retry"} else if delivery == Delivery::Accepted {"accepted"} else {"failed"}})
    );
    Ok(true)
}

pub(super) async fn run(pool: deadpool_postgres::Pool, config: Config) {
    let Ok(http) = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(8))
        .build()
    else {
        eprintln!("{}", r#"{"event":"community_email_client_unavailable"}"#);
        return;
    };
    loop {
        let cleaned = match pool.get().await {
            Ok(client) => client
                .execute(
                    "DELETE FROM uec.community_email_outbox WHERE expires_at <= now()",
                    &[],
                )
                .await
                .is_ok(),
            Err(_) => false,
        };
        if !cleaned {
            eprintln!("{}", r#"{"event":"community_email_outbox_unavailable"}"#);
        } else {
            for _ in 0..10 {
                match deliver_next(&pool, &http, &config, "https://api.resend.com/emails").await {
                    Ok(true) => tokio::time::sleep(Duration::from_secs(1)).await,
                    Ok(false) => break,
                    Err(()) => {
                        eprintln!("{}", r#"{"event":"community_email_job_unavailable"}"#);
                        break;
                    }
                }
            }
        }
        tokio::time::sleep(Duration::from_secs(15)).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::community::CommunityConfig;
    use axum::{
        Router,
        body::{Body, to_bytes},
        http::Request,
        routing::post,
    };
    use std::sync::{Arc, Mutex};
    use tower::ServiceExt;

    #[test]
    fn status_email_only_describes_publicly_trackable_decisions() {
        for status in ["received", "held", "restricted", "removed"] {
            assert!(status_message(status).is_none());
        }
        for status in ["screened", "rejected", "published"] {
            assert!(status_message(status).is_some());
        }
    }

    #[tokio::test]
    #[ignore = "requires empty loopback PostgreSQL with migrations 066 and 122"]
    async fn email_intake_reply_and_retry_use_the_restricted_outbox() {
        let dsn = std::env::var("UEC_COMMUNITY_EMAIL_TEST_DATABASE_URL").unwrap();
        assert_eq!(
            reqwest::Url::parse(&dsn).unwrap().host_str(),
            Some("127.0.0.1")
        );
        let mut database = deadpool_postgres::Config::new();
        database.url = Some(dsn);
        let pool = database
            .create_pool(
                Some(deadpool_postgres::Runtime::Tokio1),
                tokio_postgres::NoTls,
            )
            .unwrap();
        let client = pool.get().await.unwrap();
        assert_eq!(
            client
                .query_one("SELECT count(*) FROM uec.community_submissions", &[])
                .await
                .unwrap()
                .get::<_, i64>(0),
            0
        );
        let token = "synthetic-restricted-operator-token-for-email-proof";
        let mut settings =
            CommunityConfig::local_pilot(false, 30, 7, 14, 20, 20, token.into()).unwrap();
        let mail = Config {
            api_key: "synthetic-provider-key".into(),
            sender: "sender@example.test".into(),
            reviewer: "review@example.test".into(),
            site_origin: "https://project.example.test".into(),
        };
        settings.email = Some(mail.clone());
        settings.validate_email_schema(Some(&pool)).await.unwrap();
        let app = super::super::routes(settings).with_state(ApiState {
            database: None,
            community_database: Some(pool.clone()),
            dev_preview_token: None,
            dev_test_release_id: None,
            dev_test_release_token: None,
        });
        async fn call(
            app: &Router,
            path: &str,
            body: Option<serde_json::Value>,
            auth: Option<&str>,
        ) -> (StatusCode, serde_json::Value) {
            let mut builder =
                Request::builder()
                    .uri(path)
                    .method(if body.is_some() { "POST" } else { "GET" });
            if let Some(token) = auth {
                builder = builder.header("authorization", format!("Bearer {token}"));
            }
            let body = body.map_or_else(Body::empty, |payload| Body::from(payload.to_string()));
            let response = app
                .clone()
                .oneshot(
                    builder
                        .header("content-type", "application/json")
                        .body(body)
                        .unwrap(),
                )
                .await
                .unwrap();
            let status = response.status();
            (
                status,
                serde_json::from_slice(&to_bytes(response.into_body(), 128 * 1024).await.unwrap())
                    .unwrap(),
            )
        }
        let intake = "/api/community/submissions";
        let (status, no_opt_in) = call(
            &app,
            intake,
            Some(json!({"kind":"facility","label":"Synthetic opted out","contact_email":"opted-out@example.test","consent":true})),
            None,
        )
        .await;
        assert_eq!(status, StatusCode::CREATED, "{no_opt_in}");
        let (status, contact) = call(
            &app,
            intake,
            Some(
                json!({"kind":"facility","label":"Synthetic opted in","consent":true,
            "email_updates":true,"contact_email":"contributor@example.test"}),
            ),
            None,
        )
        .await;
        assert_eq!(status, StatusCode::CREATED, "{contact}");
        let id = contact["submission_id"].as_str().unwrap();
        let queue = call(
            &app,
            "/api/private/community/submissions",
            None,
            Some(token),
        )
        .await
        .1;
        let rows = queue["submissions"].as_array().unwrap();
        assert_eq!(
            rows.iter()
                .filter(|row| row["email_reply_available"] == true)
                .count(),
            1
        );
        assert!(!queue.to_string().contains("contributor@example.test"));
        let reply_path = format!("/api/private/community/submissions/{id}/reply");
        let reply_body = json!({"request_id":Uuid::new_v4(),"message":"Synthetic reply"});
        assert_eq!(
            call(&app, &reply_path, Some(reply_body.clone()), None)
                .await
                .0,
            StatusCode::NOT_FOUND
        );
        for _ in 0..2 {
            assert_eq!(
                call(&app, &reply_path, Some(reply_body.clone()), Some(token))
                    .await
                    .0,
                StatusCode::ACCEPTED
            );
        }
        for case in [&contact, &no_opt_in] {
            let path = format!(
                "/api/private/community/submissions/{}/disposition",
                case["submission_id"].as_str().unwrap()
            );
            for _ in 0..2 {
                assert_eq!(
                    call(
                        &app,
                        &path,
                        Some(json!({"action":"screen","reason_code":"eligible"})),
                        Some(token)
                    )
                    .await
                    .0,
                    StatusCode::OK
                );
            }
        }
        let captured = Arc::new(Mutex::new(Vec::<(String, serde_json::Value)>::new()));
        let inbox = captured.clone();
        let provider = Router::new().route(
            "/emails",
            post(
                move |headers: HeaderMap, Json(body): Json<serde_json::Value>| {
                    let inbox = inbox.clone();
                    async move {
                        let mut calls = inbox.lock().unwrap();
                        calls.push((headers["idempotency-key"].to_str().unwrap().into(), body));
                        if calls.len() == 1 {
                            StatusCode::TOO_MANY_REQUESTS
                        } else {
                            StatusCode::ACCEPTED
                        }
                    }
                },
            ),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = format!("http://{}/emails", listener.local_addr().unwrap());
        let delivery_server =
            tokio::spawn(async move { axum::serve(listener, provider).await.unwrap() });
        let http = reqwest::Client::builder()
            .timeout(Duration::from_secs(4))
            .build()
            .unwrap();
        assert!(deliver_next(&pool, &http, &mail, &endpoint).await.unwrap());
        client.execute("UPDATE uec.community_email_outbox SET next_attempt_at=now() WHERE attempts=1 AND finished_at IS NULL",&[]).await.unwrap();
        for _ in 0..4 {
            assert!(deliver_next(&pool, &http, &mail, &endpoint).await.unwrap());
        }
        assert!(!deliver_next(&pool, &http, &mail, &endpoint).await.unwrap());
        delivery_server.abort();
        let calls = captured.lock().unwrap();
        assert_eq!(calls.len(), 5);
        assert_eq!(calls.iter().filter(|(id, _)| *id == calls[0].0).count(), 2);
        assert_eq!(
            calls
                .iter()
                .filter(|(_, body)| body["to"] == json!(["contributor@example.test"]))
                .count(),
            2
        );
        assert!(calls.iter().all(|(_, body)| {
            body["reply_to"] == "review@example.test"
                && !body
                    .to_string()
                    .contains(contact["receipt_secret"].as_str().unwrap())
        }));
        assert_eq!(
            client
                .query_one(
                    "SELECT count(*) FROM uec.community_email_outbox WHERE content IS NOT NULL",
                    &[]
                )
                .await
                .unwrap()
                .get::<_, i64>(0),
            0
        );
    }
}
