//! Unified contact list and identity addresses. Addresses cannot be stolen across cases.
use crate::{detail, owner, owner_validation, row_json, server_error, State};
use axum::{
    body::Bytes,
    extract::{Path, Query, State as AxState},
    http::HeaderMap,
    response::{IntoResponse, Response},
    Json,
};
use concierge_core::{contact, py_strip, pydantic};
use serde_json::{json, Value};
use std::collections::HashMap;
use uuid::Uuid;
pub(crate) async fn listing(
    AxState(state): AxState<State>,
    headers: HeaderMap,
    Query(q): Query<HashMap<String, String>>,
) -> Response {
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let limit = match q.get("limit") {
        None => 50,
        Some(s) => match pydantic::parse_int(&json!(s)) {
            Ok(n) => n.clamp(1, 200) as i64,
            Err(_) => return detail(422, "Limit is not valid."),
        },
    };
    let search = py_strip(q.get("q").map(String::as_str).unwrap_or(""));
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    let rows=match c.query("SELECT c.case_key,c.display_name,c.company,c.primary_phone,c.primary_email,c.assigned_to,c.company_id,(SELECT u.email FROM tenant_users u WHERE u.id=c.assigned_to) AS assignee_email,(SELECT co.name FROM companies co WHERE co.id=c.company_id) AS company_name,c.automation_paused,c.takeover_at,c.updated_at,(SELECT count(*) FROM case_events e WHERE e.case_id=c.id) AS event_count,(SELECT string_agg(DISTINCT e.channel,',') FROM case_events e WHERE e.case_id=c.id) AS channels,(SELECT max(e.occurred_at) FROM case_events e WHERE e.case_id=c.id) AS last_at FROM customer_cases c WHERE c.tenant_id=$1 AND ($2='' OR c.display_name ILIKE '%'||$2||'%' OR c.primary_phone LIKE '%'||$2||'%' OR c.primary_email ILIKE '%'||$2||'%') ORDER BY COALESCE((SELECT max(e.occurred_at) FROM case_events e WHERE e.case_id=c.id),c.updated_at) DESC LIMIT $3",&[&u.tenant_id,&search,&limit]).await{Ok(r)=>r,Err(_)=>return server_error()};
    let items: Vec<Value> = rows
        .iter()
        .map(|r| {
            let mut v = row_json(r);
            let mut channels: Vec<_> = v["channels"]
                .as_str()
                .unwrap_or("")
                .split(',')
                .filter(|s| !s.is_empty())
                .map(str::to_owned)
                .collect();
            channels.sort();
            v["channels"] = json!(channels);
            let label = ["display_name", "primary_phone", "primary_email", "case_key"]
                .iter()
                .find_map(|k| v[*k].as_str().filter(|s| !s.is_empty()))
                .unwrap_or("Unknown contact")
                .to_owned();
            v["label"] = json!(label);
            v
        })
        .collect();
    Json(json!({"count":items.len(),"contacts":items})).into_response()
}
type Result<T> = std::result::Result<T, Box<Response>>;
async fn case(c: &tokio_postgres::Client, tid: Uuid, key: &str) -> Result<Uuid> {
    match c
        .query_opt(
            "SELECT id FROM customer_cases WHERE tenant_id=$1 AND case_key=$2",
            &[&tid, &key],
        )
        .await
    {
        Ok(Some(r)) => Ok(r.get(0)),
        Ok(None) => Err(Box::new(detail(404, "Customer not found"))),
        Err(_) => Err(Box::new(server_error())),
    }
}
pub(crate) async fn addresses(
    AxState(state): AxState<State>,
    Path(key): Path<String>,
    headers: HeaderMap,
) -> Response {
    if let Some(r) = crate::unroutable(&key) {
        return r;
    };
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    let cid = match case(&c, u.tenant_id, &key).await {
        Ok(id) => id,
        Err(r) => return *r,
    };
    match c.query("SELECT id,kind,value,label,source,created_at FROM customer_addresses WHERE tenant_id=$1 AND case_id=$2 ORDER BY kind,created_at",&[&u.tenant_id,&cid]).await{Ok(rows)=>Json(json!({"addresses":rows.iter().map(row_json).collect::<Vec<_>>()})).into_response(),Err(_)=>server_error()}
}
pub(crate) async fn add(
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
    let v = match owner_validation::parse(&bytes, &headers, "AddressIn") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    if !matches!(u.role.as_str(), "owner" | "editor") {
        return detail(403, "Insufficient permissions");
    };
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    let cid = match case(&c, u.tenant_id, &key).await {
        Ok(id) => id,
        Err(r) => return *r,
    };
    let kind = v["kind"].as_str().unwrap();
    let raw = v["value"].as_str().unwrap();
    let value = if kind == "phone" {
        let r = match c
            .query_one(
                "SELECT default_country_code FROM tenants WHERE id=$1",
                &[&u.tenant_id],
            )
            .await
        {
            Ok(r) => r,
            Err(_) => return server_error(),
        };
        let own = r.get::<_, Option<String>>(0).unwrap_or_default();
        let own = py_strip(&own);
        let valid =
            |s: &str| (1..=3).contains(&s.chars().count()) && s.chars().all(|c| c.is_numeric());
        let configured = py_strip(&state.0.config.default_country_code);
        let cc = if valid(own) {
            own
        } else if valid(configured) {
            configured
        } else {
            ""
        };
        match contact::normalize_phone(raw, cc) {
            Some(s) if !s.is_empty() => s,
            _ => return detail(400, "Enter a phone number we can call or text"),
        }
    } else {
        let s = py_strip(raw).to_lowercase();
        if s.is_empty() || !contact::is_email(&s) {
            return detail(400, "Enter a valid email address");
        };
        s
    };
    let value: String = value.chars().take(200).collect();
    let label = v["label"].as_str().unwrap();
    match c.query_opt("INSERT INTO customer_addresses (tenant_id,case_id,kind,value,label,source) VALUES($1,$2,$3,$4,$5,'owner') ON CONFLICT (tenant_id,kind,value) DO UPDATE SET label=coalesce(nullif(EXCLUDED.label,''),customer_addresses.label) WHERE customer_addresses.case_id=EXCLUDED.case_id RETURNING id,kind,value,label,source,created_at",&[&u.tenant_id,&cid,&kind,&value,&label]).await{Ok(Some(r))=>(axum::http::StatusCode::CREATED,Json(row_json(&r))).into_response(),Ok(None)=>detail(400,"That address already belongs to another customer"),Err(_)=>server_error()}
}
pub(crate) async fn remove(
    AxState(state): AxState<State>,
    Path((key, raw)): Path<(String, String)>,
    headers: HeaderMap,
) -> Response {
    if let Some(r) = crate::unroutable(&key).or_else(|| crate::unroutable(&raw)) {
        return r;
    };
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let id = match raw.parse::<i64>() {
        Ok(n) => n,
        Err(_) => return detail(422, "Address id is not valid."),
    };
    if !matches!(u.role.as_str(), "owner" | "editor") {
        return detail(403, "Insufficient permissions");
    };
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(mut c) = pool.get().await else {
        return server_error();
    };
    let cid = match case(&c, u.tenant_id, &key).await {
        Ok(id) => id,
        Err(r) => return *r,
    };
    let Ok(tx) = c.transaction().await else {
        return server_error();
    };
    // Serialize removals for this contact so simultaneous deletes cannot remove its last identity.
    if tx
        .query_one(
            "SELECT id FROM customer_cases WHERE tenant_id=$1 AND id=$2 FOR UPDATE",
            &[&u.tenant_id, &cid],
        )
        .await
        .is_err()
    {
        return server_error();
    };
    let count = match tx
        .query_one(
            "SELECT count(*) FROM customer_addresses WHERE tenant_id=$1 AND case_id=$2",
            &[&u.tenant_id, &cid],
        )
        .await
    {
        Ok(r) => r.get::<_, i64>(0),
        Err(_) => return server_error(),
    };
    if count <= 1 {
        return detail(400, "A customer needs at least one address");
    };
    match tx
        .execute(
            "DELETE FROM customer_addresses WHERE tenant_id=$1 AND case_id=$2 AND id=$3",
            &[&u.tenant_id, &cid, &id],
        )
        .await
    {
        Ok(0) => detail(404, "Address not found"),
        Ok(_) => match tx.commit().await {
            Ok(_) => Json(json!({"removed":true})).into_response(),
            Err(_) => server_error(),
        },
        Err(_) => server_error(),
    }
}
