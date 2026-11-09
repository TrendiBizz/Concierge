//! HTTP-level tests with a fake Concierge. They also pin the exact JSON sent to Concierge (`tests/fixtures/execute_bundle.json`),
//! which the Python suite posts to the real endpoint, so the two sides cannot drift apart silently.
use async_trait::async_trait;
use axum::body::Body;
use axum::http::{Request, StatusCode};
use concierge_core::contact::contact_key;
use hermes_gateway::backend::{Backend, BackendError};
use hermes_gateway::capability::verify;
use hermes_gateway::ledger::MemoryLedger;
use hermes_gateway::ops::Op;
use hermes_gateway::policy::{Autonomy, PolicyContext, WorkflowPolicy};
use hermes_gateway::server::{router, AppState};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};
use tower::ServiceExt;

const NOW: i64 = 1_800_000_000;
const SECRET: &str = "capability-secret-not-real-0123456789abcdef";
const MINT: &str = "mint-key-not-real-0123456789abcdefghijkl";
const TENANT: &str = "00000000-0000-0000-0000-0000000000a1";
const CASE: &str = "00000000-0000-0000-0000-0000000000c1";

struct Fake {
    ctx: Mutex<PolicyContext>,
    executed: Mutex<Vec<Value>>,
    refuse: Mutex<Option<(u16, Value)>>,
    down: Mutex<bool>,
}

#[async_trait]
impl Backend for Fake {
    async fn policy_context(
        &self,
        tenant_id: &str,
        _case_id: &str,
    ) -> Result<PolicyContext, BackendError> {
        if *self.down.lock().unwrap() {
            return Err(BackendError::Unavailable("connection refused".into()));
        }
        let ctx = self.ctx.lock().unwrap().clone();
        if ctx.tenant_id != tenant_id {
            Err(BackendError::NotFound)
        } else {
            Ok(ctx)
        }
    }
    async fn execute(&self, _t: &str, _c: &str, bundle: &Value) -> Result<Value, BackendError> {
        self.executed.lock().unwrap().push(bundle.clone());
        match self.refuse.lock().unwrap().clone() {
            Some((status, body)) => Err(BackendError::Refused { status, body }),
            None => Ok(json!({"actions": [], "delivery": {"state": "draft_created"}})),
        }
    }
}

fn ctx(autonomy: Autonomy) -> PolicyContext {
    PolicyContext {
        tenant_id: TENANT.into(),
        case_id: CASE.into(),
        case_version: 7,
        automation_paused: false,
        timezone: "Pacific/Auckland".parse().unwrap(),
        default_country_code: "64".into(),
        email_send_authorized: true,
        sms_send_authorized: true,
        case_contacts: HashSet::from([contact_key("ann@example.com", "64")]),
        suppressed: HashSet::new(),
        knowledge_evidence: "Standard service is $120.".into(),
        workflow: WorkflowPolicy {
            autonomy,
            min_confidence: 0.8,
        },
        approvals: HashMap::new(),
    }
}

fn app(autonomy: Autonomy, clock_offset: i64) -> (axum::Router, Arc<Fake>) {
    let fake = Arc::new(Fake {
        ctx: Mutex::new(ctx(autonomy)),
        executed: Mutex::new(vec![]),
        refuse: Mutex::new(None),
        down: Mutex::new(false),
    });
    let state = Arc::new(AppState {
        secret: SECRET.as_bytes().to_vec(),
        mint_key: MINT.into(),
        backend: fake.clone(),
        revoked: Mutex::new(HashSet::new()),
        ledger: Mutex::new(MemoryLedger::default()),
        clock: Box::new(move || NOW + clock_offset),
    });
    (router(state), fake)
}

async fn call(
    app: &axum::Router,
    method: &str,
    uri: &str,
    bearer: Option<&str>,
    body: &str,
) -> (StatusCode, Value) {
    let mut req = Request::builder()
        .method(method)
        .uri(uri)
        .header("content-type", "application/json");
    if let Some(b) = bearer {
        req = req.header("authorization", format!("Bearer {b}"));
    }
    let resp = app
        .clone()
        .oneshot(req.body(Body::from(body.to_string())).unwrap())
        .await
        .unwrap();
    let status = resp.status();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    (
        status,
        serde_json::from_slice(&bytes).unwrap_or(Value::Null),
    )
}

