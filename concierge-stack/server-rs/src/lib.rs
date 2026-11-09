//! Read-only routes of the Concierge API in Rust: `/healthz`, `/api/v1/widget-config`, `GET /admin/tenants` and
//! `GET /admin/tenants/{slug}`, plus the owner-portal origin boundary and wildcard CORS. Every decision (origin allow-list,
//! channel authorization, public view, admin gate, snippet URLs) is `concierge-core` logic held to the Python originals;
//! this crate only adds HTTP and PostgreSQL. Nothing here writes except the calendar token backfill the Python route also does.
use axum::extract::{Path, Query, Request, State as AxState};
use axum::http::{header, HeaderMap, HeaderValue, Method, StatusCode};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::{Json, Router};
use concierge_core::edge::{self, Boundary};
use concierge_core::{channel_auth, ical, pydantic, report, requests, tenants};
use deadpool_postgres::{Manager, Pool};
use serde_json::{json, Map, Value};
use std::collections::HashMap;
use std::sync::Arc;
use tokio_postgres::types::Type;
use tokio_postgres::Row;
use tower_http::cors::{Any, CorsLayer};

#[derive(Clone)]
pub struct Config {
    pub database_url: String,
    pub admin_token: String,
    pub public_base_url: String,
    pub voice_recording_enabled: bool,
}

impl Config {
    pub fn from_env() -> Config {
        let get = |k: &str, d: &str| std::env::var(k).unwrap_or_else(|_| d.to_string());
        Config {
            database_url: get(
                "DATABASE_URL",
                "postgresql://postgres:postgres@localhost:5432/concierge",
            ),
            admin_token: get("ADMIN_TOKEN", ""),
            public_base_url: get("PUBLIC_BASE_URL", "http://localhost:8000"),
            voice_recording_enabled: concierge_core::pydantic::parse_bool(&json!(get(
                "VOICE_RECORDING_ENABLED",
                "false"
            )))
            .unwrap_or(false),
        }
    }
}

pub struct Inner {
    pub config: Config,
    pub pool: Option<Pool>,
}

#[derive(Clone)]
pub struct State(pub Arc<Inner>);

impl State {
    pub async fn connect(config: Config) -> Result<State, String> {
        let pg: tokio_postgres::Config = config.database_url.parse().map_err(|e| format!("{e}"))?;
        let manager = Manager::new(pg, tokio_postgres::NoTls);
        let pool = Pool::builder(manager)
            .max_size(10)
            .build()
            .map_err(|e| e.to_string())?;
        let _probe = pool.get().await.map_err(|e| e.to_string())?;
        Ok(State(Arc::new(Inner {
            config,
            pool: Some(pool),
        })))
    }

    /// A state with no database (for tests of routes that never reach it).
    pub fn without_database(config: Config) -> State {
        State(Arc::new(Inner { config, pool: None }))
    }
}

fn detail(status: u16, message: &str) -> Response {
    (
        StatusCode::from_u16(status).unwrap(),
        Json(json!({"detail": message})),
    )
        .into_response()
}

fn server_error() -> Response {
    (StatusCode::INTERNAL_SERVER_ERROR, "Internal Server Error").into_response()
}

/// Starlette's `{"detail": "Not Found"}` for a path no route matched.
async fn not_found() -> Response {
    detail(404, "Not Found")
}

/// `datetime.isoformat()` for an aware UTC timestamp, as FastAPI serialises it.
fn iso(ts: chrono::DateTime<chrono::Utc>) -> String {
    let micros = ts.timestamp_subsec_micros();
    let base = ts.format("%Y-%m-%dT%H:%M:%S").to_string();
    if micros == 0 {
        format!("{base}+00:00")
    } else {
        format!("{base}.{micros:06}+00:00")
    }
}

