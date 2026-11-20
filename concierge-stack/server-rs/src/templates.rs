//! Saved replies retain leading body whitespace and trim only its right edge.
use crate::{detail, owner, owner_validation, row_json, server_error, State};
use axum::{
    body::Bytes,
    extract::{Path, State as AxState},
    http::HeaderMap,
    response::{IntoResponse, Response},
    Json,
};
use concierge_core::py_strip;
use serde_json::json;
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
    match c.query("SELECT id,name,subject,body,updated_at FROM email_templates WHERE tenant_id=$1 ORDER BY name",&[&u.tenant_id]).await{Ok(rows)=>Json(rows.iter().map(row_json).collect::<Vec<_>>()).into_response(),Err(_)=>server_error()}
}
pub(crate) async fn create(
    AxState(state): AxState<State>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    save(state, headers, bytes, None).await
}
pub(crate) async fn update(
    AxState(state): AxState<State>,
    Path(id): Path<String>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    if let Some(r) = crate::unroutable(&id) {
        return r;
    }
    save(state, headers, bytes, Some(id)).await
}
async fn save(state: State, headers: HeaderMap, bytes: Bytes, raw: Option<String>) -> Response {
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let v = match owner_validation::parse(&bytes, &headers, "TemplateBody") {
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
    let subject = py_strip(v["subject"].as_str().unwrap());
    let body = v["body"]
        .as_str()
        .unwrap()
        .trim_end_matches(|c: char| py_strip(&c.to_string()).is_empty());
    let result = if let Some(raw) = raw.as_deref() {
        let id = match uuid::Uuid::parse_str(raw) {
            Ok(id) => id,
            Err(_) => return detail(409, "You already have a saved reply with that name"),
        };
        c.query_opt("UPDATE email_templates SET name=$3,subject=$4,body=$5,updated_at=now() WHERE id=$1 AND tenant_id=$2 RETURNING *",&[&id,&u.tenant_id,&name,&subject,&body]).await
    } else {
        c.query_opt("INSERT INTO email_templates (tenant_id,name,subject,body) VALUES ($1,$2,$3,$4) RETURNING *",&[&u.tenant_id,&name,&subject,&body]).await
    };
    match result {
        Ok(Some(r)) => (
            if raw.is_some() {
                axum::http::StatusCode::OK
            } else {
                axum::http::StatusCode::CREATED
            },
            Json(row_json(&r)),
        )
            .into_response(),
        Ok(None) => detail(404, "Unknown saved reply"),
        Err(_) => detail(409, "You already have a saved reply with that name"),
    }
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
    if !edit(&u) {
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
            "DELETE FROM email_templates WHERE id=$1 AND tenant_id=$2",
            &[&id, &u.tenant_id],
        )
        .await
    {
        Ok(0) => detail(404, "Unknown saved reply"),
        Ok(_) => Json(json!({"deleted":true})).into_response(),
        Err(_) => server_error(),
    }
}
