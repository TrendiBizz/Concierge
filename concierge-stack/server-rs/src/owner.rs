//! Batch 40, family 2: the owner-portal reads. Every route here authenticates with `owner_auth.current_user` (a Bearer
//! session token whose SHA-256 is looked up in `tenant_sessions`) and then reads only rows of that user's tenant. They sit
//! under the owner boundary middleware in `lib.rs`, so each response carries the hardening headers.
//!
//! Order of decisions, as FastAPI makes them: the router (a decoded `/` in a path segment is a 404), then the session
//! dependency (401), then path/query validation (422), then the handler.
use crate::public::SegAt;
use crate::{detail, row_json, server_error, unroutable, State};
use axum::extract::{Query, State as AxState};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::{Json, Router};
use concierge_core::owner_portal::{self, Device};
use concierge_core::{channel_auth, owner_auth, pydantic, pyval, requests, tenants};
use serde_json::{json, Map, Value};
use std::collections::HashMap;
use uuid::Uuid;

pub struct User {
    pub tenant_id: Uuid,
    pub email: String,
    pub role: String,
    pub slug: String,
}

pub fn routes() -> Router<State> {
    Router::new()
        .route("/owner/me", get(me))
        .route("/owner/crm", get(crm))
        .route("/owner/crm/leads/:lead_id/transcript", get(crm_transcript))
        .route("/owner/crm/leads/:lead_id/recordings", get(crm_recordings))
        .route("/owner/onboarding", get(onboarding))
        .route("/owner/onboarding/authorizations", get(authorizations))
        .route("/owner/onboarding/readiness", get(readiness))
        .route("/owner/knowledge", get(knowledge))
        .route("/owner/email-drafts", get(email_drafts))
        .route("/owner/phone-setup", get(phone_setup))
        .route("/owner/phone-numbers", get(phone_numbers))
        .route("/owner/phone-calls", get(phone_calls))
        .route(
            "/owner/phone-calls/:call_id/transcript",
            get(phone_transcript),
        )
}

/// `owner_auth.current_user`. Starlette decodes header values as latin-1, so the bytes are widened one to one.
async fn authenticate(state: &State, headers: &HeaderMap) -> Result<User, Response> {
    let raw: String = headers
        .get("authorization")
        .map(|v| v.as_bytes().iter().map(|&b| b as char).collect())
        .unwrap_or_default();
    let token = owner_portal::bearer_token(&raw).map_err(|d| detail(401, d))?;
    let Some(pool) = state.0.pool.as_ref() else {
        return Err(server_error());
    };
    let Ok(client) = pool.get().await else {
        return Err(server_error());
    };
    let digest = owner_auth::digest(token);
    let Ok(row) = client
        .query_opt(
            "SELECT u.id,u.tenant_id,u.email,u.role,t.slug,t.name \
             FROM tenant_sessions s JOIN tenant_users u ON u.id=s.user_id \
             JOIN tenants t ON t.id=u.tenant_id \
             WHERE s.token_hash=$1 AND s.expires_at>now() AND u.active",
            &[&digest],
        )
        .await
    else {
        return Err(server_error());
    };
    let Some(row) = row else {
        return Err(detail(401, "Session expired or invalid"));
    };
    Ok(User {
        tenant_id: row.get("tenant_id"),
        email: row.get("email"),
        role: row.get("role"),
        slug: row.get("slug"),
    })
}

macro_rules! session {
    ($state:expr, $headers:expr) => {
        match authenticate(&$state, &$headers).await {
            Ok(u) => u,
            Err(r) => return r,
        }
    };
}

macro_rules! db {
    ($state:expr) => {
        match $state.0.pool.as_ref() {
            None => return server_error(),
            Some(pool) => match pool.get().await {
                Ok(c) => c,
                Err(_) => return server_error(),
            },
        }
    };
}

fn rows_json(rows: &[tokio_postgres::Row]) -> Value {
    Value::Array(rows.iter().map(row_json).collect())
}