async fn token(app: &axum::Router, ops: &[&str]) -> String {
    let (s, v) = call(app, "POST", "/v1/capabilities", Some(MINT), &json!({"tenant_id": TENANT, "case_id": CASE, "run_id": "run-1", "ops": ops, "ttl_secs": 300}).to_string()).await;
    assert_eq!(s, StatusCode::OK, "{v}");
    v["token"].as_str().unwrap().to_string()
}

const ALL_OPS: [&str; 3] = ["prepare_reply", "schedule_followup", "escalate_case"];

fn plan(extra: Value) -> String {
    let mut p = json!({"task_id": "task-1", "intent": "factual_question", "next_step": "reply to Ann", "confidence": 0.95,
        "proposed_actions": [{"op": "schedule_followup", "idempotency_key": "k-1", "expected_case_version": 7, "params": {"title": "Call Ann", "due_at": "2027-01-18T09:00:00+13:00"}}],
        "customer_draft": {"channel": "email", "recipient": "ann@example.com", "subject": "Opening hours", "body": "We open at 9am."}});
    for (k, v) in extra.as_object().unwrap() {
        p[k] = v.clone();
    }
    p.to_string()
}

#[tokio::test]
async fn health_and_capability_minting() {
    let (app, _) = app(Autonomy::DraftReview, 0);
    assert_eq!(
        call(&app, "GET", "/healthz", None, "").await.0,
        StatusCode::OK
    );
    let body =
        json!({"tenant_id": TENANT, "case_id": CASE, "run_id": "r", "ops": ["prepare_reply"]})
            .to_string();
    assert_eq!(
        call(&app, "POST", "/v1/capabilities", None, &body).await.0,
        StatusCode::UNAUTHORIZED
    );
    assert_eq!(
        call(&app, "POST", "/v1/capabilities", Some("wrong"), &body)
            .await
            .0,
        StatusCode::UNAUTHORIZED
    );
    let bad = json!({"tenant_id": TENANT, "case_id": CASE, "run_id": "r", "ops": ["run_shell"]})
        .to_string();
    assert_eq!(
        call(&app, "POST", "/v1/capabilities", Some(MINT), &bad)
            .await
            .0,
        StatusCode::UNPROCESSABLE_ENTITY
    );
    let long = json!({"tenant_id": TENANT, "case_id": CASE, "run_id": "r", "ops": ["prepare_reply"], "ttl_secs": 86_400}).to_string();
    let (s, v) = call(&app, "POST", "/v1/capabilities", Some(MINT), &long).await;
    assert_eq!(s, StatusCode::OK);
    let cap = verify(
        SECRET.as_bytes(),
        v["token"].as_str().unwrap(),
        NOW + 1,
        &|_| false,
    )
    .unwrap();
    assert_eq!(
        (cap.expires_at - cap.issued_at, cap.ops),
        (900, vec![Op::PrepareReply]),
        "a day-long request is clamped to 15 minutes"
    );
}

#[tokio::test]
async fn shadow_mode_validates_but_never_calls_concierge() {
    let (app, fake) = app(Autonomy::Shadow, 0);
    let t = token(&app, &ALL_OPS).await;
    let (s, v) = call(&app, "POST", "/v1/plans", Some(&t), &plan(json!({}))).await;
    assert_eq!(
        (s, v["mode"].as_str(), v["executed"].as_bool()),
        (StatusCode::OK, Some("shadow"), Some(false))
    );
    assert!(
        fake.executed.lock().unwrap().is_empty(),
        "shadow mode must not reach Concierge"
    );
    assert_eq!(v["would_execute"]["delivery"]["mode"], "shadow_only");
}