/// A row as Python's `dict(row)` is JSON-encoded: asyncpg returns `jsonb` as text, so it stays a string.
pub fn row_json(row: &Row) -> Value {
    let mut m = Map::new();
    for (i, col) in row.columns().iter().enumerate() {
        let t = col.type_();
        let v: Value = match *t {
            Type::UUID => row
                .get::<_, Option<uuid::Uuid>>(i)
                .map_or(Value::Null, |u| json!(u.to_string())),
            Type::TEXT | Type::VARCHAR | Type::BPCHAR | Type::NAME => row
                .get::<_, Option<String>>(i)
                .map_or(Value::Null, |s| json!(s)),
            Type::BOOL => row
                .get::<_, Option<bool>>(i)
                .map_or(Value::Null, |b| json!(b)),
            Type::INT2 => row
                .get::<_, Option<i16>>(i)
                .map_or(Value::Null, |n| json!(n)),
            Type::INT4 => row
                .get::<_, Option<i32>>(i)
                .map_or(Value::Null, |n| json!(n)),
            Type::INT8 => row
                .get::<_, Option<i64>>(i)
                .map_or(Value::Null, |n| json!(n)),
            Type::FLOAT4 => row
                .get::<_, Option<f32>>(i)
                .map_or(Value::Null, |n| json!(n as f64)),
            Type::FLOAT8 => row
                .get::<_, Option<f64>>(i)
                .map_or(Value::Null, |n| json!(n)),
            Type::TIMESTAMPTZ => row
                .get::<_, Option<chrono::DateTime<chrono::Utc>>>(i)
                .map_or(Value::Null, |d| json!(iso(d))),
            Type::JSONB | Type::JSON => row
                .get::<_, Option<Value>>(i)
                .map_or(Value::Null, |j| json!(j.to_string_python())),
            Type::TEXT_ARRAY | Type::VARCHAR_ARRAY => row
                .get::<_, Option<Vec<String>>>(i)
                .map_or(Value::Null, |a| json!(a)),
            _ => Value::Null,
        };
        m.insert(col.name().to_string(), v);
    }
    Value::Object(m)
}

/// PostgreSQL normalises `jsonb` text (`{"a": 1, "b": [1, 2]}`); serde writes it compactly, so re-render with Postgres' spacing.
trait PgJson {
    fn to_string_python(&self) -> String;
}

impl PgJson for Value {
    fn to_string_python(&self) -> String {
        fn w(v: &Value, out: &mut String) {
            match v {
                Value::Object(m) => {
                    out.push('{');
                    for (i, (k, x)) in m.iter().enumerate() {
                        if i > 0 {
                            out.push_str(", ");
                        }
                        out.push_str(&Value::String(k.clone()).to_string());
                        out.push_str(": ");
                        w(x, out);
                    }
                    out.push('}');
                }
                Value::Array(a) => {
                    out.push('[');
                    for (i, x) in a.iter().enumerate() {
                        if i > 0 {
                            out.push_str(", ");
                        }
                        w(x, out);
                    }
                    out.push(']');
                }
                other => out.push_str(&other.to_string()),
            }
        }
        let mut s = String::new();
        w(self, &mut s);
        s
    }
}

async fn tenant_where(state: &State, column: &str, value: &str) -> Result<Option<Value>, ()> {
    let pool = state.0.pool.as_ref().ok_or(())?;
    let client = pool.get().await.map_err(|_| ())?;
    let sql = format!("SELECT * FROM tenants WHERE {column} = $1");
    let row = client.query_opt(&sql, &[&value]).await.map_err(|_| ())?;
    match row {
        None => Ok(None),
        Some(r) => tenants::load(&row_json(&r)).map(Some).map_err(|_| ()),
    }
}

async fn healthz(AxState(state): AxState<State>) -> Response {
    let Some(pool) = state.0.pool.as_ref() else {
        return server_error();
    };
    let Ok(client) = pool.get().await else {
        return server_error();
    };
    match client.query_one("SELECT 1", &[]).await {
        Ok(_) => Json(json!({"ok": true})).into_response(),
        Err(_) => server_error(),
    }
}

/// FastAPI's 422 for a missing required query parameter.
fn missing_query(name: &str) -> Response {
    (StatusCode::UNPROCESSABLE_ENTITY, Json(json!({"detail": [{"type": "missing", "loc": ["query", name], "msg": "Field required", "input": null}]}))).into_response()
}

