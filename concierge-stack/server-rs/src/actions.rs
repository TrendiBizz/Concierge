//! First-party action executor. A database transaction owns the durable ledger,
//! case lock and every draft/task effect; no route sends customer messages.
use crate::{detail, row_json, server_error, State};
use axum::{
    body::Bytes,
    extract::{Path, Query, State as AxState},
    http::HeaderMap,
    response::{IntoResponse, Response},
    Json,
};
use chrono::{DateTime, Utc};
use concierge_core::{
    contact::contact_key,
    edge, py_strip,
    pyval::{self, truncate_chars},
};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::HashMap;
use tokio_postgres::GenericClient;
use uuid::Uuid;

const READ_ONLY: &[&str] = &[
    "get_case_context",
    "search_business_knowledge",
    "get_channel_readiness",
    "check_availability",
    "get_action_status",
];
const MUTATING: &[&str] = &[
    "prepare_reply",
    "prepare_quote",
    "request_booking",
    "schedule_followup",
    "escalate_case",
];
const VERSION:&str="SELECT floor(extract(epoch FROM greatest(l.created_at,l.updated_at,COALESCE(st.updated_at,l.created_at),COALESCE((SELECT max(m.created_at) FROM messages m WHERE m.conversation_id=l.conversation_id),l.created_at)))*1000)::bigint FROM leads l LEFT JOIN case_action_state st ON st.tenant_id=l.tenant_id AND st.lead_id=l.id WHERE l.tenant_id=$1 AND l.id=$2";

enum Failure {
    Reply(u16, Value),
    Database,
}
impl From<tokio_postgres::Error> for Failure {
    fn from(_: tokio_postgres::Error) -> Self {
        Self::Database
    }
}
type Result<T> = std::result::Result<T, Failure>;
impl Failure {
    fn response(self) -> Response {
        match self {
            Self::Database => server_error(),
            Self::Reply(status, value) => (
                axum::http::StatusCode::from_u16(status).unwrap(),
                Json(json!({"detail":value})),
            )
                .into_response(),
        }
    }
}
fn conflict(code: &str, message: &str) -> Failure {
    Failure::Reply(409, json!({"error":code,"detail":message}))
}
fn missing() -> Failure {
    Failure::Reply(404, json!("Case not found"))
}
fn gate(state: &State, headers: &HeaderMap) -> Option<Response> {
    let cfg = &state.0.config;
    if !cfg.action_gateway_enabled || cfg.action_gateway_key.is_empty() {
        return Some(detail(404, "Not found"));
    }
    let key = headers
        .get("x-action-gateway-key")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    edge::require_admin(&cfg.action_gateway_key, key)
        .err()
        .map(|_| detail(401, "Invalid gateway key"))
}
fn ids(raw: &str, query: &HashMap<String, String>) -> Result<(Uuid, Uuid)> {
    let lead = Uuid::parse_str(raw).map_err(|_| Failure::Reply(422, json!("Invalid lead id")))?;
    let tenant = query
        .get("tenant_id")
        .and_then(|s| Uuid::parse_str(s).ok())
        .ok_or_else(|| Failure::Reply(422, json!("Invalid tenant id")))?;
    Ok((tenant, lead))
}
async fn tenant<C: GenericClient + Sync>(c: &C, id: Uuid) -> Result<Value> {
    c.query_opt("SELECT * FROM tenants WHERE id=$1", &[&id])
        .await?
        .map(|r| row_json(&r))
        .ok_or_else(missing)
}
async fn lead<C: GenericClient + Sync>(c: &C, tid: Uuid, lid: Uuid, lock: bool) -> Result<Value> {
    c.query_opt(
        if lock {
            "SELECT * FROM leads WHERE tenant_id=$1 AND id=$2 FOR UPDATE"
        } else {
            "SELECT * FROM leads WHERE tenant_id=$1 AND id=$2"
        },
        &[&tid, &lid],
    )
    .await?
    .map(|r| row_json(&r))
    .ok_or_else(missing)
}
async fn version<C: GenericClient + Sync>(c: &C, tid: Uuid, lid: Uuid) -> Result<i64> {
    Ok(c.query_one(VERSION, &[&tid, &lid]).await?.get(0))
}
async fn paused<C: GenericClient + Sync>(c: &C, tid: Uuid, lid: Uuid) -> Result<bool> {
    Ok(c.query_opt(
        "SELECT automation_paused FROM case_action_state WHERE tenant_id=$1 AND lead_id=$2",
        &[&tid, &lid],
    )
    .await?
    .is_some_and(|r| r.get(0)))
}
async fn settings<C: GenericClient + Sync>(c: &C, tid: Uuid) -> Result<(String, f64)> {
    Ok(c.query_opt(
        "SELECT autonomy,min_confidence::float8 FROM case_action_settings WHERE tenant_id=$1",
        &[&tid],
    )
    .await?
    .map_or(("shadow".into(), 0.8), |r| (r.get(0), r.get(1))))
}
async fn authorized<C: GenericClient + Sync>(c: &C, tid: Uuid, channel: &str) -> Result<bool> {
    Ok(c.query_opt(
        "SELECT authorized FROM tenant_channel_authorizations WHERE tenant_id=$1 AND channel=$2",
        &[&tid, &channel],
    )
    .await?
    .is_some_and(|r| r.get(0)))
}
fn cc<'a>(tenant: &'a Value, state: &'a State) -> &'a str {
    let valid =
        |s: &str| !s.is_empty() && s.chars().count() <= 3 && s.chars().all(|c| c.is_ascii_digit());
    let own = py_strip(tenant["default_country_code"].as_str().unwrap_or(""));
    if valid(own) {
        own
    } else {
        let fallback = py_strip(&state.0.config.default_country_code);
        if valid(fallback) {
            fallback
        } else {
            ""
        }
    }
}
fn text<'a>(v: &'a Value, key: &str) -> &'a str {
    v[key].as_str().unwrap_or("")
}
fn contacts(l: &Value, country: &str) -> Vec<String> {
    let mut keys: Vec<_> = ["email", "phone"]
        .iter()
        .map(|f| contact_key(text(l, f), country))
        .filter(|s| !s.is_empty())
        .collect();
    keys.sort();
    keys.dedup();
    keys
}