#[tokio::test]
async fn reviewed_mode_sends_the_exact_pinned_bundle_to_concierge() {
    let (app, fake) = app(Autonomy::DraftReview, 0);
    let t = token(&app, &ALL_OPS).await;
    let (s, v) = call(&app, "POST", "/v1/plans", Some(&t), &plan(json!({}))).await;
    assert_eq!(
        (s, v["mode"].as_str()),
        (StatusCode::OK, Some("executed")),
        "{v}"
    );
    let sent = fake.executed.lock().unwrap()[0].clone();
    assert_eq!(
        sent["delivery"]["mode"], "needs_approval",
        "draft-review autonomy never sends by itself"
    );
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/tests/fixtures/execute_bundle.json"
    );
    if std::env::var("UPDATE_FIXTURES").is_ok() {
        std::fs::write(path, serde_json::to_string_pretty(&sent).unwrap() + "\n").unwrap();
    }
    let golden: Value = serde_json::from_str(
        &std::fs::read_to_string(path).expect("fixture (run with UPDATE_FIXTURES=1 once)"),
    )
    .unwrap();
    assert_eq!(sent, golden, "the wire format Concierge accepts changed; update the fixture and the Python model together");
}

#[tokio::test]
async fn bad_capabilities_are_refused() {
    let (app, fake) = app(Autonomy::DraftReview, 0);
    let good = token(&app, &ALL_OPS).await;
    for bearer in [None, Some("garbage"), Some("a.b")] {
        assert_eq!(
            call(&app, "POST", "/v1/plans", bearer, &plan(json!({})))
                .await
                .0,
            StatusCode::UNAUTHORIZED
        );
    }
    let tampered = format!("{}x", good);
    assert_eq!(
        call(&app, "POST", "/v1/plans", Some(&tampered), &plan(json!({})))
            .await
            .0,
        StatusCode::UNAUTHORIZED
    );
    let (late, _) = {
        let s = Arc::new(AppState {
            secret: SECRET.as_bytes().to_vec(),
            mint_key: MINT.into(),
            backend: fake.clone(),
            revoked: Mutex::new(HashSet::new()),
            ledger: Mutex::new(MemoryLedger::default()),
            clock: Box::new(|| NOW + 301),
        });
        (router(s), ())
    };
    assert_eq!(
        call(&late, "POST", "/v1/plans", Some(&good), &plan(json!({})))
            .await
            .0,
        StatusCode::UNAUTHORIZED,
        "expired"
    );
    let (s, v) = call(
        &app,
        "POST",
        "/v1/capabilities",
        Some(MINT),
        &json!({"tenant_id": TENANT, "case_id": CASE, "run_id": "r2", "ops": ["prepare_reply"]})
            .to_string(),
    )
    .await;
    assert_eq!(s, StatusCode::OK);
    let nonce = v["nonce"].as_str().unwrap();
    assert_eq!(
        call(
            &app,
            "DELETE",
            &format!("/v1/capabilities/{nonce}"),
            None,
            ""
        )
        .await
        .0,
        StatusCode::UNAUTHORIZED,
        "revoking needs the mint key"
    );
    assert_eq!(
        call(
            &app,
            "DELETE",
            &format!("/v1/capabilities/{nonce}"),
            Some(MINT),
            ""
        )
        .await
        .0,
        StatusCode::OK
    );
    assert_eq!(
        call(
            &app,
            "POST",
            "/v1/plans",
            Some(v["token"].as_str().unwrap()),
            &plan(json!({}))
        )
        .await
        .0,
        StatusCode::UNAUTHORIZED,
        "revoked"
    );
    assert!(fake.executed.lock().unwrap().is_empty());
}

