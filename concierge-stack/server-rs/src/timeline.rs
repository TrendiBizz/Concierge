//! Unified history and the cross-channel human takeover switch.
use crate::{detail, owner, owner_validation, row_json, server_error, State};
use axum::{
    body::Bytes,
    extract::{Path, Query, State as AxState},
    http::HeaderMap,
    response::{IntoResponse, Response},
    Json,
};
use concierge_core::{py_strip, pydantic};
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap};
fn label(channel: &str) -> String {
    match channel {
        "email" => "Email".into(),
        "sms" => "SMS".into(),
        "phone" => "Phone".into(),
        "chat" => "Website chat".into(),
        _ => concierge_core::report::title(channel),
    }
}
pub(crate) async fn get(
    AxState(state): AxState<State>,
    Path(key): Path<String>,
    headers: HeaderMap,
    Query(q): Query<HashMap<String, String>>,
) -> Response {
    if let Some(r) = crate::unroutable(&key) {
        return r;
    };
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let limit = match q.get("limit") {
        None => 200,
        Some(s) => match pydantic::parse_int(&json!(s)) {
            Ok(n) => n.clamp(1, 500) as i64,
            Err(_) => return detail(422, "Limit is not valid."),
        },
    };
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    let case = match c
        .query_opt(
            "SELECT * FROM customer_cases WHERE tenant_id=$1 AND case_key=$2",
            &[&u.tenant_id, &key],
        )
        .await
    {
        Ok(Some(r)) => r,
        Ok(None) => return detail(404, "Contact not found"),
        Err(_) => return server_error(),
    };
    let cid: uuid::Uuid = case.get("id");
    let events=match c.query("SELECT e.channel,e.direction,e.body,e.occurred_at,e.answered_at FROM case_events e JOIN customer_cases c ON c.id=e.case_id WHERE c.tenant_id=$1 AND c.case_key=$2 ORDER BY e.occurred_at DESC,e.id DESC LIMIT $3",&[&u.tenant_id,&key,&limit]).await{Ok(r)=>r,Err(_)=>return server_error()};
    let leads=match c.query("SELECT id,status,channel,message,created_at FROM leads WHERE tenant_id=$1 AND case_id=$2 ORDER BY created_at DESC LIMIT 50",&[&u.tenant_id,&cid]).await{Ok(r)=>r,Err(_)=>return server_error()};
    let ids: Vec<uuid::Uuid> = leads.iter().map(|r| r.get(0)).collect();
    let appts=match c.query("SELECT starts_at,status,name FROM appointments WHERE tenant_id=$1 AND lead_id=ANY($2::uuid[]) ORDER BY starts_at DESC LIMIT 50",&[&u.tenant_id,&ids]).await{Ok(r)=>r,Err(_)=>return server_error()};
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    let event_data: Vec<Value> = events
        .iter()
        .map(|r| {
            let mut v = row_json(r);
            let channel = v["channel"]
                .as_str()
                .filter(|s| !s.is_empty())
                .unwrap_or("other");
            *counts.entry(channel.to_owned()).or_default() += 1;
            v["channel_label"] = json!(label(v["channel"].as_str().unwrap_or("")));
            v
        })
        .collect();
    let case = row_json(&case);
    let contact_label = ["display_name", "primary_phone", "primary_email", "case_key"]
        .iter()
        .find_map(|k| case[*k].as_str().filter(|s| !s.is_empty()))
        .unwrap_or("Unknown contact");
    let channels: Vec<_> = counts.keys().collect();
    let labels: Vec<_> = channels.iter().map(|c| label(c)).collect();
    Json(json!({"case_key":key,"label":contact_label,"phone":case["primary_phone"],"email":case["primary_email"],"automation_paused":case["automation_paused"],"takeover_at":case["takeover_at"],"event_count":events.len(),"by_channel":counts,"channels":channels,"labels":labels,"events":event_data,"enquiries":leads.iter().map(row_json).collect::<Vec<_>>(),"appointments":appts.iter().map(row_json).collect::<Vec<_>>()})).into_response()
}
async fn set(
    c: &tokio_postgres::Client,
    tid: uuid::Uuid,
    key: &str,
    paused: bool,
    by: &str,
) -> Result<bool, tokio_postgres::Error> {
    let by: String = by.chars().take(100).collect();
    c.execute("UPDATE customer_cases SET automation_paused=$3,takeover_at=CASE WHEN $3 THEN now() ELSE NULL END,takeover_by=CASE WHEN $3 THEN $4 ELSE '' END,updated_at=now() WHERE tenant_id=$1 AND case_key=$2",&[&tid,&key,&paused,&by]).await.map(|n|n==1)
}
pub(crate) async fn contact_takeover(
    AxState(state): AxState<State>,
    Path(key): Path<String>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    if let Some(r) = crate::unroutable(&key) {
        return r;
    };
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let v = match owner_validation::parse(&bytes, &headers, "ContactTakeover") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    let paused = v["paused"].as_bool().unwrap();
    let reason = v["reason"].as_str().unwrap();
    if paused && py_strip(reason).is_empty() {
        return detail(
            422,
            "Say why you are taking over; it is recorded for the customer's history",
        );
    };
    let by = format!(
        "{}: {reason}",
        if u.email.is_empty() {
            &u.role
        } else {
            &u.email
        }
    );
    let by = by.trim_matches([':', ' ']);
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    match set(&c, u.tenant_id, &key, paused, by).await {
        Ok(true) => Json(json!({"paused":paused,"case_key":key})).into_response(),
        Ok(false) => detail(404, "Contact not found"),
        Err(_) => server_error(),
    }
}
pub(crate) async fn lead_takeover(
    AxState(state): AxState<State>,
    Path(raw): Path<String>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    if let Some(r) = crate::unroutable(&raw) {
        return r;
    };
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let v = match owner_validation::parse(&bytes, &headers, "CaseTakeoverRequest") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    let paused = v["paused"].as_bool().unwrap();
    let id = match uuid::Uuid::parse_str(&raw) {
        Ok(id) => id,
        Err(_) => return server_error(),
    };
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    let cid: Option<uuid::Uuid> = match c
        .query_opt(
            "SELECT case_id FROM leads WHERE tenant_id=$1 AND id=$2",
            &[&u.tenant_id, &id],
        )
        .await
    {
        Ok(Some(r)) => r.get(0),
        Ok(None) => return detail(404, "Enquiry not found"),
        Err(_) => return server_error(),
    };
    let Some(cid) = cid else {
        return detail(
            409,
            "This enquiry has no conversation history to take over yet",
        );
    };
    let key: String = match c
        .query_opt(
            "SELECT case_key FROM customer_cases WHERE tenant_id=$1 AND id=$2",
            &[&u.tenant_id, &cid],
        )
        .await
    {
        Ok(Some(r)) => r.get(0),
        Ok(None) => return detail(404, "Customer case not found"),
        Err(_) => return server_error(),
    };
    let fallback = u.id.to_string();
    let by = if u.email.is_empty() {
        &fallback
    } else {
        &u.email
    };
    match set(&c, u.tenant_id, &key, paused, by).await {
        Ok(changed) => Json(json!({"lead_id":raw,"automation_paused":paused,"updated":changed}))
            .into_response(),
        Err(_) => server_error(),
    }
}