pub(crate) async fn context(
    AxState(state): AxState<State>,
    Path(raw): Path<String>,
    Query(q): Query<HashMap<String, String>>,
    headers: HeaderMap,
) -> Response {
    if let Some(r) = crate::unroutable(&raw) {
        return r;
    }
    if let Some(r) = gate(&state, &headers) {
        return r;
    }
    match context_inner(&state, &raw, &q).await {
        Ok(v) => Json(v).into_response(),
        Err(e) => e.response(),
    }
}
async fn context_inner(state: &State, raw: &str, q: &HashMap<String, String>) -> Result<Value> {
    let (tid, lid) = ids(raw, q)?;
    let pool = state.0.pool.as_ref().ok_or(Failure::Database)?;
    let c = pool.get().await.map_err(|_| Failure::Database)?;
    let t = tenant(&**c, tid).await?;
    let l = lead(&**c, tid, lid, false).await?;
    let country = cc(&t, state);
    let keys = contacts(&l, country);
    let suppressed: Vec<String> = c
        .query(
            "SELECT contact FROM opt_outs WHERE tenant_id=$1 AND contact=ANY($2::text[])",
            &[&tid, &keys],
        )
        .await?
        .iter()
        .map(|r| r.get(0))
        .collect();
    let chunks=c.query("SELECT content FROM chunks WHERE tenant_id=$1 AND content LIKE '%$%' ORDER BY id LIMIT 300",&[&tid]).await?;
    let mut parts = vec![
        text(&t, "persona").to_owned(),
        text(&t, "incentive").to_owned(),
    ];
    parts.extend(chunks.iter().map(|r| r.get::<_, String>(0)));
    let evidence = truncate_chars(&parts.join("\n"), 100_000);
    let (autonomy, confidence) = settings(&**c, tid).await?;
    Ok(
        json!({"tenant_id":tid.to_string(),"case_id":lid.to_string(),"case_version":version(&**c,tid,lid).await?,"automation_paused":paused(&**c,tid,lid).await?,"timezone":if text(&t,"timezone").is_empty(){"UTC"}else{text(&t,"timezone")},"default_country_code":country,"email_send_authorized":authorized(&**c,tid,"email_send").await?,"sms_send_authorized":authorized(&**c,tid,"sms_send").await?,"case_contacts":keys,"suppressed":suppressed,"knowledge_evidence":evidence,"autonomy":autonomy,"min_confidence":confidence,"approvals":{}}),
    )
}

