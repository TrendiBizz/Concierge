//! Owner task mutations use tenant predicates in the write itself.
use crate::{detail, owner, owner_validation, row_json, server_error, State};
use axum::{
    body::Bytes,
    extract::{Path, Query, State as AxState},
    http::HeaderMap,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use std::collections::HashMap;
fn can_edit(u: &owner::User) -> bool {
    matches!(u.role.as_str(), "owner" | "editor")
}
fn id(raw: &str) -> Result<i64, &'static str> {
    raw.parse().map_err(|_| "Task id is not valid.")
}
fn date(v: &Value) -> Option<chrono::DateTime<chrono::Utc>> {
    v.as_str()
        .and_then(|s| chrono::DateTime::parse_from_rfc3339(s).ok())
        .map(|d| d.with_timezone(&chrono::Utc))
}
pub(crate) async fn listing(
    AxState(state): AxState<State>,
    headers: HeaderMap,
    Query(q): Query<HashMap<String, String>>,
) -> Response {
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let status = q.get("status").map(String::as_str).unwrap_or("open");
    if !["open", "done", "all"].contains(&status) {
        return detail(422, "Status is not valid.");
    }
    if !matches!(u.role.as_str(), "owner" | "editor" | "viewer") {
        return detail(403, "Insufficient permissions");
    }
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    let order = if status == "open" {
        "t.due_at NULLS LAST,t.created_at"
    } else {
        "COALESCE(t.completed_at,t.created_at) DESC"
    };
    let sql=format!("SELECT t.*,l.name AS lead_name,l.score_label AS lead_label FROM tasks t LEFT JOIN leads l ON l.id=t.lead_id WHERE t.tenant_id=$1 AND ($2='all' OR t.status=$2) ORDER BY {order} LIMIT 200");
    match c.query(&sql, &[&u.tenant_id, &status]).await {
        Ok(rows) => Json(rows.iter().map(row_json).collect::<Vec<_>>()).into_response(),
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
    let v = match owner_validation::parse(&bytes, &headers, "TaskCreate") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    if !can_edit(&u) {
        return detail(403, "Insufficient permissions");
    }
    let title = concierge_core::py_strip(v["title"].as_str().unwrap());
    if title.is_empty() {
        return detail(400, "A to-do needs a title");
    }
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    let lead = match v["lead_id"].as_str().filter(|s| !s.is_empty()) {
        None => None,
        Some(raw) => match uuid::Uuid::parse_str(raw) {
            Ok(id) => Some(id),
            Err(_) => return detail(400, "Invalid lead id"),
        },
    };
    if let Some(lead) = lead {
        match c
            .query_opt(
                "SELECT 1 FROM leads WHERE id=$1 AND tenant_id=$2",
                &[&lead, &u.tenant_id],
            )
            .await
        {
            Ok(Some(_)) => (),
            Ok(None) => return detail(404, "Unknown lead"),
            Err(_) => return server_error(),
        }
    }
    let due = date(&v["due_at"]);
    let notes = v["notes"].as_str().unwrap_or("");
    match c.query_one("INSERT INTO tasks (tenant_id,lead_id,title,notes,due_at,kind,source) VALUES ($1,$2,$3,$4,$5,'manual','manual') RETURNING *",&[&u.tenant_id,&lead,&title,&notes,&due]).await {Ok(r)=>(axum::http::StatusCode::CREATED,Json(row_json(&r))).into_response(),Err(_)=>server_error()}
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
    let id = match id(&raw) {
        Ok(i) => i,
        Err(r) => return detail(422, r),
    };
    let v = match owner_validation::parse(&bytes, &headers, "TaskUpdate") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    if !can_edit(&u) {
        return detail(403, "Insufficient permissions");
    }
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    match c
        .query_opt(
            "SELECT 1 FROM tasks WHERE id=$1 AND tenant_id=$2",
            &[&id, &u.tenant_id],
        )
        .await
    {
        Ok(Some(_)) => (),
        Ok(None) => return detail(404, "Unknown to-do"),
        Err(_) => return server_error(),
    }
    let raw_body: Value = serde_json::from_slice(&bytes).unwrap();
    let has = |k: &str| raw_body.get(k).is_some();
    if !["title", "notes", "due_at", "status"]
        .iter()
        .any(|k| has(k))
    {
        return detail(400, "Nothing to update");
    }
    let title = v["title"].as_str().map(concierge_core::py_strip);
    if has("title") && title.is_none_or(str::is_empty) {
        return detail(400, "A to-do needs a title");
    }
    let status = v["status"].as_str();
    if has("status") && status.is_none() {
        return detail(400, "status must be open or done");
    }
    let notes = v["notes"].as_str();
    let due = date(&v["due_at"]);
    match c.query_opt("UPDATE tasks SET title=CASE WHEN $3 THEN $4 ELSE title END,notes=CASE WHEN $5 THEN $6 ELSE notes END,due_at=CASE WHEN $7 THEN $8 ELSE due_at END,status=CASE WHEN $9 THEN $10 ELSE status END,completed_at=CASE WHEN $9 THEN CASE WHEN $10='done' THEN now() ELSE NULL END ELSE completed_at END WHERE id=$1 AND tenant_id=$2 RETURNING *",&[&id,&u.tenant_id,&has("title"),&title,&has("notes"),&notes,&has("due_at"),&due,&has("status"),&status]).await{Ok(Some(r))=>Json(row_json(&r)).into_response(),Ok(None)=>detail(404,"Unknown to-do"),Err(_)=>server_error()}
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
    let id = match id(&raw) {
        Ok(i) => i,
        Err(r) => return detail(422, r),
    };
    if !can_edit(&u) {
        return detail(403, "Insufficient permissions");
    }
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    match c
        .execute(
            "DELETE FROM tasks WHERE id=$1 AND tenant_id=$2",
            &[&id, &u.tenant_id],
        )
        .await
    {
        Ok(0) => detail(404, "Unknown to-do"),
        Ok(_) => Json(json!({"deleted":true})).into_response(),
        Err(_) => server_error(),
    }
}
