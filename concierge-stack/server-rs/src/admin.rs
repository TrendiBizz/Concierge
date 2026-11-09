//! The read-only `/admin/...` listing routes. Each one is `Depends(require_admin)` in Python, so the order every handler
//! follows is the order FastAPI follows:
//!
//! 1. the router: an encoded slash makes the segment unroutable (`unroutable`), before anything else;
//! 2. the admin gate (a dependency, so it raises before any parameter is validated: 401/403 beats 422);
//! 3. path and query validation, every error collected in declaration order (one 422 listing them all);
//! 4. the handler body (the email-draft feature gate, then the tenant lookup, then the queries).
//!
//! The response shapes that are more than a SQL row are `concierge_core::admin_views`, held to the live Python by
//! `tests/parity30.rs`; the SQL is held to the live Python by `QA/verification/rust_server_parity.py`.
use super::{
    admin_gate, detail, row_json, server_error, tenant_where, unprocessable_entry, unroutable, State,
};
use axum::extract::{RawQuery, State as AxState};
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::Json;
use concierge_core::{admin_views as views, pydantic, report};
use deadpool_postgres::Object;
use serde_json::{json, Value};
use std::collections::HashMap;
use tokio_postgres::types::ToSql;
use tokio_postgres::Row;

type R = Result<Response, Response>;

/// The one path parameter of these routes (segment 3 of `/admin/<x>/<param>/...`), percent-decoded the way Starlette
/// does: invalid UTF-8 becomes U+FFFD instead of the rejection axum's `Path` would answer with (a 400 that Python
/// never sends).
struct Seg(String);

#[axum::async_trait]
impl<S: Send + Sync> axum::extract::FromRequestParts<S> for Seg {
    type Rejection = std::convert::Infallible;

    async fn from_request_parts(
        parts: &mut axum::http::request::Parts,
        _state: &S,
    ) -> Result<Self, Self::Rejection> {
        Ok(Seg(unquote_path(
            parts.uri.path().split('/').nth(3).unwrap_or(""),
        )))
    }
}

fn finish(r: R) -> Response {
    match r {
        Ok(x) | Err(x) => x,
    }
}

fn db<T>(r: Result<T, tokio_postgres::Error>) -> Result<T, Response> {
    r.map_err(|_| server_error())
}

async fn connection(state: &State) -> Result<Object, Response> {
    let pool = state.0.pool.as_ref().ok_or_else(server_error)?;
    pool.get().await.map_err(|_| server_error())
}

fn unhex(b: u8) -> Option<u8> {
    (b as char).to_digit(16).map(|d| d as u8)
}