pub(crate) async fn brief(
    AxState(state): AxState<State>,
    Path(raw): Path<String>,
    Query(q): Query<HashMap<String, String>>,
    headers: HeaderMap,
) -> Response {
    if let Some(r) = crate::unroutable(&raw) {
        return r;
    }
    if let Some(r) = gate(&state, &headers) {
        return r;
    }
    match brief_inner(&state, &raw, &q).await {
        Ok(v) => Json(v).into_response(),
        Err(e) => e.response(),
    }
}
async fn brief_inner(state: &State, raw: &str, q: &HashMap<String, String>) -> Result<Value> {
    let (tid, lid) = ids(raw, q)?;
    let pool = state.0.pool.as_ref().ok_or(Failure::Database)?;
    let c = pool.get().await.map_err(|_| Failure::Database)?;
    let t = tenant(&**c, tid).await?;
    let l = lead(&**c, tid, lid, false).await?;
    let mut messages = Vec::new();
    if let Some(cid) = l["conversation_id"]
        .as_str()
        .and_then(|s| Uuid::parse_str(s).ok())
    {
        let rows=c.query("SELECT role,content FROM messages WHERE conversation_id=$1 ORDER BY id DESC LIMIT 20",&[&cid]).await?;
        messages=rows.iter().rev().map(|r|json!({"role":r.get::<_,String>(0),"content":truncate_chars(&r.get::<_,String>(1),1000)})).collect();
    }
    Ok(
        json!({"business":{"name":t["name"],"guidance":truncate_chars(text(&t,"persona"),1000)},"lead":{"name":truncate_chars(text(&l,"name"),120),"email":text(&l,"email"),"phone":text(&l,"phone"),"channel":text(&l,"channel"),"status":text(&l,"status"),"message":truncate_chars(text(&l,"message"),2000)},"messages":messages}),
    )
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Automation {
    tenant_id: Uuid,
    paused: bool,
}
pub(crate) async fn automation(
    AxState(state): AxState<State>,
    Path(raw): Path<String>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    if let Some(r) = crate::unroutable(&raw) {
        return r;
    }
    if let Some(r) = gate(&state, &headers) {
        return r;
    }
    let normalised = match parse_request(&bytes, "ActionAutomation") {
        Ok(v) => v,
        Err(r) => return *r,
    };
    let body: Automation = match serde_json::from_value(normalised) {
        Ok(b) => b,
        Err(_) => return detail(422, "Invalid automation request"),
    };
    let id = match Uuid::parse_str(&raw) {
        Ok(id) => id,
        Err(_) => return detail(422, "Invalid lead id"),
    };
    match automation_inner(&state, id, body).await {
        Ok(v) => Json(v).into_response(),
        Err(e) => e.response(),
    }
}
async fn automation_inner(state: &State, lid: Uuid, b: Automation) -> Result<Value> {
    let pool = state.0.pool.as_ref().ok_or(Failure::Database)?;
    let c = pool.get().await.map_err(|_| Failure::Database)?;
    lead(&**c, b.tenant_id, lid, false).await?;
    c.execute("INSERT INTO case_action_state(tenant_id,lead_id,automation_paused,updated_at) VALUES($1,$2,$3,now()) ON CONFLICT(tenant_id,lead_id) DO UPDATE SET automation_paused=EXCLUDED.automation_paused,updated_at=now()",&[&b.tenant_id,&lid,&b.paused]).await?;
    Ok(json!({"case_id":lid.to_string(),"automation_paused":b.paused}))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Action {
    op: String,
    idempotency_key: String,
    dedupe_key: String,
    fingerprint: String,
    case_version: i64,
    #[serde(default = "empty_object")]
    params: Value,
}
fn empty_object() -> Value {
    json!({})
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Delivery {
    channel: String,
    recipient: String,
    #[serde(default)]
    subject: String,
    body: String,
    mode: String,
    fingerprint: String,
    dedupe_key: String,
    #[serde(default)]
    send_at: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Bundle {
    task_id: String,
    tenant_id: Uuid,
    #[serde(default)]
    actions: Vec<Action>,
    #[serde(default)]
    delivery: Option<Delivery>,
}
fn len(s: &str, min: usize, max: usize) -> bool {
    let n = s.chars().count();
    n >= min && n <= max
}
fn valid(b: &Bundle) -> bool {
    len(&b.task_id, 1, 300)
        && b.actions.len() <= 10
        && b.actions.iter().all(|a| {
            len(&a.op, 0, 64)
                && len(&a.idempotency_key, 1, 128)
                && len(&a.dedupe_key, 0, 300)
                && len(&a.fingerprint, 1, 128)
                && a.params.is_object()
        })
        && b.delivery.as_ref().is_none_or(|d| {
            ["email", "sms"].contains(&d.channel.as_str())
                && len(&d.recipient, 0, 320)
                && len(&d.subject, 0, 300)
                && len(&d.body, 1, 4000)
                && ["shadow_only", "needs_approval", "auto"].contains(&d.mode.as_str())
                && len(&d.fingerprint, 1, 128)
                && len(&d.dedupe_key, 1, 300)
        })
}
pub(crate) async fn execute(
    AxState(state): AxState<State>,
    Path(raw): Path<String>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    if let Some(r) = crate::unroutable(&raw) {
        return r;
    }
    if let Some(r) = gate(&state, &headers) {
        return r;
    }
    let normalised = match parse_request(&bytes, "CaseBundle") {
        Ok(v) => v,
        Err(r) => return *r,
    };
    let b: Bundle = match serde_json::from_value(normalised) {
        Ok(b) => b,
        Err(_) => return detail(422, "Invalid action bundle"),
    };
    if !valid(&b) {
        return detail(422, "Invalid action bundle");
    }
    let id = match Uuid::parse_str(&raw) {
        Ok(id) => id,
        Err(_) => return detail(422, "Invalid lead id"),
    };
    match execute_inner(&state, id, b).await {
        Ok(v) => Json(v).into_response(),
        Err(e) => e.response(),
    }
}
async fn record<C: GenericClient + Sync>(
    c: &C,
    tid: Uuid,
    lid: Uuid,
    key: &str,
    op: &str,
    fingerprint: &str,
) -> Result<Option<Value>> {
    let initial = json!({"op":op,"state":"pending"});
    let inserted=c.query_opt("INSERT INTO case_actions(tenant_id,idempotency_key,lead_id,op,fingerprint,state,result) VALUES($1,$2,$3,$4,$5,'done',$6) ON CONFLICT(tenant_id,idempotency_key) DO NOTHING RETURNING 1",&[&tid,&key,&lid,&op,&fingerprint,&initial]).await?;
    if inserted.is_some() {
        return Ok(None);
    }
    let stored=c.query_one("SELECT lead_id,fingerprint,result FROM case_actions WHERE tenant_id=$1 AND idempotency_key=$2",&[&tid,&key]).await?;
    if stored.get::<_, Uuid>(0) != lid || stored.get::<_, String>(1) != fingerprint {
        return Err(conflict(
            "key_reuse",
            "this idempotency key was used for a different request",
        ));
    }
    Ok(Some(stored.get(2)))
}
async fn task<C: GenericClient + Sync>(
    c: &C,
    tid: Uuid,
    lid: Uuid,
    title: &str,
    notes: &str,
    due: Option<DateTime<Utc>>,
) -> Result<i64> {
    Ok(c.query_one("INSERT INTO tasks(tenant_id,lead_id,title,notes,due_at,kind,source) VALUES($1,$2,$3,$4,$5,'manual','concierge') RETURNING id",&[&tid,&lid,&truncate_chars(title,200),&truncate_chars(notes,2000),&due]).await?.get(0))
}
fn parameter(p: &Value, key: &str, default: &str) -> String {
    if pyval::truthy(p.get(key)) {
        pyval::str_or_empty(p.get(key)).unwrap_or_else(|| p[key].to_string())
    } else {
        default.into()
    }
}
fn due(p: &Value) -> Result<Option<DateTime<Utc>>> {
    if !pyval::truthy(p.get("due_at")) {
        return Ok(None);
    }
    let raw = parameter(p, "due_at", "");
    match DateTime::parse_from_rfc3339(&raw.replace(' ', "T")) {
        Ok(d) => Ok(Some(d.with_timezone(&Utc))),
        Err(_) => {
            let naive = chrono::NaiveDateTime::parse_from_str(&raw, "%Y-%m-%dT%H:%M:%S%.f").is_ok()
                || chrono::NaiveDate::parse_from_str(&raw, "%Y-%m-%d").is_ok();
            Err(Failure::Reply(
                422,
                json!({"error":if naive{"due_at_needs_timezone"}else{"bad_due_at"}}),
            ))
        }
    }
}
async fn execute_inner(state: &State, lid: Uuid, b: Bundle) -> Result<Value> {
    let tid = b.tenant_id;
    let pool = state.0.pool.as_ref().ok_or(Failure::Database)?;
    let mut c = pool.get().await.map_err(|_| Failure::Database)?;
    let t = tenant(&**c, tid).await?;
    let tx = c.transaction().await?;
    let l = lead(&*tx, tid, lid, true).await?;
    if settings(&*tx, tid).await?.0 == "shadow" {
        return Err(conflict(
            "shadow_mode",
            "this business is in shadow mode; nothing executes",
        ));
    }
    let is_paused = paused(&*tx, tid, lid).await?;
    let current = version(&*tx, tid, lid).await?;
    for a in &b.actions {
        if !READ_ONLY.contains(&a.op.as_str()) && !MUTATING.contains(&a.op.as_str()) {
            return Err(Failure::Reply(
                422,
                json!({"error":"unknown_operation","op":a.op}),
            ));
        }
        if READ_ONLY.contains(&a.op.as_str()) {
            continue;
        }
        if a.case_version != current {
            return Err(conflict(
                "stale_case",
                &format!("planned against v{}, case is v{current}", a.case_version),
            ));
        }
        if is_paused && ["request_booking", "schedule_followup"].contains(&a.op.as_str()) {
            return Err(conflict("automation_paused", &a.op));
        }
    }
    if let Some(d) = &b.delivery {
        if d.mode == "shadow_only" {
            return Err(conflict(
                "shadow_mode",
                "a shadow-only delivery cannot execute",
            ));
        }
        if is_paused {
            return Err(conflict(
                "automation_paused",
                "a person has taken over this case",
            ));
        }
        if !authorized(
            &*tx,
            tid,
            if d.channel == "email" {
                "email_send"
            } else {
                "sms_send"
            },
        )
        .await?
        {
            return Err(conflict("channel_not_authorized", ""));
        }
        let country = cc(&t, state);
        let key = contact_key(&d.recipient, country);
        if !contacts(&l, country).contains(&key) {
            return Err(conflict("recipient_not_on_case", ""));
        }
        if tx
            .query_opt(
                "SELECT 1 FROM opt_outs WHERE tenant_id=$1 AND contact=$2",
                &[&tid, &key],
            )
            .await?
            .is_some()
        {
            return Err(conflict("recipient_opted_out", ""));
        }
    }
    let mut results = Vec::new();
    for a in &b.actions {
        if READ_ONLY.contains(&a.op.as_str()) || a.op == "prepare_reply" {
            results.push(json!({"op":a.op,"state":"noop"}));
            continue;
        }
        if let Some(mut stored) =
            record(&*tx, tid, lid, &a.idempotency_key, &a.op, &a.fingerprint).await?
        {
            stored["duplicate"] = json!(true);
            results.push(stored);
            continue;
        }
        let p = &a.params;
        let out = match a.op.as_str() {
            "schedule_followup" => {
                let id = task(
                    &*tx,
                    tid,
                    lid,
                    &parameter(p, "title", "Follow up (suggested by Concierge)"),
                    &parameter(p, "notes", ""),
                    due(p)?,
                )
                .await?;
                json!({"op":a.op,"state":"task_created","task_id":id})
            }
            "escalate_case" => {
                let title = "Take over: ".to_owned()
                    + &truncate_chars(&parameter(p, "reason", "Concierge asked for a person"), 150);
                let id = task(&*tx, tid, lid, &title, &parameter(p, "notes", ""), None).await?;
                tx.execute("INSERT INTO case_action_state(tenant_id,lead_id,automation_paused,updated_at) VALUES($1,$2,true,now()) ON CONFLICT(tenant_id,lead_id) DO UPDATE SET automation_paused=true,updated_at=now()",&[&tid,&lid]).await?;
                json!({"op":a.op,"state":"escalated","task_id":id})
            }
            _ => {
                let id = task(
                    &*tx,
                    tid,
                    lid,
                    &format!("Concierge asked for: {}", a.op.replace('_', " ")),
                    &truncate_chars(&crate::PgJson::to_string_python(p), 1800),
                    None,
                )
                .await?;
                json!({"op":a.op,"state":"needs_human","task_id":id})
            }
        };
        tx.execute(
            "UPDATE case_actions SET result=$3 WHERE tenant_id=$1 AND idempotency_key=$2",
            &[&tid, &a.idempotency_key, &out],
        )
        .await?;
        results.push(out);
    }
    let mut delivery_result = Value::Null;
    if let Some(d) = &b.delivery {
        let _ = &d.send_at; // Stored drafts require human approval; no scheduled send is performed.
        if let Some(mut stored) = record(
            &*tx,
            tid,
            lid,
            &d.dedupe_key,
            &format!("delivery:{}", d.channel),
            &d.fingerprint,
        )
        .await?
        {
            stored["duplicate"] = json!(true);
            delivery_result = stored
        } else if d.channel == "email" {
            let subject = truncate_chars(
                &d.subject.split_whitespace().collect::<Vec<_>>().join(" "),
                250,
            );
            let inbound = truncate_chars(
                if text(&l, "message").is_empty() {
                    "(no inbound text)"
                } else {
                    text(&l, "message")
                },
                20000,
            );
            let id:i64=tx.query_one("INSERT INTO email_drafts(tenant_id,source_id,sender,subject,inbound_body,reply_body,origin) VALUES($1,$2,$3,$4,$5,$6,'concierge') ON CONFLICT(tenant_id,source_id) WHERE source_id IS NOT NULL DO UPDATE SET source_id=EXCLUDED.source_id RETURNING id",&[&tid,&truncate_chars(&d.dedupe_key,500),&py_strip(&d.recipient),&subject,&inbound,&truncate_chars(&d.body,10000)]).await?.get(0);
            delivery_result =
                json!({"state":"draft_created","draft_id":id,"needs_human_approval":true});
        } else {
            let id = task(
                &*tx,
                tid,
                lid,
                "Send this SMS reply (drafted by Concierge)",
                &d.body,
                None,
            )
            .await?;
            delivery_result =
                json!({"state":"task_created","task_id":id,"needs_human_approval":true})
        }
        tx.execute(
            "UPDATE case_actions SET result=$3 WHERE tenant_id=$1 AND idempotency_key=$2",
            &[&tid, &d.dedupe_key, &delivery_result],
        )
        .await?;
    }
    tx.commit().await?;
    Ok(json!({"task_id":b.task_id,"actions":results,"delivery":delivery_result}))
}

fn parse_request(bytes: &[u8], model: &str) -> std::result::Result<Value, Box<Response>> {
    let original: Value =
        serde_json::from_slice(bytes).map_err(|_| Box::new(detail(422, "Invalid JSON")))?;
    if original.is_null() {
        return Err(Box::new((axum::http::StatusCode::UNPROCESSABLE_ENTITY,Json(json!({"detail":[{"type":"missing","loc":["body"],"msg":"Field required","input":null}]}))).into_response()));
    }
    concierge_core::requests::validate(model, &original).map_err(|error| {
        let errors = match error {
            concierge_core::requests::Outcome::Errors(errors) => {
                concierge_core::request_errors::format_errors(model, &original, &errors, true)
            }
            _ => json!([]),
        };
        Box::new(
            (
                axum::http::StatusCode::UNPROCESSABLE_ENTITY,
                Json(json!({"detail":errors})),
            )
                .into_response(),
        )
    })
}