/// FastAPI's 422 for a `uuid.UUID` path parameter pydantic could not parse. The reason text is the `uuid` crate's own,
/// which is what pydantic-core quotes.
fn bad_uuid(name: &str, input: &str, reason: &str) -> Response {
    (
        StatusCode::UNPROCESSABLE_ENTITY,
        Json(json!({"detail": [{
            "type": "uuid_parsing", "loc": ["path", name],
            "msg": format!("Input should be a valid UUID, {reason}"),
            "input": input, "ctx": {"error": reason}}]})),
    )
        .into_response()
}

/// Starlette's `[^/]+` also needs at least one character, which axum does not insist on for a segment in the middle of a path.
fn no_route(segment: &str) -> Option<Response> {
    if segment.is_empty() {
        return Some(detail(404, "Not Found"));
    }
    unroutable(segment)
}

async fn me(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    let u = session!(state, headers);
    Json(json!({"email": u.email, "role": u.role, "tenant": u.slug})).into_response()
}

async fn phone_setup(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    let u = session!(state, headers);
    let client = db!(state);
    let Ok(row) = client
        .query_opt(
            "SELECT designated_number,connection,answer_mode,owner_number,status FROM managed_phone_setups WHERE tenant_id=$1",
            &[&u.tenant_id],
        )
        .await
    else {
        return server_error();
    };
    Json(row.map_or_else(|| json!({"status": "not_requested"}), |r| row_json(&r))).into_response()
}

async fn phone_numbers(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    let u = session!(state, headers);
    let client = db!(state);
    let Ok(rows) = client
        .query(
            "SELECT e164,enabled,created_at FROM phone_numbers WHERE tenant_id=$1",
            &[&u.tenant_id],
        )
        .await
    else {
        return server_error();
    };
    Json(rows_json(&rows)).into_response()
}

async fn phone_calls(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    let u = session!(state, headers);
    let client = db!(state);
    let Ok(rows) = client
        .query(
            "SELECT call_sid,from_number,to_number,status,started_at,ended_at, \
             recording_consent,recording_status \
             FROM phone_calls WHERE tenant_id=$1 ORDER BY started_at DESC LIMIT 100",
            &[&u.tenant_id],
        )
        .await
    else {
        return server_error();
    };
    Json(rows_json(&rows)).into_response()
}

async fn phone_transcript(
    AxState(state): AxState<State>,
    SegAt(call_id): SegAt<3>,
    headers: HeaderMap,
) -> Response {
    if let Some(r) = no_route(&call_id) {
        return r;
    }
    let u = session!(state, headers);
    let client = db!(state);
    let Ok(found) = client
        .query_opt(
            "SELECT 1 FROM phone_calls WHERE tenant_id=$1 AND call_sid=$2",
            &[&u.tenant_id, &call_id],
        )
        .await
    else {
        return server_error();
    };
    if found.is_none() {
        return detail(404, "Call not found");
    }
    let Ok(rows) = client
        .query(
            "SELECT m.role,m.content,m.created_at FROM phone_calls p \
             JOIN conversations c ON c.tenant_id=p.tenant_id AND c.session_id=p.call_sid AND c.channel='phone' \
             JOIN messages m ON m.conversation_id=c.id WHERE p.tenant_id=$1 AND p.call_sid=$2 \
             AND m.role IN ('user','assistant') ORDER BY m.id LIMIT 200",
            &[&u.tenant_id, &call_id],
        )
        .await
    else {
        return server_error();
    };
    Json(rows_json(&rows)).into_response()
}

