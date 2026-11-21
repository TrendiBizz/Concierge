//! Offline protocol and lifecycle checks. All credentials and media are synthetic.
use axum::{
    body::{Body, Bytes},
    extract::State,
    http::{HeaderMap, Method, StatusCode},
    response::Response,
    routing::any,
    Router,
};
use base64::{
    engine::general_purpose::{STANDARD, URL_SAFE_NO_PAD},
    Engine,
};
use concierge_social::{
    connector::{Connector, PublishRequest, Registry},
    media::Asset,
    model::{NewPost, Status},
    scheduler,
    store::Store,
    vault::{account_label, Vault},
    youtube::{self, Config, Endpoints},
    youtube_publish::{self, YouTube},
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::VecDeque,
    sync::{Arc, Mutex},
};
static ENV_LOCK: tokio::sync::Mutex<()> = tokio::sync::Mutex::const_new(());
type RequestCheck = Box<dyn Fn(&HeaderMap, &[u8]) + Send + Sync>;
struct Step {
    method: Method,
    path: &'static str,
    status: u16,
    headers: Vec<(&'static str, String)>,
    body: Value,
    check: RequestCheck,
}
async fn handle(
    State(steps): State<Arc<Mutex<VecDeque<Step>>>>,
    method: Method,
    uri: axum::http::Uri,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    let step = steps
        .lock()
        .unwrap()
        .pop_front()
        .expect("unexpected mock request");
    assert_eq!(method, step.method);
    assert_eq!(uri.path(), step.path);
    (step.check)(&headers, &body);
    let mut response = Response::builder()
        .status(StatusCode::from_u16(step.status).unwrap())
        .header("Content-Type", "application/json");
    for (k, v) in step.headers {
        response = response.header(k, v);
    }
    response.body(Body::from(step.body.to_string())).unwrap()
}
fn step(method: Method, path: &'static str, status: u16, body: Value) -> Step {
    Step {
        method,
        path,
        status,
        body,
        headers: vec![],
        check: Box::new(|_, _| {}),
    }
}
async fn server() -> (
    String,
    Arc<Mutex<VecDeque<Step>>>,
    tokio::task::JoinHandle<()>,
) {
    let steps = Arc::new(Mutex::new(VecDeque::new()));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let base = format!("http://{}", listener.local_addr().unwrap());
    let app = Router::new()
        .fallback(any(handle))
        .with_state(steps.clone());
    let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    (base, steps, task)
}
fn seed() -> (Store, Vault, Config) {
    let s = Store::open_memory().unwrap();
    s.create_customer("tenant", "Business", "").unwrap();
    s.create_customer("other", "Other business", "").unwrap();
    let v = Vault::from_base64_key(&STANDARD.encode([17u8; 32])).unwrap();
    (
        s,
        v,
        Config {
            client_id: "mock-client".into(),
            secret: "mock-only".into(),
            callback: "https://example.invalid/owner/social/oauth/callback".into(),
        },
    )
}
fn endpoints(base: &str) -> Endpoints {
    Endpoints {
        token: format!("{base}/token"),
        channels: format!("{base}/channels"),
        revoke: format!("{base}/revoke"),
    }
}
fn grant() -> Value {
    json!({"access_token":"mock-access","refresh_token":"mock-refresh","expires_in":3600,"scope":youtube::SCOPES})
}
#[test]
fn oauth_start_uses_offline_pkce_and_tenant_single_use_state() {
    let (s, v, c) = seed();
    let a = youtube::start(&s, &v, "tenant", &c).unwrap();
    let b = youtube::start(&s, &v, "tenant", &c).unwrap();
    assert_ne!(a.state, b.state);
    let u = reqwest::Url::parse(&a.authorization_url).unwrap();
    assert_eq!(u.host_str(), Some("accounts.google.com"));
    let q: std::collections::HashMap<_, _> = u.query_pairs().into_owned().collect();
    for (k, val) in [
        ("access_type", "offline"),
        ("prompt", "consent"),
        ("include_granted_scopes", "true"),
        ("code_challenge_method", "S256"),
        ("scope", youtube::SCOPES),
    ] {
        assert_eq!(q[k], val);
    }
    assert!(!q.contains_key("client_secret"));
    assert!(s.oauth_consume("other", "youtube", &a.state).is_err());
    assert!(s.oauth_consume("tenant", "tiktok", &a.state).is_err());
    let sealed = s.oauth_consume("tenant", "youtube", &a.state).unwrap();
    let verifier = v.open(&sealed, "oauth:youtube:tenant").unwrap();
    assert_eq!(
        q["code_challenge"],
        URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()))
    );
    assert!(s.oauth_consume("tenant", "youtube", &a.state).is_err());
}
#[tokio::test]
async fn oauth_finish_encrypts_channel_tokens_and_disconnect_erases_even_if_revoke_fails() {
    let (s, v, c) = seed();
    let (base, steps, task) = server().await;
    let e = endpoints(&base);
    let a = youtube::start(&s, &v, "tenant", &c).unwrap();
    let u = reqwest::Url::parse(&a.authorization_url).unwrap();
    let challenge = u
        .query_pairs()
        .find(|(k, _)| k == "code_challenge")
        .unwrap()
        .1
        .into_owned();
    let mut token = step(Method::POST, "/token", 200, grant());
    token.check = Box::new(move |_, b| {
        let form: std::collections::HashMap<_, _> =
            reqwest::Url::parse(&format!("http://mock/?{}", std::str::from_utf8(b).unwrap()))
                .unwrap()
                .query_pairs()
                .into_owned()
                .collect();
        assert_eq!(form["grant_type"], "authorization_code");
        assert_eq!(
            URL_SAFE_NO_PAD.encode(Sha256::digest(form["code_verifier"].as_bytes())),
            challenge
        );
    });
    steps.lock().unwrap().extend([
        token,
        step(
            Method::GET,
            "/channels",
            200,
            json!({"items":[{"id":"UC_mock_channel","snippet":{"title":"Business channel"}}]}),
        ),
    ]);
    let id = youtube::finish_with_endpoints(&s, &v, "tenant", &c, &a.state, "mock-code", &e)
        .await
        .unwrap();
    let (net, external, access, refresh) = s.account("tenant", &id).unwrap();
    assert_eq!(net, "youtube");
    assert_eq!(external, "UC_mock_channel");
    assert_ne!(access, "mock-access");
    let label = account_label("tenant", "youtube", &external);
    assert!(v.open(&access, &label).unwrap() == "mock-access");
    assert!(v.open(&refresh.unwrap(), &label).unwrap() == "mock-refresh");
    assert_eq!(
        s.list_accounts("tenant").unwrap()[0].display_name,
        "Business channel"
    );
    assert!(s.account("other", &id).is_err());
    assert!(
        youtube::finish_with_endpoints(&s, &v, "tenant", &c, &a.state, "mock-code", &e)
            .await
            .is_err()
    );
    steps
        .lock()
        .unwrap()
        .push_back(step(Method::POST, "/revoke", 503, json!({})));
    s.mark_reauth("tenant", &id).unwrap();
    assert!(s.account("tenant", &id).is_err());
    youtube::disconnect_with_endpoints(&s, &v, "tenant", &id, &e)
        .await
        .unwrap();
    assert!(s.account("tenant", &id).is_err());
    assert!(s.refresh_candidate("tenant", &id).is_err());
    assert!(steps.lock().unwrap().is_empty());
    task.abort();
}
#[tokio::test]
async fn missing_refresh_or_upload_scope_never_links() {
    let (s, v, c) = seed();
    let (base, steps, task) = server().await;
    for mutation in ["refresh_token", "scope"] {
        let mut g = grant();
        g[mutation] = json!("");
        steps
            .lock()
            .unwrap()
            .push_back(step(Method::POST, "/token", 200, g));
        let a = youtube::start(&s, &v, "tenant", &c).unwrap();
        let err = youtube::finish_with_endpoints(
            &s,
            &v,
            "tenant",
            &c,
            &a.state,
            "mock-code",
            &endpoints(&base),
        )
        .await
        .unwrap_err();
        assert_eq!(err, "YouTube did not grant upload access");
    }
    assert!(s.list_accounts("tenant").unwrap().is_empty());
    task.abort();
}
#[tokio::test]
async fn invalid_grant_marks_needs_reauth_and_refresh_keeps_existing_refresh_credential() {
    let (s, v, c) = seed();
    let label = account_label("tenant", "youtube", "channel");
    let access = v.seal("mock-access", &label).unwrap();
    let refresh = v.seal("mock-refresh", &label).unwrap();
    let id = s
        .upsert_verified_account(concierge_social::store::VerifiedAccount {
            customer: "tenant",
            network: "youtube",
            external_id: "channel",
            display_name: "Business channel",
            token_enc: &access,
            refresh_enc: Some(&refresh),
            expires_at: Some(1),
            granted_scopes: youtube::SCOPES,
        })
        .unwrap();
    let (base, steps, task) = server().await;
    steps.lock().unwrap().push_back(step(
        Method::POST,
        "/token",
        200,
        json!({"access_token":"mock-next","expires_in":3600}),
    ));
    youtube::refresh_with_endpoints(&s, &v, "tenant", &id, &c, &endpoints(&base))
        .await
        .unwrap();
    assert!(s.account("tenant", &id).unwrap().3 == Some(refresh));
    steps.lock().unwrap().push_back(step(
        Method::POST,
        "/token",
        400,
        json!({"error":"invalid_grant","error_description":"untrusted detail"}),
    ));
    let error = youtube::refresh_with_endpoints(&s, &v, "tenant", &id, &c, &endpoints(&base))
        .await
        .unwrap_err();
    assert!(!error.contains("untrusted"));
    assert!(s.list_accounts("tenant").unwrap()[0].needs_reauth);
    task.abort();
}
#[test]
fn metadata_defaults_private_and_checks_unicode_title_bytes_and_privacy() {
    assert_eq!(
        youtube_publish::metadata(&json!({"title":"Reviewed video"})).unwrap()["status"]
            ["privacyStatus"],
        "private"
    );
    for options in [
        json!({}),
        json!({"title":"<bad>"}),
        json!({"title":"x".repeat(101)}),
        json!({"title":"Video","description":"😀".repeat(1251)}),
        json!({"title":"Video","privacy":"invalid"}),
    ] {
        assert!(youtube_publish::metadata(&options).is_err());
    }
    assert!(youtube_publish::metadata(
        &json!({"title":"😀".repeat(100),"description":"😀".repeat(1250)})
    )
    .is_ok());
}
// This single test owns the publishing switches for this integration-test process.
#[tokio::test]
async fn resumable_upload_approval_switches_and_reconciliation_protocol() {
    let _environment = ENV_LOCK.lock().await;
    let (s, v, _) = seed();
    let account = s
        .add_account(
            "tenant",
            "youtube",
            "channel",
            "Business channel",
            &v.seal(
                "mock-access",
                &account_label("tenant", "youtube", "channel"),
            )
            .unwrap(),
            None,
        )
        .unwrap();
    let dir = std::env::temp_dir().join(format!("youtube-test-{}", std::process::id()));
    std::fs::create_dir_all(dir.join("tenant")).unwrap();
    let bytes = vec![7u8; 8 * 256 * 1024 + 17];
    let path = dir.join("tenant/video.bin");
    std::fs::write(&path, &bytes).unwrap();
    let asset = Asset {
        id: "video".into(),
        kind: "video".into(),
        mime: "video/mp4".into(),
        bytes: bytes.len() as u64,
        width: 1,
        height: 1,
        duration_seconds: 1.0,
        path,
    };
    std::fs::write(
        dir.join("tenant/video.json"),
        serde_json::to_vec(&asset).unwrap(),
    )
    .unwrap();
    std::env::set_var("SOCIAL_MEDIA_DIR", &dir);
    let (base, steps, task) = server().await;
    let connector = Arc::new(YouTube::with_upload_endpoint(&format!("{base}/init")).unwrap());
    let mut registry = Registry::new();
    registry.register(connector.clone());
    let make = || NewPost {
        content: "Reviewed video".into(),
        link: String::new(),
        hashtags: String::new(),
        account_ids: vec![account.clone()],
        media: vec!["upload:video".into()],
        options: json!({"title":"Reviewed video","description":"Reviewed description"}),
    };
    let post = s.create_post("tenant", make()).unwrap();
    let now = concierge_social::now_unix();
    std::env::set_var("SOCIAL_ENABLE_PUBLISH", "true");
    std::env::set_var("SOCIAL_ENABLE_YOUTUBE_PUBLISH", "true");
    assert_eq!(scheduler::run_due(&s, &v, &registry, now).await.unwrap(), 0);
    s.submit("tenant", &post.id).unwrap();
    let approval = s
        .create_approval("tenant", &post.id, now, now + 100)
        .unwrap();
    assert_eq!(scheduler::run_due(&s, &v, &registry, now).await.unwrap(), 0);
    s.decide("tenant", &approval, true, now).unwrap();
    // Enforce scopes at the scheduler as well as at OAuth finish.
    // add_account has no grant, so the approved post must still fail closed.
    assert_eq!(scheduler::run_due(&s, &v, &registry, now).await.unwrap(), 0);
    assert_eq!(
        s.get_post("tenant", &post.id).unwrap().status,
        Status::Failed
    );
    let encrypted = v
        .seal(
            "mock-access",
            &account_label("tenant", "youtube", "channel"),
        )
        .unwrap();
    s.upsert_verified_account(concierge_social::store::VerifiedAccount {
        customer: "tenant",
        network: "youtube",
        external_id: "channel",
        display_name: "Business channel",
        token_enc: &encrypted,
        refresh_enc: None,
        expires_at: None,
        granted_scopes: youtube::SCOPES,
    })
    .unwrap();
    for value in ["false", "TRUE"] {
        std::env::set_var("SOCIAL_ENABLE_YOUTUBE_PUBLISH", value);
        let p = s.create_post("tenant", make()).unwrap();
        s.submit("tenant", &p.id).unwrap();
        let a = s.create_approval("tenant", &p.id, now, now + 100).unwrap();
        s.decide("tenant", &a, true, now).unwrap();
        assert_eq!(scheduler::run_due(&s, &v, &registry, now).await.unwrap(), 0);
        assert!(s
            .get_post("tenant", &p.id)
            .unwrap()
            .last_error
            .unwrap()
            .contains("not enabled"));
    }
    std::env::set_var("SOCIAL_ENABLE_YOUTUBE_PUBLISH", "true");
    std::env::set_var("SOCIAL_ENABLE_PUBLISH", "TRUE");
    assert!(!youtube_publish::enabled());
    std::env::set_var("SOCIAL_ENABLE_PUBLISH", "true");
    let total = bytes.len();
    let mut init = step(Method::POST, "/init", 200, json!({}));
    init.headers.push(("Location", format!("{base}/upload")));
    init.check = Box::new(move |h, b| {
        assert_eq!(h["x-upload-content-length"], total.to_string());
        assert_eq!(h["x-upload-content-type"], "video/mp4");
        let body: Value = serde_json::from_slice(b).unwrap();
        assert_eq!(body["status"]["privacyStatus"], "private");
        assert_eq!(body["status"]["selfDeclaredMadeForKids"], false);
    });
    let mut partial = step(Method::PUT, "/upload", 308, json!({}));
    partial.headers.push(("Range", "bytes=0-262143".into()));
    partial.check = Box::new(move |h, b| {
        assert_eq!(
            h["content-range"],
            format!("bytes 0-{}/{}", 8 * 256 * 1024 - 1, total)
        );
        assert_eq!(b.len(), 8 * 256 * 1024);
    });
    let retry = step(Method::PUT, "/upload", 503, json!({}));
    let mut query = step(Method::PUT, "/upload", 308, json!({}));
    query.headers.push(("Range", "bytes=0-2097151".into()));
    query.check = Box::new(move |h, b| {
        assert_eq!(h["content-range"], format!("bytes */{total}"));
        assert!(b.is_empty());
    });
    let mut complete = step(Method::PUT, "/upload", 201, json!({"id":"mock_video"}));
    complete.check = Box::new(move |h, b| {
        assert_eq!(
            h["content-range"],
            format!("bytes 2097152-{}/{}", total - 1, total)
        );
        assert_eq!(b.len(), 17);
    });
    steps
        .lock()
        .unwrap()
        .extend([init, partial, retry, query, complete]);
    let p = s.create_post("tenant", make()).unwrap();
    s.submit("tenant", &p.id).unwrap();
    let a = s.create_approval("tenant", &p.id, now, now + 100).unwrap();
    s.decide("tenant", &a, true, now).unwrap();
    assert_eq!(scheduler::run_due(&s, &v, &registry, now).await.unwrap(), 1);
    assert_eq!(
        s.get_post("tenant", &p.id).unwrap().status,
        Status::Published
    );
    assert_eq!(
        s.result_url("tenant", &p.id, &account).unwrap().as_deref(),
        Some("https://www.youtube.com/watch?v=mock_video")
    );
    assert!(s.result_url("other", &p.id, &account).unwrap().is_none());
    assert!(steps.lock().unwrap().is_empty());
    let mut request = PublishRequest {
        external_id: "channel".into(),
        idempotency_key: "mock".into(),
        access_token: "mock-access".into(),
        refresh_token: None,
        text: "Reviewed".into(),
        link: String::new(),
        media: vec!["upload:video".into()],
        options: json!({"title":"Reviewed"}),
        local_media: Some(asset),
    };
    request.local_media.as_mut().unwrap().kind = "image".into();
    assert!(connector.publish(request).await.is_err());
    task.abort();
    std::env::remove_var("SOCIAL_ENABLE_PUBLISH");
    std::env::remove_var("SOCIAL_ENABLE_YOUTUBE_PUBLISH");
    std::env::remove_var("SOCIAL_MEDIA_DIR");
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test]
async fn google_upload_errors_are_static_and_session_location_cannot_leak_credentials() {
    let _environment = ENV_LOCK.lock().await;
    std::env::set_var("SOCIAL_ENABLE_PUBLISH", "true");
    std::env::set_var("SOCIAL_ENABLE_YOUTUBE_PUBLISH", "true");
    let (base, steps, task) = server().await;
    let path = std::env::temp_dir().join(format!("youtube-errors-{}", std::process::id()));
    std::fs::write(&path, [0u8; 1]).unwrap();
    let make = || PublishRequest {
        external_id: "channel".into(),
        idempotency_key: "mock".into(),
        access_token: "mock-access".into(),
        refresh_token: None,
        text: "Reviewed video".into(),
        link: String::new(),
        media: vec!["upload:video".into()],
        options: json!({"title":"Reviewed video"}),
        local_media: Some(Asset {
            id: "video".into(),
            kind: "video".into(),
            mime: "video/mp4".into(),
            bytes: 1,
            width: 1,
            height: 1,
            duration_seconds: 1.0,
            path: path.clone(),
        }),
    };
    let connector = YouTube::with_upload_endpoint(&format!("{base}/init")).unwrap();
    for (reason, expected) in [
        ("quotaExceeded", "quota reached"),
        ("uploadLimitExceeded", "upload limit"),
        ("forbidden", "denied upload access"),
    ] {
        steps.lock().unwrap().push_back(step(
            Method::POST,
            "/init",
            403,
            json!({"error":{"errors":[{"reason":reason}],"message":"untrusted body"}}),
        ));
        match connector.publish(make()).await.unwrap_err() {
            concierge_social::connector::ConnectorError::Permanent(message) => {
                assert!(message.contains(expected));
                assert!(!message.contains("untrusted"));
            }
            _ => panic!("expected a permanent safe error"),
        }
    }
    steps.lock().unwrap().push_back(step(
        Method::POST,
        "/init",
        401,
        json!({"error":"invalid_grant"}),
    ));
    assert!(matches!(
        connector.publish(make()).await,
        Err(concierge_social::connector::ConnectorError::AuthExpired(_))
    ));
    let mut redirect = step(Method::POST, "/init", 200, json!({}));
    redirect
        .headers
        .push(("Location", "http://example.invalid/upload".into()));
    steps.lock().unwrap().push_back(redirect);
    assert!(connector.publish(make()).await.is_err());
    assert!(steps.lock().unwrap().is_empty());
    std::fs::remove_file(path).unwrap();
    task.abort();
    std::env::remove_var("SOCIAL_ENABLE_PUBLISH");
    std::env::remove_var("SOCIAL_ENABLE_YOUTUBE_PUBLISH");
}

#[test]
fn legacy_default_rules_gain_youtube_without_overriding_custom_platform_policy() {
    let (s, _, _) = seed();
    let mut rules = concierge_social::guardrails::Rules::default();
    rules.platforms.remove("youtube");
    rules.forbidden_phrases.push("blocked phrase".into());
    s.update_rules("tenant", &rules).unwrap();
    let upgraded = s.rules("tenant").unwrap();
    assert!(upgraded.platforms.contains_key("youtube"));
    assert_eq!(upgraded.forbidden_phrases, rules.forbidden_phrases);
    rules.platforms.remove("facebook");
    s.update_rules("tenant", &rules).unwrap();
    assert!(!s.rules("tenant").unwrap().platforms.contains_key("youtube"));
}
