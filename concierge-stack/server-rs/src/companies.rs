//! Tenant-scoped company catalogue; null parent explicitly removes nesting.
use crate::{detail, owner, owner_validation, row_json, server_error, State};
use axum::{
    body::Bytes,
    extract::{Path, State as AxState},
    http::HeaderMap,
    response::{IntoResponse, Response},
    Json,
};
use concierge_core::py_strip;
use serde_json::{json, Value};
fn edit(u: &owner::User) -> bool {
    matches!(u.role.as_str(), "owner" | "editor")
}
pub(crate) async fn listing(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
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
    let rows=c.query("SELECT c.id,c.name,c.domain,c.notes,c.parent_id,(SELECT count(*) FROM customer_cases k WHERE k.company_id=c.id) AS contacts,(SELECT count(*) FROM leads l JOIN customer_cases k ON l.case_id=k.id WHERE k.company_id=c.id AND l.status IN ('new','contacted','booked')) AS open_deals,(SELECT coalesce(sum(l.value_cents),0)::text FROM leads l JOIN customer_cases k ON l.case_id=k.id WHERE k.company_id=c.id AND l.status IN ('new','contacted','booked')) AS open_value_cents FROM companies c WHERE c.tenant_id=$1 ORDER BY c.name",&[&u.tenant_id]).await;
    match rows {
        Ok(rows) => Json(
            rows.iter()
                .map(|r| {
                    let mut v = row_json(r);
                    v["open_value_cents"] =
                        serde_json::from_str(v["open_value_cents"].as_str().unwrap()).unwrap();
                    v
                })
                .collect::<Vec<_>>(),
        )
        .into_response(),
        Err(_) => server_error(),
    }
}
pub(crate) async fn create(
    AxState(state): AxState<State>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let v = match owner_validation::parse(&bytes, &headers, "CompanyBody") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    if !edit(&u) {
        return detail(403, "Insufficient permissions");
    }
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    let name = py_strip(v["name"].as_str().unwrap());
    let domain = py_strip(v["domain"].as_str().unwrap());
    let notes = py_strip(v["notes"].as_str().unwrap());
    match c
        .query_one(
            "INSERT INTO companies (tenant_id,name,domain,notes) VALUES ($1,$2,$3,$4) RETURNING *",
            &[&u.tenant_id, &name, &domain, &notes],
        )
        .await
    {
        Ok(r) => (axum::http::StatusCode::CREATED, Json(row_json(&r))).into_response(),
        Err(_) => detail(409, "You already have a company with that name"),
    }
}
pub(crate) async fn update(
    AxState(state): AxState<State>,
    Path(raw): Path<String>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    if let Some(r) = crate::unroutable(&raw) {
        return r;
    }
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let v = match owner_validation::parse(&bytes, &headers, "CompanyUpdate") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    if !edit(&u) {
        return detail(403, "Insufficient permissions");
    }
    let sent: Value = serde_json::from_slice(&bytes).unwrap();
    let has = |k: &str| sent.get(k).is_some() && (!sent[k].is_null() || k == "parent_id");
    if !["name", "domain", "notes", "parent_id"]
        .iter()
        .any(|k| has(k))
    {
        return detail(400, "Nothing to update");
    }
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    let parent = if has("parent_id") {
        match v["parent_id"].as_str().filter(|s| !s.is_empty()) {
            None => None,
            Some(s) => {
                let id = match uuid::Uuid::parse_str(s) {
                    Ok(id) => id,
                    Err(_) => return detail(400, "Invalid company id"),
                };
                match c
                    .query_opt(
                        "SELECT 1 FROM companies WHERE id=$1 AND tenant_id=$2",
                        &[&id, &u.tenant_id],
                    )
                    .await
                {
                    Ok(Some(_)) => Some(id),
                    Ok(None) => return detail(404, "Unknown company"),
                    Err(_) => return server_error(),
                }
            }
        }
    } else {
        None
    };
    let id = match uuid::Uuid::parse_str(&raw) {
        Ok(id) => id,
        Err(_) => return server_error(),
    };
    let name = v["name"].as_str();
    let domain = v["domain"].as_str();
    let notes = v["notes"].as_str();
    match c.query_opt("UPDATE companies SET name=CASE WHEN $3 THEN $4 ELSE name END,domain=CASE WHEN $5 THEN $6 ELSE domain END,notes=CASE WHEN $7 THEN $8 ELSE notes END,parent_id=CASE WHEN $9 THEN $10 ELSE parent_id END,updated_at=now() WHERE id=$1 AND tenant_id=$2 RETURNING *",&[&id,&u.tenant_id,&has("name"),&name,&has("domain"),&domain,&has("notes"),&notes,&has("parent_id"),&parent]).await{Ok(Some(r))=>Json(row_json(&r)).into_response(),Ok(None)=>detail(404,"Unknown company"),Err(_)=>server_error()}
}
pub(crate) async fn delete(
    AxState(state): AxState<State>,
    Path(raw): Path<String>,
    headers: HeaderMap,
) -> Response {
    if let Some(r) = crate::unroutable(&raw) {
        return r;
    }
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    if u.role != "owner" {
        return detail(403, "Insufficient permissions");
    }
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
    match c
        .execute(
            "DELETE FROM companies WHERE id=$1 AND tenant_id=$2",
            &[&id, &u.tenant_id],
        )
        .await
    {
        Ok(0) => detail(404, "Unknown company"),
        Ok(_) => Json(json!({"deleted":true})).into_response(),
        Err(_) => server_error(),
    }
}
