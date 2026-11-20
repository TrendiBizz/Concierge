//! Tenant-owned customer exports and webhook configuration. Delivery is a separate worker.
use crate::{detail, owner, owner_validation, row_json, server_error, State};
use axum::{
    body::Bytes,
    extract::{Query, State as AxState},
    http::{header, HeaderMap},
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use std::collections::HashMap;
fn csv(cells: &[&str]) -> String {
    cells
        .iter()
        .map(|s| {
            if s.contains([',', '"', '\r', '\n']) {
                format!("\"{}\"", s.replace('"', "\"\""))
            } else {
                s.to_string()
            }
        })
        .collect::<Vec<_>>()
        .join(",")
        + "\r\n"
}
pub(crate) async fn export(
    AxState(state): AxState<State>,
    headers: HeaderMap,
    Query(q): Query<HashMap<String, String>>,
) -> Response {
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let format = q.get("format").map(String::as_str).unwrap_or("json");
    if !["json", "csv"].contains(&format) {
        return detail(422, "Format is not valid.");
    };
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    let rows=match c.query("SELECT c.case_key,c.display_name,c.primary_phone,c.primary_email,c.updated_at,COALESCE((SELECT string_agg(DISTINCT e.channel,'|') FROM case_events e WHERE e.case_id=c.id),'') AS channels,COALESCE((SELECT string_agg(a.kind||':'||a.value,'|' ORDER BY a.kind,a.value) FROM customer_addresses a WHERE a.case_id=c.id),'') AS addresses FROM customer_cases c WHERE c.tenant_id=$1 ORDER BY c.display_name,c.created_at",&[&u.tenant_id]).await{Ok(r)=>r,Err(_)=>return server_error()};
    let contacts: Vec<Value> = rows
        .iter()
        .map(|r| {
            let mut v = row_json(r);
            for k in ["channels", "addresses"] {
                v[k] = json!(v[k]
                    .as_str()
                    .unwrap_or("")
                    .split('|')
                    .filter(|s| !s.is_empty())
                    .collect::<Vec<_>>());
            }
            let time = v.as_object_mut().unwrap().remove("updated_at").unwrap();
            v["last_seen"] = time;
            v
        })
        .collect();
    if format == "json" {
        return Json(json!({"count":contacts.len(),"contacts":contacts})).into_response();
    };
    let mut out = csv(&[
        "customer",
        "case_key",
        "kind",
        "address",
        "channels",
        "last_seen",
    ]);
    for v in &contacts {
        let key = v["case_key"].as_str().unwrap_or("");
        let name = v["display_name"]
            .as_str()
            .filter(|s| !s.is_empty())
            .unwrap_or(key);
        let channels = v["channels"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(Value::as_str)
            .collect::<Vec<_>>()
            .join("|");
        let seen = v["last_seen"].as_str().unwrap_or("");
        let addresses = v["addresses"].as_array().unwrap();
        if addresses.is_empty() {
            out.push_str(&csv(&[name, key, "", "", &channels, seen]));
        } else {
            for a in addresses {
                let (kind, value) = a
                    .as_str()
                    .unwrap()
                    .split_once(':')
                    .unwrap_or((a.as_str().unwrap(), ""));
                out.push_str(&csv(&[name, key, kind, value, &channels, seen]));
            }
        }
    }
    (
        [
            (header::CONTENT_TYPE, "text/csv; charset=utf-8"),
            (
                header::CONTENT_DISPOSITION,
                "attachment; filename=\"customers.csv\"",
            ),
        ],
        out,
    )
        .into_response()
}
pub(crate) async fn webhook_get(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
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
    match c
        .query_opt(
            "SELECT url,active,created_at FROM tenant_webhooks WHERE tenant_id=$1",
            &[&u.tenant_id],
        )
        .await
    {
        Ok(r) => Json(json!({"webhook":r.as_ref().map(row_json)})).into_response(),
        Err(_) => server_error(),
    }
}
pub(crate) async fn webhook_set(
    AxState(state): AxState<State>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let v = match owner_validation::parse(&bytes, &headers, "WebhookIn") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    if u.role != "owner" {
        return detail(403, "Insufficient permissions");
    };
    let raw = v["url"].as_str().unwrap();
    if !raw.starts_with("https://") {
        return detail(400, "Use an https address for your CRM endpoint");
    };
    let url = concierge_core::py_strip(raw);
    let secret = v["secret"].as_str().unwrap();
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    match c.execute("INSERT INTO tenant_webhooks(tenant_id,url,secret,active) VALUES($1,$2,$3,true) ON CONFLICT(tenant_id) DO UPDATE SET url=$2,secret=$3,active=true",&[&u.tenant_id,&url,&secret]).await{Ok(_)=>Json(json!({"url":url,"active":true})).into_response(),Err(_)=>server_error()}
}
pub(crate) async fn webhook_delete(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    if u.role != "owner" {
        return detail(403, "Insufficient permissions");
    };
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    match c
        .execute(
            "DELETE FROM tenant_webhooks WHERE tenant_id=$1",
            &[&u.tenant_id],
        )
        .await
    {
        Ok(_) => Json(json!({"removed":true})).into_response(),
        Err(_) => server_error(),
    }
}