/// `urllib.parse.unquote_plus` with `errors="replace"`: `+` is a space, `%XX` is a byte, bytes are read as UTF-8.
fn unquote_plus(s: &str) -> String {
    let b = s.as_bytes();
    let mut out = Vec::with_capacity(b.len());
    let mut i = 0;
    while i < b.len() {
        match b[i] {
            b'+' => out.push(b' '),
            b'%' if i + 2 < b.len() && unhex(b[i + 1]).is_some() && unhex(b[i + 2]).is_some() => {
                out.push(unhex(b[i + 1]).unwrap() * 16 + unhex(b[i + 2]).unwrap());
                i += 2;
            }
            c => out.push(c),
        }
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// Starlette's `QueryParams`: `parse_qsl(keep_blank_values=True)` split on `&` only, and the LAST value of a repeated key.
fn query_map(raw: Option<&str>) -> HashMap<String, String> {
    let mut map = HashMap::new();
    for part in raw.unwrap_or("").split('&').filter(|p| !p.is_empty()) {
        let (k, v) = part.split_once('=').unwrap_or((part, ""));
        map.insert(unquote_plus(k), unquote_plus(v));
    }
    map
}

/// The validation errors FastAPI collects before it calls the handler.
struct Params {
    query: HashMap<String, String>,
    errors: Vec<Value>,
}

impl Params {
    fn new(raw: Option<String>) -> Params {
        Params {
            query: query_map(raw.as_deref()),
            errors: vec![],
        }
    }

    /// `name: int = default`.
    fn int(&mut self, name: &str, default: i128) -> i128 {
        match self.query.get(name) {
            None => default,
            Some(raw) => match pydantic::parse_int(&json!(raw)) {
                Ok(n) => n,
                Err(ty) => {
                    self.errors.push(unprocessable_entry("query", name, ty, raw));
                    default
                }
            },
        }
    }

    /// `name: Literal[...] = default`.
    fn literal(&mut self, name: &str, allowed: &[&str], default: &str) -> String {
        match self.query.get(name) {
            None => default.to_string(),
            Some(raw) => match pydantic::literal(&json!(raw), allowed) {
                Ok(v) => v.to_string(),
                Err(_) => {
                    let quoted: Vec<String> = allowed.iter().map(|a| format!("'{a}'")).collect();
                    let expected = match quoted.split_last() {
                        Some((last, [])) => last.clone(),
                        Some((last, head)) => format!("{} or {last}", head.join(", ")),
                        None => String::new(),
                    };
                    self.errors.push(json!({
                        "type": "literal_error", "loc": ["query", name],
                        "msg": format!("Input should be {expected}"), "input": raw, "ctx": {"expected": expected},
                    }));
                    default.to_string()
                }
            },
        }
    }

    /// `name: str | None = None`: an empty value is the empty string, not `None`.
    fn optional_text(&self, name: &str) -> Option<String> {
        self.query.get(name).cloned()
    }

    fn check(self) -> Result<(), Response> {
        if self.errors.is_empty() {
            Ok(())
        } else {
            Err((
                StatusCode::UNPROCESSABLE_ENTITY,
                Json(json!({"detail": self.errors})),
            )
                .into_response())
        }
    }
}

fn clamp(n: i128, low: i128, high: i128) -> i64 {
    n.clamp(low, high) as i64
}

fn tenant_id_of(tenant: &Value) -> Result<uuid::Uuid, Response> {
    uuid::Uuid::parse_str(tenant["id"].as_str().unwrap_or("")).map_err(|_| server_error())
}

/// `_require_tenant`.
async fn require_tenant(state: &State, slug: &str) -> Result<(Value, uuid::Uuid), Response> {
    let tenant = match tenant_where(state, "slug", slug).await {
        Ok(Some(t)) => t,
        Ok(None) => return Err(detail(404, "Unknown tenant")),
        Err(()) => return Err(server_error()),
    };
    let id = tenant_id_of(&tenant)?;
    Ok((tenant, id))
}

fn json_rows(rows: &[Row]) -> Response {
    Json(Value::Array(rows.iter().map(row_json).collect())).into_response()
}

fn tenant_int(tenant: &Value, key: &str) -> i64 {
    tenant.get(key).and_then(Value::as_i64).unwrap_or(0)
}

// ------------------------------------------------------------------------------------------------ /admin/capabilities

async fn capabilities(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    if let Err(r) = admin_gate(&state, &headers) {
        return *r;
    }
    Json(json!({"email_drafts": email_drafts_enabled()})).into_response()
}

/// `settings.email_drafts_enabled`: `EMAIL_DRAFTS_ENABLED`, a pydantic boolean, off by default.
fn email_drafts_enabled() -> bool {
    std::env::var("EMAIL_DRAFTS_ENABLED")
        .ok()
        .and_then(|v| pydantic::parse_bool(&json!(v)).ok())
        .unwrap_or(false)
}

// ------------------------------------------------------------------------------------------------ simple listings

/// Shared start of every `/admin/tenants/{slug}/...` route: the router, then the gate.
fn start(state: &State, headers: &HeaderMap, slug: &str) -> Result<(), Response> {
    // Starlette's `[^/]+` also needs at least one character, and axum matches an empty segment in the middle of a path.
    if let Some(r) = unroutable(slug).or_else(|| slug.is_empty().then(|| detail(404, "Not Found"))) {
        return Err(r);
    }
    admin_gate(state, headers).map_err(|r| *r)
}

async fn leads(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    RawQuery(raw): RawQuery,
    headers: HeaderMap,
) -> Response {
    finish(leads_inner(state, slug, raw, headers).await)
}

async fn leads_inner(state: State, slug: String, raw: Option<String>, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let mut p = Params::new(raw);
    let limit = p.int("limit", 100);
    let min_score = p.int("min_score", 0);
    p.check()?;
    let (_, tid) = require_tenant(&state, &slug).await?;
    // `score >= $3` makes PostgreSQL infer int4, and asyncpg refuses a Python int outside it (a 500).
    let min_score = i32::try_from(min_score.max(0)).map_err(|_| server_error())?;
    let limit = clamp(limit, 1, 500);
    let c = connection(&state).await?;
    let rows = db(c
        .query(
            "SELECT * FROM leads WHERE tenant_id = $1 AND score >= $3 ORDER BY created_at DESC LIMIT $2",
            &[&tid, &limit, &min_score],
        )
        .await)?;
    Ok(json_rows(&rows))
}

async fn appointments(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    RawQuery(raw): RawQuery,
    headers: HeaderMap,
) -> Response {
    finish(appointments_inner(state, slug, raw, headers).await)
}

async fn appointments_inner(state: State, slug: String, raw: Option<String>, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let mut p = Params::new(raw);
    let status = p.optional_text("status");
    let limit = p.int("limit", 100);
    p.check()?;
    let (_, tid) = require_tenant(&state, &slug).await?;
    let limit = clamp(limit, 1, 500);
    let c = connection(&state).await?;
    let rows = db(c
        .query(
            "SELECT * FROM appointments WHERE tenant_id = $1 AND ($2::text IS NULL OR status = $2) \
             ORDER BY starts_at DESC LIMIT $3",
            &[&tid, &status, &limit],
        )
        .await)?;
    Ok(json_rows(&rows))
}

async fn outbox(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    RawQuery(raw): RawQuery,
    headers: HeaderMap,
) -> Response {
    finish(outbox_inner(state, slug, raw, headers).await)
}

async fn outbox_inner(state: State, slug: String, raw: Option<String>, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let mut p = Params::new(raw);
    let limit = p.int("limit", 100);
    p.check()?;
    let (_, tid) = require_tenant(&state, &slug).await?;
    let limit = clamp(limit, 1, 500);
    let c = connection(&state).await?;
    let rows = db(c
        .query(
            "SELECT id, kind, channel, to_addr, status, attempts, last_error, send_at, sent_at \
             FROM outbox WHERE tenant_id = $1 ORDER BY id DESC LIMIT $2",
            &[&tid, &limit],
        )
        .await)?;
    Ok(json_rows(&rows))
}

async fn conversations(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    RawQuery(raw): RawQuery,
    headers: HeaderMap,
) -> Response {
    finish(conversations_inner(state, slug, raw, headers).await)
}

async fn conversations_inner(state: State, slug: String, raw: Option<String>, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let mut p = Params::new(raw);
    let limit = p.int("limit", 50);
    p.check()?;
    let (_, tid) = require_tenant(&state, &slug).await?;
    let limit = clamp(limit, 1, 200);
    let c = connection(&state).await?;
    let convs = db(c
        .query(
            "SELECT * FROM conversations WHERE tenant_id = $1 AND channel <> 'eval' ORDER BY started_at DESC LIMIT $2",
            &[&tid, &limit],
        )
        .await)?;
    let mut out = Vec::new();
    for conv in &convs {
        let id: uuid::Uuid = db(conv.try_get("id"))?;
        let msgs = db(c
            .query(
                "SELECT role, content, flag, created_at FROM messages WHERE conversation_id = $1 ORDER BY id",
                &[&id],
            )
            .await)?;
        let mut item = row_json(conv);
        item["messages"] = Value::Array(msgs.iter().map(row_json).collect());
        out.push(item);
    }
    Ok(Json(Value::Array(out)).into_response())
}

async fn tasks(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    RawQuery(raw): RawQuery,
    headers: HeaderMap,
) -> Response {
    finish(tasks_inner(state, slug, raw, headers).await)
}

async fn tasks_inner(state: State, slug: String, raw: Option<String>, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let mut p = Params::new(raw);
    let status = p.literal("status", &["open", "done", "all"], "open");
    p.check()?;
    let (_, tid) = require_tenant(&state, &slug).await?;
    let order = if status == "open" {
        "t.due_at NULLS LAST, t.created_at"
    } else {
        "COALESCE(t.completed_at, t.created_at) DESC"
    };
    let filter = if status == "all" { "" } else { "AND t.status = $2" };
    let sql = format!(
        "SELECT t.*, l.name AS lead_name, l.score_label AS lead_label \
         FROM tasks t LEFT JOIN leads l ON l.id = t.lead_id \
         WHERE t.tenant_id = $1 {filter} ORDER BY {order} LIMIT 200"
    );
    let c = connection(&state).await?;
    let rows = if status == "all" {
        db(c.query(&sql, &[&tid]).await)?
    } else {
        let st: &str = &status;
        db(c.query(&sql, &[&tid, &st]).await)?
    };
    Ok(json_rows(&rows))
}

async fn email_drafts(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    RawQuery(raw): RawQuery,
    headers: HeaderMap,
) -> Response {
    finish(email_drafts_inner(state, slug, raw, headers).await)
}

async fn email_drafts_inner(state: State, slug: String, raw: Option<String>, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let mut p = Params::new(raw);
    let status = p.literal("status", &["draft", "approved", "discarded", "all"], "draft");
    p.check()?;
    // `_email_feature_gate()` runs inside the handler, after validation and before the tenant lookup.
    if !email_drafts_enabled() {
        return Err(detail(503, "Email draft workflow is disabled"));
    }
    let (_, tid) = require_tenant(&state, &slug).await?;
    let c = connection(&state).await?;
    let st: &str = &status;
    let rows = db(c
        .query(
            "SELECT * FROM email_drafts WHERE tenant_id=$1 AND ($2='all' OR status=$2) ORDER BY id DESC LIMIT 100",
            &[&tid, &st],
        )
        .await)?;
    Ok(json_rows(&rows))
}

async fn phone_setup(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    headers: HeaderMap,
) -> Response {
    finish(phone_setup_inner(state, slug, headers).await)
}

async fn phone_setup_inner(state: State, slug: String, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let (_, tid) = require_tenant(&state, &slug).await?;
    let c = connection(&state).await?;
    let row = db(c
        .query_opt(
            "SELECT designated_number,connection,answer_mode,owner_number,status FROM managed_phone_setups WHERE tenant_id=$1",
            &[&tid],
        )
        .await)?;
    Ok(Json(row.map_or_else(|| json!({"status": "not_requested"}), |r| row_json(&r))).into_response())
}

async fn phone_numbers(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    headers: HeaderMap,
) -> Response {
    finish(phone_numbers_inner(state, slug, headers).await)
}

async fn phone_numbers_inner(state: State, slug: String, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let (_, tid) = require_tenant(&state, &slug).await?;
    let c = connection(&state).await?;
    // No ORDER BY in the Python query either: both servers read the table in the order PostgreSQL returns it.
    let rows = db(c
        .query("SELECT e164, enabled, created_at FROM phone_numbers WHERE tenant_id=$1", &[&tid])
        .await)?;
    Ok(json_rows(&rows))
}

async fn phone_calls(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    headers: HeaderMap,
) -> Response {
    finish(phone_calls_inner(state, slug, headers).await)
}

async fn phone_calls_inner(state: State, slug: String, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let (_, tid) = require_tenant(&state, &slug).await?;
    let c = connection(&state).await?;
    let rows = db(c
        .query(
            "SELECT call_sid, from_number, to_number, status, started_at, ended_at \
             FROM phone_calls WHERE tenant_id=$1 ORDER BY started_at DESC LIMIT 100",
            &[&tid],
        )
        .await)?;
    Ok(json_rows(&rows))
}

// ------------------------------------------------------------------------------------------------ campaigns

async fn delivery(c: &Object, campaign_id: i64) -> Result<Vec<(String, i64)>, Response> {
    let rows = db(c
        .query(
            "SELECT status, count(*) AS n FROM outbox WHERE campaign_id = $1 GROUP BY status",
            &[&campaign_id],
        )
        .await)?;
    rows.iter()
        .map(|r| Ok((db(r.try_get::<_, String>(0))?, db(r.try_get::<_, i64>(1))?)))
        .collect()
}

async fn campaigns(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    headers: HeaderMap,
) -> Response {
    finish(campaigns_inner(state, slug, headers).await)
}

async fn campaigns_inner(state: State, slug: String, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let (_, tid) = require_tenant(&state, &slug).await?;
    let c = connection(&state).await?;
    let rows = db(c
        .query(
            "SELECT * FROM campaigns WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT 100",
            &[&tid],
        )
        .await)?;
    let mut out = Vec::new();
    for r in &rows {
        let id: i64 = db(r.try_get("id"))?;
        let d = delivery(&c, id).await?;
        out.push(views::campaign_with_delivery(&row_json(r), &d).map_err(|_| server_error())?);
    }
    Ok(Json(Value::Array(out)).into_response())
}

/// `campaign_id: int` from the path, then the campaign row. FastAPI validates the path before the handler runs; an id
/// beyond int8 is refused by asyncpg (a 500) once the handler queries with it.
async fn campaign_row(state: &State, raw: &str) -> Result<(Value, i64), Response> {
    let id = match pydantic::parse_int(&json!(raw)) {
        Ok(n) => n,
        Err(ty) => {
            return Err((
                StatusCode::UNPROCESSABLE_ENTITY,
                Json(json!({"detail": [unprocessable_entry("path", "campaign_id", ty, raw)]})),
            )
                .into_response())
        }
    };
    let id = i64::try_from(id).map_err(|_| server_error())?;
    let c = connection(state).await?;
    let row = db(c.query_opt("SELECT * FROM campaigns WHERE id = $1", &[&id]).await)?;
    match row {
        Some(r) => Ok((row_json(&r), id)),
        None => Err(detail(404, "Unknown campaign")),
    }
}

async fn campaign(
    AxState(state): AxState<State>,
    Seg(raw): Seg,
    headers: HeaderMap,
) -> Response {
    finish(campaign_inner(state, raw, headers).await)
}

async fn campaign_inner(state: State, raw: String, headers: HeaderMap) -> R {
    start(&state, &headers, &raw)?;
    let (row, id) = campaign_row(&state, &raw).await?;
    let c = connection(&state).await?;
    let d = delivery(&c, id).await?;
    let body = views::campaign_with_delivery(&row, &d).map_err(|_| server_error())?;
    Ok(Json(body).into_response())
}

// ------------------------------------------------------------------------------------------------ scoring, sla

async fn scoring_weights(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    headers: HeaderMap,
) -> Response {
    finish(scoring_inner(state, slug, headers).await)
}

async fn scoring_inner(state: State, slug: String, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let (tenant, _) = require_tenant(&state, &slug).await?;
    Ok(Json(json!({"weights": views::describe_scoring(tenant.get("scoring"))})).into_response())
}

/// `sla.overdue(tenant)`: the leads waiting longer than the client's target. Nothing at all when the target is off.
async fn overdue(c: &Object, tenant: &Value, tid: uuid::Uuid) -> Result<Vec<Row>, Response> {
    let minutes = tenant_int(tenant, "sla_minutes");
    if minutes <= 0 {
        return Ok(vec![]);
    }
    let min_score = tenant
        .get("sla_min_score")
        .and_then(Value::as_i64)
        .unwrap_or(70);
    let (min_score, minutes, days) = (
        i32::try_from(min_score).map_err(|_| server_error())?,
        i32::try_from(minutes).map_err(|_| server_error())?,
        7_i32,
    );
    let params: [&(dyn ToSql + Sync); 4] = [&tid, &min_score, &minutes, &days];
    db(c.query(
        "SELECT id, name, phone, email, message, channel, score, score_label, score_reasons, \
                created_at, sla_alerted_at, \
                floor(EXTRACT(EPOCH FROM (now() - created_at)) / 60)::int AS minutes_waiting \
         FROM leads \
         WHERE tenant_id = $1 AND status = 'new' AND score >= $2 \
           AND created_at < now() - make_interval(mins => $3) \
           AND created_at > now() - make_interval(days => $4) \
           AND NOT EXISTS (SELECT 1 FROM appointments a \
                           WHERE a.lead_id = leads.id AND a.status IN ('booked', 'completed')) \
         ORDER BY score DESC, created_at \
         LIMIT 100",
        &params,
    )
    .await)
}

async fn sla(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    headers: HeaderMap,
) -> Response {
    finish(sla_inner(state, slug, headers).await)
}

async fn sla_inner(state: State, slug: String, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let (tenant, tid) = require_tenant(&state, &slug).await?;
    let c = connection(&state).await?;
    let rows: Vec<Value> = overdue(&c, &tenant, tid).await?.iter().map(row_json).collect();
    Ok(Json(views::sla_response(&tenant, &rows)).into_response())
}

// ------------------------------------------------------------------------------------------------ sales

async fn board_rows(c: &Object, tid: uuid::Uuid) -> Result<Vec<Value>, Response> {
    let rows = db(c
        .query(
            "SELECT id, name, phone, email, message, channel, status, score, score_label, value_cents, \
                    next_action_at, lost_reason, won_at, lost_at, created_at \
             FROM leads \
             WHERE tenant_id = $1 AND (status NOT IN ('won', 'lost') OR updated_at > now() - interval '30 days') \
             ORDER BY score DESC, created_at DESC LIMIT 1000",
            &[&tid],
        )
        .await)?;
    Ok(rows.iter().map(row_json).collect())
}

async fn pipeline(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    headers: HeaderMap,
) -> Response {
    finish(pipeline_inner(state, slug, headers).await)
}

async fn pipeline_inner(state: State, slug: String, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let (tenant, tid) = require_tenant(&state, &slug).await?;
    let c = connection(&state).await?;
    let rows = board_rows(&c, tid).await?;
    let body = views::pipeline_view(&rows, tenant_int(&tenant, "lead_value_cents"), 50);
    Ok(Json(body).into_response())
}

async fn sales_summary(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    RawQuery(raw): RawQuery,
    headers: HeaderMap,
) -> Response {
    finish(sales_summary_inner(state, slug, raw, headers).await)
}

async fn sales_summary_inner(state: State, slug: String, raw: Option<String>, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let mut p = Params::new(raw);
    let days = p.int("days", 7);
    p.check()?;
    let (tenant, tid) = require_tenant(&state, &slug).await?;
    let days = report::clamp_days(days);
    let average = tenant_int(&tenant, "lead_value_cents");
    let window = format!("now() - make_interval(days => {days})");
    let c = connection(&state).await?;
    let new_leads: i64 = db(c
        .query_one(
            &format!("SELECT count(*) FROM leads WHERE tenant_id = $1 AND created_at > {window}"),
            &[&tid],
        )
        .await)?
    .get(0);
    let moved_rows = db(c
        .query(
            &format!(
                "SELECT to_status, count(*) AS n FROM lead_events WHERE tenant_id = $1 AND created_at > {window} GROUP BY to_status"
            ),
            &[&tid],
        )
        .await)?;
    let moved: Vec<(String, i64)> = moved_rows
        .iter()
        .map(|r| (r.get::<_, String>(0), r.get::<_, i64>(1)))
        .collect();
    let won_rows = db(c
        .query(
            &format!("SELECT value_cents FROM leads WHERE tenant_id = $1 AND status = 'won' AND won_at > {window}"),
            &[&tid],
        )
        .await)?;
    let won_values: Vec<i64> = won_rows
        .iter()
        .map(|r| i64::from(r.get::<_, Option<i32>>(0).unwrap_or(0)))
        .collect();
    let board = views::pipeline_view(&board_rows(&c, tid).await?, average, 0);
    let leads_waiting = if tenant_int(&tenant, "sla_minutes") != 0 {
        Some(overdue(&c, &tenant, tid).await?.len() as i64)
    } else {
        None
    };
    let overdue_todos: i64 = db(c
        .query_one(
            "SELECT count(*) FROM tasks WHERE tenant_id = $1 AND status = 'open' AND due_at < now()",
            &[&tid],
        )
        .await)?
    .get(0);
    let body = views::summary_view(&views::SummaryInput {
        days,
        new_leads,
        moved: &moved,
        won_values: &won_values,
        average_cents: average,
        open_value_cents: board["open_value_cents"].as_i64().unwrap_or(0),
        weighted_value_cents: board["weighted_value_cents"].as_i64().unwrap_or(0),
        overdue_todos,
        leads_waiting,
    });
    Ok(Json(body).into_response())
}

// ------------------------------------------------------------------------------------------------ stats

async fn stats(
    AxState(state): AxState<State>,
    Seg(slug): Seg,
    RawQuery(raw): RawQuery,
    headers: HeaderMap,
) -> Response {
    finish(stats_inner(state, slug, raw, headers).await)
}

async fn counts(c: &Object, sql: &str, params: &[&(dyn ToSql + Sync)]) -> Result<Vec<(String, i64)>, Response> {
    let rows = db(c.query(sql, params).await)?;
    Ok(rows
        .iter()
        .map(|r| (r.get::<_, String>(0), r.get::<_, i64>(1)))
        .collect())
}

async fn stats_inner(state: State, slug: String, raw: Option<String>, headers: HeaderMap) -> R {
    start(&state, &headers, &slug)?;
    let mut p = Params::new(raw);
    let days = p.int("days", 30);
    p.check()?;
    let (tenant, tid) = require_tenant(&state, &slug).await?;
    let days = report::clamp_days(days);
    // `make_interval(days => $2)` makes PostgreSQL infer int4 (see the report route).
    let d = days as i32;
    let c = connection(&state).await?;
    let conversations = counts(
        &c,
        "SELECT channel, count(*) AS conversations FROM conversations \
         WHERE tenant_id = $1 AND channel <> 'eval' AND started_at > now() - make_interval(days => $2) \
         GROUP BY channel",
        &[&tid, &d],
    )
    .await?;
    let statuses = counts(
        &c,
        "SELECT status, count(*) AS n FROM leads WHERE tenant_id = $1 \
         AND created_at > now() - make_interval(days => $2) GROUP BY status",
        &[&tid, &d],
    )
    .await?;
    let appointments: i64 = db(c
        .query_one(
            "SELECT count(*) FROM appointments WHERE tenant_id = $1 AND created_at > now() - make_interval(days => $2)",
            &[&tid, &d],
        )
        .await)?
    .get(0);
    let guard_hits: i64 = db(c
        .query_one(
            "SELECT count(*) FROM messages m JOIN conversations c ON c.id = m.conversation_id \
             WHERE c.tenant_id = $1 AND m.flag = 'quote_guard' AND m.created_at > now() - make_interval(days => $2)",
            &[&tid, &d],
        )
        .await)?
    .get(0);
    let sent = counts(
        &c,
        "SELECT channel, count(*) AS n FROM outbox WHERE tenant_id = $1 AND status = 'sent' \
         AND created_at > now() - make_interval(days => $2) GROUP BY channel",
        &[&tid, &d],
    )
    .await?;
    let daily_rows = db(c
        .query(
            "SELECT d::date AS day, \
               (SELECT count(*) FROM conversations c WHERE c.tenant_id = $1 AND c.channel <> 'eval' AND c.started_at::date = d::date) AS conversations, \
               (SELECT count(*) FROM leads l WHERE l.tenant_id = $1 AND l.created_at::date = d::date) AS leads \
             FROM generate_series(now() - make_interval(days => $2 - 1), now(), interval '1 day') d \
             ORDER BY day",
            &[&tid, &d],
        )
        .await)?;
    let daily: Vec<(String, i64, i64)> = daily_rows
        .iter()
        .map(|r| {
            (
                r.get::<_, chrono::NaiveDate>(0).to_string(),
                r.get::<_, i64>(1),
                r.get::<_, i64>(2),
            )
        })
        .collect();
    let won_value: i64 = db(c
        .query_one(
            "SELECT COALESCE(sum(value_cents), 0) FROM leads WHERE tenant_id = $1 AND status = 'won' \
             AND updated_at > now() - make_interval(days => $2)",
            &[&tid, &d],
        )
        .await)?
    .get(0);
    let body = views::stats_view(&views::StatsInput {
        days,
        conversations_by_channel: &conversations,
        leads_by_status: &statuses,
        appointments,
        quote_guard_interventions: guard_hits,
        sent_by_channel: &sent,
        daily: &daily,
        lead_value_cents: tenant_int(&tenant, "lead_value_cents"),
        won_value_cents: won_value,
    });
    Ok(Json(body).into_response())
}

// ------------------------------------------------------------------------------------------------ trailing slash

/// The route templates of this module, for Starlette's `redirect_slashes`.
const TEMPLATES: &[&str] = &[
    "/admin/capabilities",
    "/admin/tenants/*/leads",
    "/admin/tenants/*/campaigns",
    "/admin/campaigns/*",
    "/admin/campaigns/*/preview",
    "/admin/tenants/*/scoring",
    "/admin/tenants/*/sla",
    "/admin/tenants/*/tasks",
    "/admin/tenants/*/pipeline",
    "/admin/tenants/*/sales-summary",
    "/admin/tenants/*/appointments",
    "/admin/tenants/*/outbox",
    "/admin/tenants/*/conversations",
    "/admin/tenants/*/stats",
    "/admin/tenants/*/email-drafts",
    "/admin/tenants/*/phone-setup",
    "/admin/tenants/*/phone-numbers",
    "/admin/tenants/*/phone-calls",
];

fn matches_template(path: &str, template: &str) -> bool {
    let (p, t): (Vec<&str>, Vec<&str>) = (path.split('/').collect(), template.split('/').collect());
    p.len() == t.len() && p.iter().zip(&t).all(|(a, b)| if *b == "*" { !a.is_empty() } else { a == b })
}

/// Starlette (`redirect_slashes=True`): a path no route matches that ends in `/` is retried with ALL trailing slashes
/// removed, and a match there is a `307` to that path on the same host, query string kept. `path` here is the
/// decoded path, as Starlette sees it. The redirect is decided by the router, so it comes before the admin gate.
fn trailing_slash_redirect(decoded_path: &str, host: Option<&str>, query: Option<&str>) -> Option<Response> {
    if !decoded_path.ends_with('/') || decoded_path == "/" {
        return None;
    }
    let stripped = decoded_path.trim_end_matches('/');
    if !TEMPLATES.iter().any(|t| matches_template(stripped, t)) {
        return None;
    }
    // `URL(scope=...)` escapes these three in the path before `RedirectResponse` quotes the whole URL.
    let path = stripped.replace('?', "%3F").replace('#', "%23").replace('\\', "%5C");
    let mut url = format!("http://{}{path}", host.unwrap_or("localhost"));
    if let Some(q) = query.filter(|q| !q.is_empty()) {
        url.push('?');
        url.push_str(q);
    }
    let mut r = Response::new(axum::body::Body::empty());
    *r.status_mut() = StatusCode::TEMPORARY_REDIRECT;
    r.headers_mut()
        .insert(header::LOCATION, py_quote(&url).parse().ok()?);
    Some(r)
}

/// `urllib.parse.quote(url, safe=":/%#?=@[]!$&'()*+,;")`, which is how `RedirectResponse` writes its `Location`.
fn py_quote(url: &str) -> String {
    let mut out = String::with_capacity(url.len());
    for byte in url.bytes() {
        if byte.is_ascii_alphanumeric() || b"_.-~:/%#?=@[]!$&'()*+,;".contains(&byte) {
            out.push(byte as char);
        } else {
            out.push_str(&format!("%{byte:02X}"));
        }
    }
    out
}

/// Percent-decode a path the way an ASGI server hands it to Starlette (`%XX` only, no `+`).
fn unquote_path(s: &str) -> String {
    let b = s.as_bytes();
    let mut out = Vec::with_capacity(b.len());
    let mut i = 0;
    while i < b.len() {
        if b[i] == b'%' && i + 2 < b.len() && unhex(b[i + 1]).is_some() && unhex(b[i + 2]).is_some() {
            out.push(unhex(b[i + 1]).unwrap() * 16 + unhex(b[i + 2]).unwrap());
            i += 2;
        } else {
            out.push(b[i]);
        }
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// FastAPI's answer to a path no route matched: the `redirect_slashes` redirect for this module's routes, else its
/// JSON 404. (Routes outside this module keep the plain 404 they always had.)
pub async fn fallback(request: axum::extract::Request) -> Response {
    let uri = request.uri();
    let host = request
        .headers()
        .get(header::HOST)
        .and_then(|v| v.to_str().ok());
    if let Some(r) = trailing_slash_redirect(&unquote_path(uri.path()), host, uri.query()) {
        return r;
    }
    detail(404, "Not Found")
}

/// Starlette routes on the DECODED path, so `/admin/campaigns/7%2F` is `/admin/campaigns/7/` to it, which no route
/// matches and `redirect_slashes` turns into a `307` to `/admin/campaigns/7`. axum sees one segment `7/` and would
/// reach the handler, whose `unroutable` answers the plain 404; the redirect has to be decided first.
async fn redirect_guard(request: axum::extract::Request, next: axum::middleware::Next) -> Response {
    let uri = request.uri();
    let host = request.headers().get(header::HOST).and_then(|v| v.to_str().ok());
    if let Some(r) = trailing_slash_redirect(&unquote_path(uri.path()), host, uri.query()) {
        return r;
    }
    next.run(request).await
}

/// This module's routes, all `GET`.
pub fn routes() -> axum::Router<State> {
    axum::Router::new()
        .route("/admin/capabilities", get(capabilities))
        .route("/admin/tenants/:slug/leads", get(leads))
        .route("/admin/tenants/:slug/campaigns", get(campaigns))
        .route("/admin/campaigns/:campaign_id", get(campaign))
        .route("/admin/tenants/:slug/scoring", get(scoring_weights))
        .route("/admin/tenants/:slug/sla", get(sla))
        .route("/admin/tenants/:slug/tasks", get(tasks))
        .route("/admin/tenants/:slug/pipeline", get(pipeline))
        .route("/admin/tenants/:slug/sales-summary", get(sales_summary))
        .route("/admin/tenants/:slug/appointments", get(appointments))
        .route("/admin/tenants/:slug/outbox", get(outbox))
        .route("/admin/tenants/:slug/conversations", get(conversations))
        .route("/admin/tenants/:slug/stats", get(stats))
        .route("/admin/tenants/:slug/email-drafts", get(email_drafts))
        .route("/admin/tenants/:slug/phone-setup", get(phone_setup))
        .route("/admin/tenants/:slug/phone-numbers", get(phone_numbers))
        .route("/admin/tenants/:slug/phone-calls", get(phone_calls))
        .layer(axum::middleware::from_fn(redirect_guard))
}