async fn crm_transcript(
    AxState(state): AxState<State>,
    SegAt(raw): SegAt<4>,
    headers: HeaderMap,
) -> Response {
    if let Some(r) = no_route(&raw) {
        return r;
    }
    let u = session!(state, headers);
    let lead_id = match Uuid::parse_str(&raw) {
        Ok(id) => id,
        Err(e) => return bad_uuid("lead_id", &raw, &e.to_string()),
    };
    let client = db!(state);
    let Ok(exists) = client
        .query_opt(
            "SELECT 1 FROM leads WHERE tenant_id=$1 AND id=$2",
            &[&u.tenant_id, &lead_id],
        )
        .await
    else {
        return server_error();
    };
    if exists.is_none() {
        return detail(404, "Enquiry not found");
    }
    let Ok(rows) = client
        .query(
            "SELECT m.role,m.content,m.created_at FROM leads l \
             JOIN conversations c ON c.id=l.conversation_id AND c.tenant_id=l.tenant_id \
             JOIN messages m ON m.conversation_id=c.id \
             WHERE l.tenant_id=$1 AND l.id=$2 AND m.role IN ('user','assistant') \
             ORDER BY m.id LIMIT 1000",
            &[&u.tenant_id, &lead_id],
        )
        .await
    else {
        return server_error();
    };
    if !rows.is_empty() {
        return Json(rows_json(&rows)).into_response();
    }
    let Ok(sources) = client
        .query(
            "SELECT original_text,created_at FROM enquiry_sources WHERE tenant_id=$1 AND lead_id=$2 ORDER BY created_at",
            &[&u.tenant_id, &lead_id],
        )
        .await
    else {
        return server_error();
    };
    let out: Vec<Value> = sources
        .iter()
        .map(|r| {
            let row = row_json(r);
            json!({"role": "user", "content": row["original_text"], "created_at": row["created_at"]})
        })
        .collect();
    Json(Value::Array(out)).into_response()
}

async fn crm_recordings(
    AxState(state): AxState<State>,
    SegAt(raw): SegAt<4>,
    headers: HeaderMap,
) -> Response {
    if let Some(r) = no_route(&raw) {
        return r;
    }
    let u = session!(state, headers);
    let lead_id = match Uuid::parse_str(&raw) {
        Ok(id) => id,
        Err(e) => return bad_uuid("lead_id", &raw, &e.to_string()),
    };
    let client = db!(state);
    let Ok(rows) = client
        .query(
            "SELECT r.session_id,r.mime_type,octet_length(r.audio) AS bytes,r.created_at \
             FROM leads l JOIN voice_recordings r ON r.conversation_id=l.conversation_id AND r.tenant_id=l.tenant_id \
             WHERE l.tenant_id=$1 AND l.id=$2 AND r.created_at>now()-interval '30 days' ORDER BY r.created_at",
            &[&u.tenant_id, &lead_id],
        )
        .await
    else {
        return server_error();
    };
    Json(rows_json(&rows)).into_response()
}

async fn authorizations(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    let u = session!(state, headers);
    let client = db!(state);
    match authorization_map(&client, u.tenant_id).await {
        Ok(m) => Json(Value::Object(m)).into_response(),
        Err(()) => server_error(),
    }
}

/// `channel_authorization.authorizations`: every known channel, absent ones as not authorized.
async fn authorization_map(
    client: &deadpool_postgres::Client,
    tenant_id: Uuid,
) -> Result<Map<String, Value>, ()> {
    let rows = client
        .query(
            "SELECT channel,authorized,updated_at FROM tenant_channel_authorizations WHERE tenant_id=$1",
            &[&tenant_id],
        )
        .await
        .map_err(|_| ())?;
    let stored: HashMap<String, Value> = rows
        .iter()
        .map(|r| {
            let v = row_json(r);
            (v["channel"].as_str().unwrap_or("").to_string(), v)
        })
        .collect();
    let mut out = Map::new();
    for key in channel_auth::CHANNELS {
        let row = stored.get(key);
        out.insert(
            key.to_string(),
            json!({
                "authorized": row.is_some_and(|r| pyval::truthy(r.get("authorized"))),
                "updated_at": row.map_or(Value::Null, |r| r["updated_at"].clone()),
                "provider_verified": false,
                "active": false,
            }),
        );
    }
    Ok(out)
}

