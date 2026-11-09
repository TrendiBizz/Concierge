//! The gateway's HTTP surface. Hermes presents a capability and a plan; it never names a tenant, never picks a recipient
//! the case does not already have, and never reaches Concierge directly.
//!
//! Status codes: 400 unreadable plan, 401 bad/expired/revoked capability, 404 unknown case, 409 Concierge refused
//! (stale case, takeover, opt-out...), 422 policy rejected the plan, 503 Concierge unavailable.
use crate::backend::{Backend, BackendError};
use crate::capability::{mint, verify, CapError, Capability, MAX_TTL_SECS};
use crate::ledger::{ActionLedger, LedgerError, MemoryLedger, NewAction};
use crate::ops::Op;
use crate::orchestrator::{build_prompts, extract_plan_json, normalise_plan, Planner};
use crate::plan::{parse_plan, Channel};
use crate::policy::{validate_plan, DeliveryMode, Validated};
use axum::{
    extract::{DefaultBodyLimit, Path, State},
    http::{header, HeaderMap, StatusCode},
    routing::{delete, get, post},
    Json, Router,
};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::HashSet;
use std::sync::{Arc, Mutex};
use subtle::ConstantTimeEq;

pub struct AppState {
    pub secret: Vec<u8>,
    pub mint_key: String,
    pub backend: Arc<dyn Backend>,
    pub planner: Arc<dyn Planner>,
    pub revoked: Mutex<HashSet<String>>,
    pub ledger: Mutex<MemoryLedger>,
    pub clock: Box<dyn Fn() -> i64 + Send + Sync>,
}

pub fn system_clock() -> Box<dyn Fn() -> i64 + Send + Sync> {
    Box::new(|| {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs() as i64)
            .unwrap_or(0)
    })
}

type Reply = (StatusCode, Json<Value>);

fn reply(status: StatusCode, body: Value) -> Reply {
    (status, Json(body))
}

fn bearer(headers: &HeaderMap) -> Option<&str> {
    headers
        .get(header::AUTHORIZATION)?
        .to_str()
        .ok()?
        .strip_prefix("Bearer ")
}

fn same(a: &str, b: &str) -> bool {
    a.len() == b.len() && bool::from(a.as_bytes().ct_eq(b.as_bytes()))
}

pub fn router(state: Arc<AppState>) -> Router {
    Router::new()
        .route("/healthz", get(|| async { "ok" }))
        .route("/v1/capabilities", post(mint_capability))
        .route("/v1/capabilities/:nonce", delete(revoke_capability))
        .route("/v1/plans", post(submit_plan))
        .route("/v1/runs", post(run_case))
        .layer(DefaultBodyLimit::max(128 * 1024))
        .with_state(state)
}