#[tokio::test]
async fn hostile_or_unsafe_plans_never_reach_concierge() {
    let (app, fake) = app(Autonomy::DraftReview, 0);
    let t = token(&app, &ALL_OPS).await;
    assert_eq!(
        call(&app, "POST", "/v1/plans", Some(&t), "not json")
            .await
            .0,
        StatusCode::BAD_REQUEST
    );
    let (s, _) = call(
        &app,
        "POST",
        "/v1/plans",
        Some(&t),
        &plan(json!({"tenant_id": "someone-else"})),
    )
    .await;
    assert_eq!(s, StatusCode::BAD_REQUEST, "a plan cannot name a tenant");
    let inject = plan(
        json!({"customer_draft": {"channel": "email", "recipient": "attacker@evil.test", "body": "see attached"}}),
    );
    let (s, v) = call(&app, "POST", "/v1/plans", Some(&t), &inject).await;
    assert_eq!(
        (s, v["rejected"]["code"].as_str()),
        (
            StatusCode::UNPROCESSABLE_ENTITY,
            Some("recipient_not_on_case")
        )
    );
    let priced = plan(
        json!({"customer_draft": {"channel": "email", "recipient": "ann@example.com", "body": "Only $5!"}}),
    );
    assert_eq!(
        call(&app, "POST", "/v1/plans", Some(&t), &priced).await.1["rejected"]["code"],
        "price_not_in_evidence"
    );
    let shell = plan(
        json!({"proposed_actions": [{"op": "run_shell", "idempotency_key": "k", "expected_case_version": 7}]}),
    );
    assert_eq!(
        call(&app, "POST", "/v1/plans", Some(&t), &shell).await.1["rejected"]["code"],
        "unknown_operation"
    );
    let big = "x".repeat(130 * 1024);
    assert_eq!(
        call(&app, "POST", "/v1/plans", Some(&t), &big).await.0,
        StatusCode::PAYLOAD_TOO_LARGE
    );
    assert!(
        fake.executed.lock().unwrap().is_empty(),
        "nothing hostile may reach Concierge"
    );
}

#[tokio::test]
async fn a_capability_only_opens_its_own_tenant() {
    let (app, fake) = app(Autonomy::DraftReview, 0);
    let (_, v) = call(&app, "POST", "/v1/capabilities", Some(MINT), &json!({"tenant_id": "00000000-0000-0000-0000-0000000000b2", "case_id": CASE, "run_id": "r", "ops": ["prepare_reply"]}).to_string()).await;
    let (s, _) = call(
        &app,
        "POST",
        "/v1/plans",
        Some(v["token"].as_str().unwrap()),
        &plan(json!({})),
    )
    .await;
    assert_eq!(
        s,
        StatusCode::NOT_FOUND,
        "tenant B's capability cannot reach tenant A's case"
    );
    assert!(fake.executed.lock().unwrap().is_empty());
}

#[tokio::test]
async fn concierge_refusals_and_outages_are_reported_honestly() {
    let (app, fake) = app(Autonomy::DraftReview, 0);
    let t = token(&app, &ALL_OPS).await;
    *fake.refuse.lock().unwrap() = Some((409, json!({"detail": {"error": "stale_case"}})));
    let (s, v) = call(&app, "POST", "/v1/plans", Some(&t), &plan(json!({}))).await;
    assert_eq!(
        (
            s,
            v["error"].as_str(),
            v["detail"]["detail"]["error"].as_str()
        ),
        (
            StatusCode::CONFLICT,
            Some("refused_by_concierge"),
            Some("stale_case")
        )
    );
    *fake.refuse.lock().unwrap() = None;
    *fake.down.lock().unwrap() = true;
    assert_eq!(
        call(&app, "POST", "/v1/plans", Some(&t), &plan(json!({})))
            .await
            .0,
        StatusCode::SERVICE_UNAVAILABLE
    );
}

#[tokio::test]
async fn idempotency_keys_cannot_be_reused_for_different_work() {
    let (app, fake) = app(Autonomy::DraftReview, 0);
    let t = token(&app, &ALL_OPS).await;
    let first = plan(json!({}));
    assert_eq!(
        call(&app, "POST", "/v1/plans", Some(&t), &first).await.0,
        StatusCode::OK
    );
    assert_eq!(
        call(&app, "POST", "/v1/plans", Some(&t), &first).await.0,
        StatusCode::OK,
        "an exact repeat is forwarded; Concierge answers it as a duplicate"
    );
    let changed = plan(
        json!({"proposed_actions": [{"op": "schedule_followup", "idempotency_key": "k-1", "expected_case_version": 7, "params": {"title": "Something else"}}]}),
    );
    let (s, v) = call(&app, "POST", "/v1/plans", Some(&t), &changed).await;
    assert_eq!(
        (s, v["error"].as_str()),
        (StatusCode::CONFLICT, Some("key_reuse"))
    );
    assert_eq!(
        fake.executed.lock().unwrap().len(),
        2,
        "the conflicting plan was stopped before Concierge"
    );
}
