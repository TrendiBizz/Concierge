use axum::{
    body::Body,
    http::{Request, StatusCode},
};
use base64::Engine;
use concierge_social::{
    api::{router, AppState},
    store::Store,
    vault::Vault,
};
use std::sync::Arc;
use tower::ServiceExt;

fn setup() -> (AppState, String, String) {
    let store = Arc::new(Store::open_memory().unwrap());
    store
        .create_customer("customer-a", "A", "a@example.test")
        .unwrap();
    store
        .create_customer("customer-b", "B", "b@example.test")
        .unwrap();
    let a = store.rotate_agent_key("customer-a").unwrap();
    let b = store.rotate_agent_key("customer-b").unwrap();
    let vault = Arc::new(
        Vault::from_base64_key(&base64::engine::general_purpose::STANDARD.encode([55u8; 32]))
            .unwrap(),
    );
    (
        AppState {
            store,
            vault,
            concierge_key: "concierge-supervisor-012345678901".into(),
            agent_key: "legacy-global-agent-01234567890".into(),
        },
        a,
        b,
    )
}
async fn get_status(app: axum::Router, customer: &str, key: &str) -> StatusCode {
    app.oneshot(
        Request::builder()
            .uri(format!("/v1/customers/{customer}/rules"))
            .header("authorization", format!("Bearer {key}"))
            .body(Body::empty())
            .unwrap(),
    )
    .await
    .unwrap()
    .status()
}
#[tokio::test]
async fn tenant_agent_key_is_scoped_and_legacy_key_is_denied() {
    let (state, a, b) = setup();
    let app = router(state.clone());
    assert_eq!(
        get_status(app.clone(), "customer-a", &a).await,
        StatusCode::OK
    );
    assert_eq!(
        get_status(app.clone(), "customer-b", &b).await,
        StatusCode::OK
    );
    assert_eq!(
        get_status(app.clone(), "customer-b", &a).await,
        StatusCode::FORBIDDEN
    );
    assert_eq!(
        get_status(app.clone(), "customer-a", &b).await,
        StatusCode::FORBIDDEN
    );
    assert_eq!(
        get_status(app.clone(), "customer-a", &state.agent_key).await,
        StatusCode::FORBIDDEN
    );
    assert_eq!(
        get_status(app, "customer-b", &state.concierge_key).await,
        StatusCode::OK
    );
}
#[tokio::test]
async fn tenant_key_rotation_revokes_previous_key_only() {
    let (state, old, b) = setup();
    let newer = state.store.rotate_agent_key("customer-a").unwrap();
    assert_ne!(old, newer);
    let app = router(state);
    assert_eq!(
        get_status(app.clone(), "customer-a", &old).await,
        StatusCode::FORBIDDEN
    );
    assert_eq!(
        get_status(app.clone(), "customer-a", &newer).await,
        StatusCode::OK
    );
    assert_eq!(get_status(app, "customer-b", &b).await, StatusCode::OK);
}
#[tokio::test]
async fn tenant_key_cannot_approve_or_rotate() {
    let (state, a, _) = setup();
    let app = router(state);
    for path in [
        "/v1/customers/customer-a/agent-key",
        "/v1/customers/customer-a/approvals/example/approve",
    ] {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri(path)
                    .method("POST")
                    .header("authorization", format!("Bearer {a}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }
}

#[tokio::test]
async fn x_linking_is_owner_only_and_requires_configuration() {
    let (state, agent, _) = setup();
    let app = router(state.clone());
    for (key, expected) in [
        (&agent, StatusCode::FORBIDDEN),
        (&state.concierge_key, StatusCode::SERVICE_UNAVAILABLE),
    ] {
        let r = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/v1/customers/customer-a/oauth/x/start")
                    .header("authorization", format!("Bearer {key}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(r.status(), expected);
    }
}