async fn knowledge(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    let u = session!(state, headers);
    let client = db!(state);
    const PREFIX: &str = "manual:owner:";
    let Ok(rows) = client
        .query(
            "SELECT url, min(title) AS title, count(*) AS chunks \
             FROM chunks WHERE tenant_id=$1 AND url LIKE $2 GROUP BY url ORDER BY min(title)",
            &[&u.tenant_id, &format!("{PREFIX}%")],
        )
        .await
    else {
        return server_error();
    };
    let out: Vec<Value> = rows
        .iter()
        .map(|r| {
            let row = row_json(r);
            let url = row["url"].as_str().unwrap_or("");
            json!({"document_id": url.strip_prefix(PREFIX).unwrap_or(url), "title": row["title"], "chunks": row["chunks"]})
        })
        .collect();
    Json(Value::Array(out)).into_response()
}

async fn email_drafts(
    AxState(state): AxState<State>,
    Query(q): Query<Vec<(String, String)>>,
    headers: HeaderMap,
) -> Response {
    let u = session!(state, headers);
    let status = match q.iter().rev().find(|(k, _)| k == "status") {
        None => "draft".to_string(),
        Some((_, v)) => match pydantic::literal(&json!(v), &["draft", "approved", "discarded", "all"]) {
            Ok(s) => s.to_string(),
            Err(_) => {
                return (
                    StatusCode::UNPROCESSABLE_ENTITY,
                    Json(json!({"detail": [{
                        "type": "literal_error", "loc": ["query", "status"],
                        "msg": "Input should be 'draft', 'approved', 'discarded' or 'all'",
                        "input": v, "ctx": {"expected": "'draft', 'approved', 'discarded' or 'all'"}}]})),
                )
                    .into_response()
            }
        },
    };
    if !state.0.extra.email_drafts_enabled {
        return detail(503, "Email draft workflow is disabled");
    }
    let client = db!(state);
    let Ok(rows) = client
        .query(
            "SELECT * FROM email_drafts WHERE tenant_id=$1 AND ($2='all' OR status=$2) ORDER BY id DESC LIMIT 100",
            &[&u.tenant_id, &status],
        )
        .await
    else {
        return server_error();
    };
    Json(rows_json(&rows)).into_response()
}

async fn crm(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    let u = session!(state, headers);
    let client = db!(state);
    // `_require_tenant(user["slug"])`, then `ensure_calendar_token`: the same backfill the admin route does.
    let Ok(row) = client
        .query_opt("SELECT * FROM tenants WHERE slug = $1", &[&u.slug])
        .await
    else {
        return server_error();
    };
    let Some(row) = row else {
        return detail(404, "Unknown tenant");
    };
    let Ok(mut tenant) = tenants::load(&row_json(&row)) else {
        return server_error();
    };
    if !pyval::truthy(tenant.get("calendar_token")) {
        let token = crate::new_token();
        let Ok(row) = client
            .query_one(
                "UPDATE tenants SET calendar_token = COALESCE(calendar_token, $2) WHERE id = $1 RETURNING *",
                &[&u.tenant_id, &token],
            )
            .await
        else {
            return server_error();
        };
        let Ok(t) = tenants::load(&row_json(&row)) else {
            return server_error();
        };
        tenant = t;
    }
    // `admin_leads(slug)` and `admin_appointments(slug)` called with their defaults (limit 100, no filters), and
    // `tasks.list_tasks(tenant_id, "all")` (limit 200, newest activity first).
    let (limit, min_score, no_status): (i64, i32, Option<&str>) = (100, 0, None);
    let Ok(leads) = client
        .query(
            "SELECT * FROM leads WHERE tenant_id = $1 AND score >= $3 ORDER BY created_at DESC LIMIT $2",
            &[&u.tenant_id, &limit, &min_score],
        )
        .await
    else {
        return server_error();
    };
    let Ok(appointments) = client
        .query(
            "SELECT * FROM appointments WHERE tenant_id = $1 AND ($2::text IS NULL OR status = $2) \
             ORDER BY starts_at DESC LIMIT $3",
            &[&u.tenant_id, &no_status, &limit],
        )
        .await
    else {
        return server_error();
    };
    let Ok(tasks) = client
        .query(
            "SELECT t.*, l.name AS lead_name, l.score_label AS lead_label \
             FROM tasks t LEFT JOIN leads l ON l.id = t.lead_id \
             WHERE t.tenant_id = $1  ORDER BY COALESCE(t.completed_at, t.created_at) DESC LIMIT 200",
            &[&u.tenant_id],
        )
        .await
    else {
        return server_error();
    };
    let Ok(origin) = requests::origin_of(&state.0.extra.owner_portal_url) else {
        return server_error();
    };
    let token = tenant["calendar_token"].as_str().unwrap_or("");
    Json(json!({
        "leads": rows_json(&leads), "appointments": rows_json(&appointments), "tasks": rows_json(&tasks),
        "calendar_url": format!("{origin}/api/v1/calendar/{token}.ics"),
    }))
    .into_response()
}

