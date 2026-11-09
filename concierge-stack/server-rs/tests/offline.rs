//! Routes and rules that never reach the database, exercised in-process.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use concierge_server::{app, Config, State};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

fn router(admin: &str) -> axum::Router {
    app(State::without_database(Config {
        database_url: String::new(),
        admin_token: admin.into(),
        public_base_url: "http://localhost:8000".into(),
        voice_recording_enabled: false,
    }))
}

async fn call(r: axum::Router, req: Request<Body>) -> (StatusCode, axum::http::HeaderMap, Vec<u8>) {
    let resp = r.oneshot(req).await.unwrap();
    let (parts, body) = resp.into_parts();
    (
        parts.status,
        parts.headers,
        body.collect().await.unwrap().to_bytes().to_vec(),
    )
}

#[tokio::test]
async fn missing_key_is_the_fastapi_422() {
    let (s, _, b) = call(
        router("x"),
        Request::get("/api/v1/widget-config")
            .body(Body::empty())
            .unwrap(),
    )
    .await;
    assert_eq!(s, 422);
    let v: Value = serde_json::from_slice(&b).unwrap();
    assert_eq!(
        v,
        json!({"detail": [{"type": "missing", "loc": ["query", "key"], "msg": "Field required", "input": null}]})
    );
}

#[tokio::test]
async fn admin_gate_matches_python() {
    let (s, _, b) = call(
        router(""),
        Request::get("/admin/tenants").body(Body::empty()).unwrap(),
    )
    .await;
    assert_eq!(
        (s, serde_json::from_slice::<Value>(&b).unwrap()),
        (
            StatusCode::SERVICE_UNAVAILABLE,
            json!({"detail": "ADMIN_TOKEN is not configured"})
        )
    );
    let (s, _, b) = call(
        router("secret"),
        Request::get("/admin/tenants")
            .header("x-admin-token", "nope")
            .body(Body::empty())
            .unwrap(),
    )
    .await;
    assert_eq!(
        (s, serde_json::from_slice::<Value>(&b).unwrap()),
        (
            StatusCode::UNAUTHORIZED,
            json!({"detail": "Invalid admin token"})
        )
    );
}

#[tokio::test]
async fn owner_boundary_refuses_foreign_origin_and_hardens_owner_paths() {
    let req = Request::get("/owner/leads")
        .header("host", "c.example")
        .header("origin", "https://evil.example")
        .body(Body::empty())
        .unwrap();
    let (s, h, _) = call(router("x"), req).await;
    assert_eq!(s, 403);
    assert_eq!(h["cache-control"], "no-store");
    // an unknown owner path from the same origin is served by the router (404 here) and still gets the hardening headers
    let req = Request::get("/owner/leads")
        .header("host", "c.example")
        .header("origin", "http://c.example")
        .body(Body::empty())
        .unwrap();
    let (s, h, _) = call(router("x"), req).await;
    assert_eq!(s, 404);
    assert_eq!(h["x-content-type-options"], "nosniff");
    assert_eq!(h["referrer-policy"], "no-referrer");
}

#[tokio::test]
async fn cors_header_is_wildcard() {
    let req = Request::get("/api/v1/widget-config")
        .header("origin", "https://anything.example")
        .body(Body::empty())
        .unwrap();
    let (_, h, _) = call(router("x"), req).await;
    assert_eq!(h["access-control-allow-origin"], "*");
}