/// FastAPI's 422 for a query parameter pydantic could not coerce. The message text is pydantic v2's own.
fn unprocessable(name: &str, ty: &str, input: &str) -> Response {
    let msg = match ty {
        "int_parsing" => "Input should be a valid integer, unable to parse string as an integer",
        "int_parsing_size" => "Unable to parse input string as an integer, exceeded maximum size",
        _ => "Input should be a valid integer",
    };
    (
        StatusCode::UNPROCESSABLE_ENTITY,
        Json(json!({"detail": [{"type": ty, "loc": ["query", name], "msg": msg, "input": input}]})),
    )
        .into_response()
}

async fn widget_config(
    AxState(state): AxState<State>,
    Query(q): Query<HashMap<String, String>>,
    headers: HeaderMap,
) -> Response {
    let Some(key) = q.get("key") else {
        return missing_query("key");
    };
    let tenant = match tenant_where(&state, "public_key", key).await {
        Ok(Some(t)) => t,
        Ok(None) => return detail(404, "Unknown key"),
        Err(()) => return server_error(),
    };
    let allowed: Vec<String> = tenant["allowed_origins"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter_map(|x| x.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();
    let allowed_refs: Vec<&str> = allowed.iter().map(String::as_str).collect();
    let origin = headers.get("origin").and_then(|v| v.to_str().ok());
    if let Err((status, message)) =
        requests::origin_gate(&allowed_refs, origin, &state.0.config.public_base_url)
    {
        return detail(status, message);
    }
    let mut view = tenants::public_view(&tenant);
    let mut recording = state.0.config.voice_recording_enabled
        && concierge_core::pyval::truthy(tenant.get("voice_enabled"));
    if recording {
        recording = match authorized(&state, &tenant["id"], "call_recording").await {
            Ok(a) => a,
            Err(()) => return server_error(),
        };
    }
    view["recording_available"] = json!(recording);
    Json(view).into_response()
}

async fn authorized(state: &State, tenant_id: &Value, channel: &str) -> Result<bool, ()> {
    if !channel_auth::CHANNELS.contains(&channel) {
        return Ok(false);
    }
    let pool = state.0.pool.as_ref().ok_or(())?;
    let client = pool.get().await.map_err(|_| ())?;
    let tid = uuid::Uuid::parse_str(tenant_id.as_str().unwrap_or("")).map_err(|_| ())?;
    let stored = client.query_opt("SELECT authorized FROM tenant_channel_authorizations WHERE tenant_id=$1 AND channel=$2", &[&tid, &channel]).await.map_err(|_| ())?;
    Ok(stored.is_some_and(|r| r.get::<_, bool>(0)))
}

fn admin_gate(state: &State, headers: &HeaderMap) -> Result<(), Box<Response>> {
    let given = headers
        .get("x-admin-token")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    edge::require_admin(&state.0.config.admin_token, given).map_err(|(s, d)| Box::new(detail(s, d)))
}

async fn admin_list(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    if let Err(r) = admin_gate(&state, &headers) {
        return *r;
    }
    let Some(pool) = state.0.pool.as_ref() else {
        return server_error();
    };
    let Ok(client) = pool.get().await else {
        return server_error();
    };
    let Ok(rows) = client
        .query("SELECT * FROM tenants ORDER BY created_at DESC", &[])
        .await
    else {
        return server_error();
    };
    let mut out = Vec::new();
    for r in &rows {
        let Ok(t) = tenants::load(&row_json(r)) else {
            return server_error();
        };
        out.push(requests::with_snippet(&state.0.config.public_base_url, &t));
    }
    Json(Value::Array(out)).into_response()
}

fn new_token() -> String {
    use base64::Engine;
    use rand::RngCore;
    let mut b = [0u8; 24];
    rand::thread_rng().fill_bytes(&mut b);
    base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(b)
}

async fn admin_get(
    AxState(state): AxState<State>,
    Path(slug): Path<String>,
    headers: HeaderMap,
) -> Response {
    if let Err(r) = admin_gate(&state, &headers) {
        return *r;
    }
    let mut tenant = match tenant_where(&state, "slug", &slug).await {
        Ok(Some(t)) => t,
        Ok(None) => return detail(404, "Unknown tenant"),
        Err(()) => return server_error(),
    };
    let Some(pool) = state.0.pool.as_ref() else {
        return server_error();
    };
    let Ok(client) = pool.get().await else {
        return server_error();
    };
    let Ok(tid) = uuid::Uuid::parse_str(tenant["id"].as_str().unwrap_or("")) else {
        return server_error();
    };
    if !concierge_core::pyval::truthy(tenant.get("calendar_token")) {
        let token = new_token();
        let Ok(row) = client.query_one("UPDATE tenants SET calendar_token = COALESCE(calendar_token, $2) WHERE id = $1 RETURNING *", &[&tid, &token]).await else { return server_error() };
        let Ok(t) = tenants::load(&row_json(&row)) else {
            return server_error();
        };
        tenant = t;
    }
    let Ok(count) = client
        .query_one("SELECT count(*) FROM chunks WHERE tenant_id = $1", &[&tid])
        .await
    else {
        return server_error();
    };
    let mut body = requests::with_snippet(&state.0.config.public_base_url, &tenant);
    body["chunk_count"] = json!(count.get::<_, i64>(0));
    Json(body).into_response()
}

/// `GET /report/{token}`: the read-only client report. The unguessable token is the credential, so there is
/// no session and no origin gate — `edge::owner_boundary` leaves this path alone, exactly as Python's
/// `owner_boundary` middleware does. `days` is clamped inside `report::clamp_days` like `_stats` does.
async fn client_report(
    AxState(state): AxState<State>,
    Path(token): Path<String>,
    Query(q): Query<HashMap<String, String>>,
) -> Response {
    let days = match q.get("days") {
        None => 30,
        Some(raw) => match pydantic::parse_int(&json!(raw)) {
            Ok(n) => report::clamp_days(n),
            Err(ty) => return unprocessable("days", ty, raw),
        },
    };
    // `make_interval(days => $n)` makes PostgreSQL infer `int4` for the parameter, so the value must be bound
    // as `i32`: binding the `i64` that `min(max(days,1),365)` produces is rejected by the driver as a type
    // mismatch. `days` is already clamped to 1..=365 here, so the narrowing cannot lose information.
    let days_param = days as i32;
    let Some(pool) = state.0.pool.as_ref() else {
        return server_error();
    };
    let Ok(client) = pool.get().await else {
        return server_error();
    };
    let Ok(row) = client
        .query_opt("SELECT * FROM tenants WHERE report_token = $1", &[&token])
        .await
    else {
        return server_error();
    };
    let Some(row) = row else {
        return detail(404, "Unknown report");
    };
    let Ok(tenant) = tenants::load(&row_json(&row)) else {
        return server_error();
    };
    let tenant_id = match uuid::Uuid::parse_str(tenant["id"].as_str().unwrap_or("")) {
        Ok(id) => id,
        Err(_) => return server_error(),
    };

    // The aggregates, one query per block, in the same shape `_stats` reads them.
    let Ok(convs) = client
        .query(
            "SELECT channel, count(*) AS conversations FROM conversations \
             WHERE tenant_id = $1 AND channel <> 'eval' AND started_at > now() - make_interval(days => $2) \
             GROUP BY channel",
            &[&tenant_id, &days_param],
        )
        .await
    else {
        return server_error();
    };
    let convs_by_channel: Vec<(String, i64)> = convs
        .iter()
        .map(|r| (r.get::<_, String>(0), r.get::<_, i64>(1)))
        .collect();

    let Ok(statuses) = client
        .query(
            "SELECT status, count(*) AS n FROM leads WHERE tenant_id = $1 \
             AND created_at > now() - make_interval(days => $2) GROUP BY status",
            &[&tenant_id, &days_param],
        )
        .await
    else {
        return server_error();
    };
    let leads_by_status: Vec<(String, i64)> = statuses
        .iter()
        .map(|r| (r.get::<_, String>(0), r.get::<_, i64>(1)))
        .collect();

    let Ok(appointments) = client
        .query_one(
            "SELECT count(*) FROM appointments WHERE tenant_id = $1 AND created_at > now() - make_interval(days => $2)",
            &[&tenant_id, &days_param],
        )
        .await
    else {
        return server_error();
    };
    let appointments = appointments.get::<_, i64>(0);

    let Ok(guard_hits) = client
        .query_one(
            "SELECT count(*) FROM messages m JOIN conversations c ON c.id = m.conversation_id \
             WHERE c.tenant_id = $1 AND m.flag = 'quote_guard' AND m.created_at > now() - make_interval(days => $2)",
            &[&tenant_id, &days_param],
        )
        .await
    else {
        return server_error();
    };
    let guard_hits = guard_hits.get::<_, i64>(0);

    let Ok(sent) = client
        .query(
            "SELECT channel, count(*) AS n FROM outbox WHERE tenant_id = $1 AND status = 'sent' \
             AND created_at > now() - make_interval(days => $2) GROUP BY channel",
            &[&tenant_id, &days_param],
        )
        .await
    else {
        return server_error();
    };
    let sent_by_channel: Vec<(String, i64)> = sent
        .iter()
        .map(|r| (r.get::<_, String>(0), r.get::<_, i64>(1)))
        .collect();

    let Ok(daily_rows) = client
        .query(
            "SELECT d::date AS day, \
               (SELECT count(*) FROM conversations c WHERE c.tenant_id = $1 AND c.channel <> 'eval' AND c.started_at::date = d::date) AS conversations, \
               (SELECT count(*) FROM leads l WHERE l.tenant_id = $1 AND l.created_at::date = d::date) AS leads \
             FROM generate_series(now() - make_interval(days => $2 - 1), now(), interval '1 day') d \
             ORDER BY day",
            &[&tenant_id, &days_param],
        )
        .await
    else {
        return server_error();
    };
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

    let Ok(won_value) = client
        .query_one(
            "SELECT COALESCE(sum(value_cents), 0) FROM leads WHERE tenant_id = $1 AND status = 'won' \
             AND updated_at > now() - make_interval(days => $2)",
            &[&tenant_id, &days_param],
        )
        .await
    else {
        return server_error();
    };
    let won_value_cents = won_value.get::<_, i64>(0);

    let Ok(leads) = client
        .query(
            "SELECT name, message, channel, status, score_label, created_at FROM leads WHERE tenant_id = $1 \
             AND created_at > now() - make_interval(days => $2) ORDER BY created_at DESC LIMIT 25",
            &[&tenant_id, &days_param],
        )
        .await
    else {
        return server_error();
    };
    let lead_rows: Vec<Value> = leads.iter().map(row_json).collect();

    let stats = report::Stats {
        days,
        tenant: &tenant,
        conversations_by_channel: &convs_by_channel,
        leads_by_status: &leads_by_status,
        appointments,
        quote_guard_interventions: guard_hits,
        sent_by_channel: &sent_by_channel,
        daily: &daily,
        won_value_cents,
    };
    let page = report::client_report(&stats, &lead_rows);
    (
        StatusCode::OK,
        [(header::CONTENT_TYPE, "text/html; charset=utf-8")],
        page,
    )
        .into_response()
}

/// `GET /api/v1/calendar/{token}.ics`: the read-only appointment feed. Like the report, the token is the
/// credential, so the route sits outside the owner boundary.
///
/// Starlette matches this path with `^/api/v1/calendar/(?P<token>[^/]+)\.ics$`: the `.ics` suffix is required
/// and the token must be at least one character, so `/api/v1/calendar/abc` and `/api/v1/calendar/.ics` are both
/// FastAPI 404s. axum 0.7 has no suffix syntax — `:token.ics` silently captures the whole segment including the
/// suffix, exactly as a bare `:token` would — so the suffix is stripped here and its absence answered as
/// Starlette's 404. Keeping the route a single `:token` also avoids registering a second pattern for the same
/// path, which would shadow this one.
async fn calendar_feed(AxState(state): AxState<State>, Path(raw): Path<String>) -> Response {
    let Some(token) = raw.strip_suffix(".ics").filter(|t| !t.is_empty()) else {
        return not_found().await;
    };
    let Some(pool) = state.0.pool.as_ref() else {
        return server_error();
    };
    let Ok(client) = pool.get().await else {
        return server_error();
    };
    let Ok(row) = client
        .query_opt("SELECT * FROM tenants WHERE calendar_token = $1", &[&token])
        .await
    else {
        return server_error();
    };
    let Some(row) = row else {
        return detail(404, "Unknown calendar");
    };
    let Ok(tenant) = tenants::load(&row_json(&row)) else {
        return server_error();
    };
    let tenant_id = match uuid::Uuid::parse_str(tenant["id"].as_str().unwrap_or("")) {
        Ok(id) => id,
        Err(_) => return server_error(),
    };
    let Ok(rows) = client
        .query(
            "SELECT * FROM appointments WHERE tenant_id = $1 AND starts_at > now() - interval '30 days' \
             ORDER BY starts_at",
            &[&tenant_id],
        )
        .await
    else {
        return server_error();
    };
    let appointments: Vec<ical::Appointment> = rows.iter().map(appointment_from_row).collect();
    let body = ical::build(
        tenant["name"].as_str().unwrap_or(""),
        &appointments,
        chrono::Utc::now().timestamp(),
    );
    (
        StatusCode::OK,
        [
            (header::CONTENT_TYPE, "text/calendar; charset=utf-8"),
            (header::CACHE_CONTROL, "private, max-age=300"),
        ],
        body,
    )
        .into_response()
}

/// One appointment row as `ical::Appointment`. `id` is a UUID and the timestamps are `timestamptz`; the feed
/// builder takes Unix seconds, so the conversion happens once here.
fn appointment_from_row(row: &Row) -> ical::Appointment {
    let text = |name: &str| row.get::<_, Option<String>>(name);
    ical::Appointment {
        id: row
            .get::<_, Option<uuid::Uuid>>("id")
            .map_or_else(String::new, |u| u.to_string()),
        name: text("name"),
        phone: text("phone"),
        email: text("email"),
        notes: text("notes"),
        status: text("status"),
        starts_at: row
            .get::<_, Option<chrono::DateTime<chrono::Utc>>>("starts_at")
            .map_or(0, |d| d.timestamp()),
        ends_at: row
            .get::<_, Option<chrono::DateTime<chrono::Utc>>>("ends_at")
            .map_or(0, |d| d.timestamp()),
    }
}

/// `owner_boundary`: hardening headers and the foreign-origin refusal for the owner portal and device SMS.
async fn boundary(AxState(state): AxState<State>, request: Request, next: Next) -> Response {
    let path = request.uri().path().to_string();
    let host = request
        .headers()
        .get(header::HOST)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();
    let origin = request
        .headers()
        .get("origin")
        .and_then(|v| v.to_str().ok())
        .map(String::from);
    match edge::owner_boundary(
        &path,
        "http",
        &host,
        origin.as_deref(),
        &state.0.config.public_base_url,
    ) {
        Boundary::Passthrough => next.run(request).await,
        Boundary::Refuse => {
            let mut r = Response::new(axum::body::Body::empty());
            *r.status_mut() = StatusCode::FORBIDDEN;
            r.headers_mut()
                .insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
            r
        }
        Boundary::Protected => {
            let mut r = next.run(request).await;
            for (k, v) in edge::PROTECTED_HEADERS {
                r.headers_mut().insert(
                    axum::http::HeaderName::from_static(k),
                    HeaderValue::from_static(v),
                );
            }
            r
        }
    }
}

pub fn app(state: State) -> Router {
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods([
            Method::GET,
            Method::POST,
            Method::PATCH,
            Method::DELETE,
            Method::OPTIONS,
        ])
        .allow_headers(
            [
                "content-type",
                "x-admin-token",
                "authorization",
                "x-voice-session-token",
            ]
            .map(axum::http::HeaderName::from_static),
        );
    Router::new()
        .route("/healthz", get(healthz))
        .route("/api/v1/widget-config", get(widget_config))
        .route("/admin/tenants", get(admin_list))
        .route("/admin/tenants/:slug", get(admin_get))
        .route("/report/:token", get(client_report))
        .route("/api/v1/calendar/:token", get(calendar_feed))
        // FastAPI answers an unmatched path (including `/report/`, whose empty segment matches no route) with
        // its JSON 404; axum's default fallback would send an empty body instead.
        .fallback(not_found)
        .layer(middleware::from_fn_with_state(state.clone(), boundary))
        .layer(cors)
        .with_state(state)
}
