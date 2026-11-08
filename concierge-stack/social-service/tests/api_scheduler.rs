use axum::{
    body::Body,
    http::{Request, StatusCode},
};
use base64::Engine;
use concierge_social::{
    api::{router, AppState},
    connector::{ConnectorError, MockConnector, Registry},
    model::{NewPost, Status},
    scheduler::run_due,
    store::Store,
    vault::{account_label, Vault},
};
use std::sync::Arc;
use tower::ServiceExt;

fn vault() -> Vault {
    let key = base64::engine::general_purpose::STANDARD.encode([5u8; 32]);
    Vault::from_base64_key(&key).unwrap()
}
fn seed() -> (Store, Vault, String, String) {
    let store = Store::open_memory().unwrap();
    store
        .create_customer("a", "Company A", "contact@example.com")
        .unwrap();
    let v = vault();
    let enc = v
        .seal("test-key", &account_label("a", "bluesky", "alice"))
        .unwrap();
    let account = store
        .add_account("a", "bluesky", "alice", "Alice", &enc, None)
        .unwrap();
    let post = store
        .create_post(
            "a",
            NewPost {
                options: serde_json::Value::Null,
                content: "Approved message".into(),
                link: String::new(),
                hashtags: String::new(),
                account_ids: vec![account.clone()],
                media: vec![],
            },
        )
        .unwrap();
    (store, v, post.id, account)
}
#[tokio::test]
async fn agents_cannot_approve_even_with_token() {
    let (store, v, post, _account) = seed();
    store.submit("a", &post).unwrap();
    let now = time::OffsetDateTime::now_utc().unix_timestamp();
    let token = store.create_approval("a", &post, now, now + 100).unwrap();
    let state = AppState {
        store: Arc::new(store),
        vault: Arc::new(v),
        concierge_key: "owner-key-012345678901234567890123".into(),
        agent_key: "agent-key-012345678901234567890123".into(),
    };
    let app = router(state);
    let path = format!("/v1/customers/a/approvals/{token}/approve");
    let req = Request::builder()
        .method("POST")
        .uri(&path)
        .header("authorization", "Bearer agent-key-012345678901234567890123")
        .body(Body::empty())
        .unwrap();
    let response = app.clone().oneshot(req).await.unwrap();
    assert_eq!(response.status(), StatusCode::FORBIDDEN);

    let req = Request::builder()
        .method("POST")
        .uri(&path)
        .header("authorization", "Bearer owner-key-012345678901234567890123")
        .body(Body::empty())
        .unwrap();
    let response = app.oneshot(req).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);
}
#[tokio::test]
async fn only_customer_approved_posts_reach_connector() {
    let (store, v, post, _) = seed();
    let mock = Arc::new(MockConnector::default());
    let mut registry = Registry::new();
    registry.register(mock.clone());
    let now = time::OffsetDateTime::now_utc().unix_timestamp();
    assert_eq!(run_due(&store, &v, &registry, now).await.unwrap(), 0);
    assert!(mock.requests.lock().unwrap().is_empty());
    store.submit("a", &post).unwrap();
    let token = store.create_approval("a", &post, now, now + 100).unwrap();
    assert_eq!(run_due(&store, &v, &registry, now).await.unwrap(), 0);
    store.decide("a", &token, true, now).unwrap();
    assert_eq!(run_due(&store, &v, &registry, now).await.unwrap(), 1);
    assert_eq!(
        store.get_post("a", &post).unwrap().status,
        Status::Published
    );
    assert_eq!(mock.requests.lock().unwrap().len(), 1);
    assert_eq!(run_due(&store, &v, &registry, now).await.unwrap(), 0);
}
#[tokio::test]
async fn uncertain_network_outcome_is_failed_not_automatically_replayed() {
    let (store, v, post, _) = seed();
    let mock = Arc::new(MockConnector::default());
    *mock.error.lock().unwrap() = Some(ConnectorError::Retryable("timeout".into()));
    let mut registry = Registry::new();
    registry.register(mock.clone());
    let now = time::OffsetDateTime::now_utc().unix_timestamp();
    store.submit("a", &post).unwrap();
    let token = store.create_approval("a", &post, now, now + 100).unwrap();
    store.decide("a", &token, true, now).unwrap();
    assert_eq!(run_due(&store, &v, &registry, now).await.unwrap(), 0);
    let result = store.get_post("a", &post).unwrap();
    assert_eq!(result.status, Status::Failed);
    assert!(result
        .last_error
        .unwrap()
        .contains("Reconciliation required"));
    assert_eq!(run_due(&store, &v, &registry, now + 10).await.unwrap(), 0);
    assert_eq!(mock.requests.lock().unwrap().len(), 1);
}