/// `owner_onboarding.overview`'s inputs (tenant row, numbers, the paired phone) read from the database, then the ported rule.
/// `Err(None)` is the `ValueError` Python raises for a tenant that has vanished; `Err(Some(_))` a failed request.
async fn overview(
    state: &State,
    client: &deadpool_postgres::Client,
    tenant_id: Uuid,
) -> Result<Value, Option<Response>> {
    let internal = |_| Some(server_error());
    let row = client
        .query_opt("SELECT * FROM tenants WHERE id = $1", &[&tenant_id])
        .await
        .map_err(internal)?;
    let Some(row) = row else { return Err(None) };
    let tenant = tenants::load(&row_json(&row)).map_err(|_| Some(server_error()))?;
    let numbers: Vec<(String, bool)> = client
        .query(
            "SELECT e164,enabled FROM phone_numbers WHERE tenant_id=$1 ORDER BY e164",
            &[&tenant_id],
        )
        .await
        .map_err(internal)?
        .iter()
        .map(|r| (r.get(0), r.get(1)))
        .collect();
    let device = client
        .query_opt(
            "SELECT last_seen,verified_at,inbound_verified_at FROM sms_devices WHERE tenant_id=$1 AND enabled",
            &[&tenant_id],
        )
        .await
        .map_err(internal)?
        .map(|d| Device {
            last_seen: d
                .get::<_, Option<chrono::DateTime<chrono::Utc>>>("last_seen")
                .map(|t| t.timestamp_micros()),
            verified: d
                .get::<_, Option<chrono::DateTime<chrono::Utc>>>("verified_at")
                .is_some(),
            inbound_verified: d
                .get::<_, Option<chrono::DateTime<chrono::Utc>>>("inbound_verified_at")
                .is_some(),
        });
    let portal = state.0.extra.portal();
    owner_portal::overview(
        &tenant,
        &numbers,
        device.as_ref(),
        chrono::Utc::now().timestamp_micros(),
        &portal,
    )
    .map_err(|_| Some(server_error()))
}

async fn onboarding(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    let u = session!(state, headers);
    let client = db!(state);
    match overview(&state, &client, u.tenant_id).await {
        Ok(v) => Json(v).into_response(),
        Err(None) => detail(404, "Business not found"),
        Err(Some(r)) => r,
    }
}

async fn readiness(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    let u = session!(state, headers);
    let client = db!(state);
    // an unhandled ValueError from `overview` is Python's plain 500
    let status = match overview(&state, &client, u.tenant_id).await {
        Ok(v) => v,
        Err(Some(r)) => return r,
        Err(None) => return server_error(),
    };
    let Ok(declarations) = authorization_map(&client, u.tenant_id).await else {
        return server_error();
    };
    let portal = state.0.extra.portal();
    Json(owner_portal::readiness(&status, &declarations, &portal)).into_response()
}