fn check_mint_key(state: &AppState, headers: &HeaderMap) -> Result<(), Reply> {
    match bearer(headers) {
        Some(k) if same(k, &state.mint_key) => Ok(()),
        _ => Err(reply(
            StatusCode::UNAUTHORIZED,
            json!({"error": "invalid_mint_key"}),
        )),
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct MintRequest {
    tenant_id: String,
    case_id: String,
    run_id: String,
    ops: Vec<String>,
    ttl_secs: Option<i64>,
}

async fn mint_capability(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    Json(req): Json<MintRequest>,
) -> Result<Reply, Reply> {
    check_mint_key(&state, &headers)?;
    let mut ops = Vec::new();
    for name in &req.ops {
        ops.push(Op::parse(name).ok_or_else(|| {
            reply(
                StatusCode::UNPROCESSABLE_ENTITY,
                json!({"error": "unknown_operation", "op": name}),
            )
        })?);
    }
    let now = (state.clock)();
    let ttl = req.ttl_secs.unwrap_or(300).clamp(1, MAX_TTL_SECS);
    let cap = Capability {
        tenant_id: req.tenant_id,
        case_id: req.case_id,
        run_id: req.run_id,
        ops,
        issued_at: now,
        expires_at: now + ttl,
        nonce: format!("{now:x}-{}", rand_suffix()),
    };
    let token = mint(&state.secret, &cap).map_err(|e| {
        reply(
            StatusCode::UNPROCESSABLE_ENTITY,
            json!({"error": format!("{e:?}")}),
        )
    })?;
    Ok(reply(
        StatusCode::OK,
        json!({"token": token, "expires_at": cap.expires_at, "nonce": cap.nonce}),
    ))
}

/// Unique enough for a nonce: nanosecond clock plus a process-wide counter. It is an identifier, not a secret.
fn rand_suffix() -> String {
    use std::sync::atomic::{AtomicU64, Ordering};
    static N: AtomicU64 = AtomicU64::new(0);
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.subsec_nanos())
        .unwrap_or(0);
    format!("{:x}{:x}", nanos, N.fetch_add(1, Ordering::Relaxed))
}

async fn revoke_capability(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    Path(nonce): Path<String>,
) -> Result<Reply, Reply> {
    check_mint_key(&state, &headers)?;
    state.revoked.lock().expect("revocation list").insert(nonce);
    Ok(reply(StatusCode::OK, json!({"revoked": true})))
}

fn cap_error(e: CapError) -> Reply {
    reply(
        StatusCode::UNAUTHORIZED,
        json!({"error": "invalid_capability", "reason": format!("{e:?}")}),
    )
}

/// The exact JSON Concierge's `Bundle` model accepts (`api/app/hermes_ops.py`); a shared fixture pins it from both sides.
pub fn bundle_json(cap: &Capability, task_id: &str, v: &Validated) -> Value {
    json!({
        "task_id": task_id,
        "tenant_id": cap.tenant_id,
        "actions": v.actions.iter().map(|a| json!({
            "op": a.op.name(), "idempotency_key": a.idempotency_key, "dedupe_key": a.dedupe_key,
            "fingerprint": a.fingerprint, "case_version": a.case_version, "params": a.params,
        })).collect::<Vec<_>>(),
        "delivery": v.delivery.as_ref().map(|d| json!({
            "channel": match d.channel { Channel::Email => "email", Channel::Sms => "sms" },
            "recipient": d.recipient, "subject": d.subject, "body": d.body,
            "mode": match d.mode { DeliveryMode::ShadowOnly => "shadow_only", DeliveryMode::NeedsApproval => "needs_approval", DeliveryMode::Auto => "auto" },
            "fingerprint": d.fingerprint, "dedupe_key": d.dedupe_key, "send_at": d.send_at.to_rfc3339(),
        })),
    })
}

fn backend_error(e: BackendError) -> Reply {
    match e {
        BackendError::NotFound => reply(StatusCode::NOT_FOUND, json!({"error": "case_not_found"})),
        BackendError::Refused { status, body } => reply(
            StatusCode::from_u16(status).unwrap_or(StatusCode::CONFLICT),
            json!({"error": "refused_by_concierge", "detail": body}),
        ),
        BackendError::Unavailable(m) => reply(
            StatusCode::SERVICE_UNAVAILABLE,
            json!({"error": "concierge_unavailable", "detail": m}),
        ),
    }
}

async fn submit_plan(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    body: String,
) -> Result<Reply, Reply> {
    let now = (state.clock)();
    let token = bearer(&headers).ok_or_else(|| cap_error(CapError::Malformed))?;
    let cap = {
        let revoked = state.revoked.lock().expect("revocation list");
        verify(&state.secret, token, now, &|nonce| revoked.contains(nonce)).map_err(cap_error)?
    };
    process_plan(&state, &cap, &body).await
}

/// Parse, validate and (unless the business is in shadow mode) forward a plan. Shared by `/v1/plans` and `/v1/runs`.
async fn process_plan(state: &AppState, cap: &Capability, body: &str) -> Result<Reply, Reply> {
    let now = (state.clock)();
    let plan = parse_plan(body).map_err(|e| {
        reply(
            StatusCode::BAD_REQUEST,
            json!({"error": "invalid_plan", "detail": format!("{e:?}")}),
        )
    })?;
    // Tenant and case come from the capability alone.
    let ctx = state
        .backend
        .policy_context(&cap.tenant_id, &cap.case_id)
        .await
        .map_err(backend_error)?;
    let validated = validate_plan(cap, &plan, &ctx, now).map_err(|r| {
        reply(
            StatusCode::UNPROCESSABLE_ENTITY,
            json!({"error": "policy_rejected", "rejected": {"code": r.code, "detail": r.detail}}),
        )
    })?;
    let bundle = bundle_json(cap, &plan.task_id, &validated);
    if validated.shadow {
        return Ok(reply(
            StatusCode::OK,
            json!({"mode": "shadow", "executed": false, "would_execute": bundle}),
        ));
    }
    {
        // Advisory pre-check. Concierge's Postgres ledger is authoritative; this only catches a key reused for different content early.
        let mut ledger = state.ledger.lock().expect("ledger");
        for a in &validated.actions {
            let fresh = NewAction {
                tenant_id: cap.tenant_id.clone(),
                case_id: cap.case_id.clone(),
                op: a.op.name().into(),
                idempotency_key: a.idempotency_key.clone(),
                fingerprint: a.fingerprint.clone(),
                case_version: a.case_version,
                approval_ref: plan.approval_ref.clone(),
            };
            if let Err(LedgerError::KeyReuseConflict(_)) = ledger.begin(fresh) {
                return Err(reply(
                    StatusCode::CONFLICT,
                    json!({"error": "key_reuse", "detail": a.idempotency_key}),
                ));
            }
        }
    }
    let result = state
        .backend
        .execute(&cap.tenant_id, &cap.case_id, &bundle)
        .await
        .map_err(backend_error)?;
    Ok(reply(
        StatusCode::OK,
        json!({"mode": "executed", "executed": true, "result": result}),
    ))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RunRequest {
    tenant_id: String,
    case_id: String,
    run_id: String,
    ops: Option<Vec<String>>,
}

/// Run Hermes on one case. The capability is minted and used here; Hermes only ever sees text.
async fn run_case(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    Json(req): Json<RunRequest>,
) -> Result<Reply, Reply> {
    check_mint_key(&state, &headers)?;
    if req.run_id.is_empty()
        || req.run_id.len() > 128
        || !req
            .run_id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"-_:.".contains(&b))
    {
        return Err(reply(
            StatusCode::UNPROCESSABLE_ENTITY,
            json!({"error": "bad_run_id"}),
        ));
    }
    let default = ["prepare_reply", "schedule_followup", "escalate_case"];
    let mut ops = Vec::new();
    for name in req
        .ops
        .as_ref()
        .map(|v| v.iter().map(String::as_str).collect::<Vec<_>>())
        .unwrap_or_else(|| default.to_vec())
    {
        ops.push(Op::parse(name).ok_or_else(|| {
            reply(
                StatusCode::UNPROCESSABLE_ENTITY,
                json!({"error": "unknown_operation", "op": name}),
            )
        })?);
    }
    let now = (state.clock)();
    let cap = Capability {
        tenant_id: req.tenant_id.clone(),
        case_id: req.case_id.clone(),
        run_id: req.run_id.clone(),
        ops: ops.clone(),
        issued_at: now,
        expires_at: now + 300,
        nonce: format!("{now:x}-{}", rand_suffix()),
    };
    let ctx = state
        .backend
        .policy_context(&cap.tenant_id, &cap.case_id)
        .await
        .map_err(backend_error)?;
    let brief = state
        .backend
        .brief(&cap.tenant_id, &cap.case_id)
        .await
        .map_err(backend_error)?;
    let (system, user) = build_prompts(&brief, &ctx, &ops, &req.run_id);
    let reply_text = state.planner.plan(&system, &user).await.map_err(|e| {
        reply(
            StatusCode::BAD_GATEWAY,
            json!({"error": "planner_unavailable", "detail": e}),
        )
    })?;
    let unusable = |e| {
        reply(
            StatusCode::UNPROCESSABLE_ENTITY,
            json!({"error": "unusable_plan_reply", "detail": format!("{e:?}")}),
        )
    };
    let plan_text = normalise_plan(
        &extract_plan_json(&reply_text).map_err(unusable)?,
        &req.run_id,
    )
    .map_err(unusable)?;
    let (status, Json(mut body)) = process_plan(&state, &cap, &plan_text)
        .await
        .unwrap_or_else(|e| e);
    body["run_id"] = json!(req.run_id);
    Ok((status, Json(body)))
}
