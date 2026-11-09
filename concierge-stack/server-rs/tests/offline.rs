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

/// The empirical answer to "does the owner boundary compose onto a token-in-path route?".
///
/// Python's `owner_boundary` middleware guards only `/owner-ui`, `/owner/*` and `/api/v1/device-sms/*`, so
/// `/report/{token}` must NOT be origin-gated and must NOT carry the three hardening headers: the unguessable
/// token is the credential, and a report is opened from wherever the owner happens to be. These tests pin that
/// against the risk of someone "helpfully" widening the protected-path list later.
#[tokio::test]
async fn report_route_is_not_behind_the_owner_boundary() {
    // A foreign Origin must not produce the 403 the boundary gives protected paths. Without a database the
    // handler itself answers 500 (the same shape the other database routes take), which is the point: the
    // boundary let the request through instead of refusing it.
    for origin in ["https://evil.example", "http://elsewhere.example", ""] {
        let req = Request::get("/report/rt_x")
            .header("host", "c.example")
            .header("origin", origin)
            .body(Body::empty())
            .unwrap();
        let (s, h, _) = call(router("x"), req).await;
        assert_ne!(
            s,
            StatusCode::FORBIDDEN,
            "origin {origin:?} must not be refused"
        );
        assert_eq!(
            h.get("cache-control"),
            None,
            "origin {origin:?} must not be hardened"
        );
        assert_eq!(
            h.get("x-content-type-options"),
            None,
            "origin {origin:?} must not be hardened"
        );
        assert_eq!(
            h.get("referrer-policy"),
            None,
            "origin {origin:?} must not be hardened"
        );
    }
    // The same request against a genuinely protected path is still refused, so the test cannot pass by
    // the middleware being absent altogether.
    let req = Request::get("/owner/leads")
        .header("host", "c.example")
        .header("origin", "https://evil.example")
        .body(Body::empty())
        .unwrap();
    let (s, _, _) = call(router("x"), req).await;
    assert_eq!(s, StatusCode::FORBIDDEN);
}

/// `days` is parsed like pydantic and clamped like `_stats`, before any database work.
#[tokio::test]
async fn report_days_is_validated_before_the_database() {
    for bad in ["abc", "1.5", "1e2", "0x10", ""] {
        let req = Request::get(format!("/report/rt_x?days={bad}"))
            .body(Body::empty())
            .unwrap();
        let (s, _, b) = call(router("x"), req).await;
        assert_eq!(s, StatusCode::UNPROCESSABLE_ENTITY, "days={bad:?}");
        let v: Value = serde_json::from_slice(&b).unwrap();
        let d = &v["detail"][0];
        assert_eq!(d["type"], "int_parsing", "days={bad:?}");
        assert_eq!(d["loc"], json!(["query", "days"]), "days={bad:?}");
        assert_eq!(d["input"], bad, "days={bad:?}");
    }
    // Accepted values pass validation and reach the database, which is absent here: 500, not 422.
    for good in [
        "1",
        "30",
        "365",
        "366",
        "0",
        "-5",
        " 7 ",
        "+7",
        "1000000000000000000000000",
    ] {
        let req = Request::get(format!(
            "/report/rt_x?days={}",
            good.replace(' ', "%20").replace('+', "%2B")
        ))
        .body(Body::empty())
        .unwrap();
        let (s, _, _) = call(router("x"), req).await;
        assert_eq!(
            s,
            StatusCode::INTERNAL_SERVER_ERROR,
            "days={good:?} should be accepted"
        );
    }
}