#[tokio::test]
async fn tightened_rules_block_previously_approved_post() {
    let (store, v, post, _) = seed();
    let mock = Arc::new(MockConnector::default());
    let mut registry = Registry::new();
    registry.register(mock.clone());
    let now = time::OffsetDateTime::now_utc().unix_timestamp();
    store.submit("a", &post).unwrap();
    let token = store.create_approval("a", &post, now, now + 100).unwrap();
    store.decide("a", &token, true, now).unwrap();
    let mut rules = store.rules("a").unwrap();
    rules.forbidden_phrases.push("approved message".into());
    store.update_rules("a", &rules).unwrap();
    assert_eq!(run_due(&store, &v, &registry, now).await.unwrap(), 0);
    assert_eq!(store.get_post("a", &post).unwrap().status, Status::Failed);
    assert!(mock.requests.lock().unwrap().is_empty());
}

#[tokio::test]
async fn social_text_contains_approved_hashtags() {
    let store = Store::open_memory().unwrap();
    store.create_customer("a", "A", "a@example.test").unwrap();
    let v = vault();
    let enc = v
        .seal("pw", &account_label("a", "bluesky", "alice"))
        .unwrap();
    let account = store
        .add_account("a", "bluesky", "alice", "Alice", &enc, None)
        .unwrap();
    let post = store
        .create_post(
            "a",
            NewPost {
                options: serde_json::Value::Null,
                content: "Hello".into(),
                link: "https://example.org".into(),
                hashtags: "#approved".into(),
                account_ids: vec![account],
                media: vec![],
            },
        )
        .unwrap();
    let now = time::OffsetDateTime::now_utc().unix_timestamp();
    store.submit("a", &post.id).unwrap();
    let token = store
        .create_approval("a", &post.id, now, now + 100)
        .unwrap();
    store.decide("a", &token, true, now).unwrap();
    let mock = Arc::new(MockConnector::default());
    let mut registry = Registry::new();
    registry.register(mock.clone());
    assert_eq!(run_due(&store, &v, &registry, now).await.unwrap(), 1);
    let requests = mock.requests.lock().unwrap();
    assert_eq!(requests[0].text, "Hello\nhttps://example.org\n#approved");
}

#[tokio::test]
async fn missing_owned_media_fails_one_job_and_preserves_other_due_work() {
    let (store, v, good, account) = seed();
    let bad = store
        .create_post(
            "a",
            NewPost {
                options: serde_json::Value::Null,
                content: "Reviewed media post".into(),
                link: String::new(),
                hashtags: String::new(),
                account_ids: vec![account],
                media: vec!["upload:missing-release-test-asset".into()],
            },
        )
        .unwrap();
    let now = time::OffsetDateTime::now_utc().unix_timestamp();
    for id in [&good, &bad.id] {
        store.submit("a", id).unwrap();
        let token = store.create_approval("a", id, now, now + 100).unwrap();
        store.decide("a", &token, true, now).unwrap();
    }
    let mock = Arc::new(MockConnector::default());
    let mut registry = Registry::new();
    registry.register(mock.clone());
    assert_eq!(run_due(&store, &v, &registry, now).await.unwrap(), 1);
    assert_eq!(store.get_post("a", &bad.id).unwrap().status, Status::Failed);
    assert_eq!(
        store.get_post("a", &good).unwrap().status,
        Status::Published
    );
    assert_eq!(mock.requests.lock().unwrap().len(), 1);
}
