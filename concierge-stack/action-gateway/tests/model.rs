//! Direct model protocol, entirely on loopback; no agent runtime or real provider.
use action_gateway::orchestrator::{ModelHttp, Planner};
use axum::{http::HeaderMap, routing::post, Json, Router};
use serde_json::{json, Value};

#[test]
fn model_configuration_is_explicit_and_credentials_require_secure_transport() {
    for base in [
        "http://example.com",
        "https://user:password@example.com",
        "https://example.com?key=secret",
        "https://example.com/#fragment",
        "file:///tmp/model",
    ] {
        assert!(ModelHttp::new(base, "test-key", "test-model").is_err());
    }
    assert!(ModelHttp::new("https://example.com/v1", "", "model").is_err());
    assert!(ModelHttp::new("https://example.com/v1", "key", " ").is_err());
    assert!(ModelHttp::new("https://example.com/v1", "key", "model").is_ok());
}

#[tokio::test]
async fn direct_model_request_uses_configured_model_and_no_agent_tools() {
    let app = Router::new().route("/v1/chat/completions", post(|headers: HeaderMap, Json(body): Json<Value>| async move {
        assert_eq!(headers["authorization"], "Bearer test-key");
        assert_eq!(body, json!({"model":"chosen-model","temperature":0.2,"messages":[{"role":"system","content":"system"},{"role":"user","content":"question"}]}));
        Json(json!({"choices":[{"message":{"content":"{\"plan\":true}"}}]}))
    }));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    for suffix in ["", "/v1", "/v1/"] {
        let client = ModelHttp::new(
            &format!("http://{addr}{suffix}"),
            "test-key",
            "chosen-model",
        )
        .unwrap();
        assert_eq!(
            client.plan("system", "question").await.unwrap(),
            "{\"plan\":true}"
        );
    }
    task.abort();
}

#[tokio::test]
async fn unusable_provider_output_is_a_failure_not_a_plan() {
    let app = Router::new().route(
        "/v1/chat/completions",
        post(|| async { Json(json!({"choices":[]})) }),
    );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let client = ModelHttp::new(&format!("http://{addr}"), "test-key", "chosen-model").unwrap();
    assert!(client.plan("system", "question").await.is_err());
    task.abort();
}
