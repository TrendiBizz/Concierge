//! Contact and enquiry assignment. Every referenced member/company is tenant-bound.
use crate::{detail, owner, owner_validation, server_error, State};
use axum::{
    body::Bytes,
    extract::{Path, State as AxState},
    http::HeaderMap,
    response::{IntoResponse, Response},
    Json,
};
use concierge_core::{py_strip, pyval::truncate_chars};
use serde_json::{json, Value};
use uuid::Uuid;
type Result<T> = std::result::Result<T, Box<Response>>;
fn fail(code: u16, msg: &str) -> Box<Response> {
    Box::new(detail(code, msg))
}
async fn member(c: &tokio_postgres::Client, tid: Uuid, raw: Option<&str>) -> Result<Option<Uuid>> {
    let Some(raw) = raw.filter(|r| !r.is_empty() && *r != "unassigned") else {
        return Ok(None);
    };
    let id = Uuid::parse_str(raw).map_err(|_| fail(400, "Invalid team member id"))?;
    match c
        .query_opt(
            "SELECT 1 FROM tenant_users WHERE id=$1 AND tenant_id=$2 AND active",
            &[&id, &tid],
        )
        .await
    {
        Ok(Some(_)) => Ok(Some(id)),
        Ok(None) => Err(fail(404, "That person is not on your team")),
        Err(_) => Err(Box::new(server_error())),
    }
}
async fn company(c: &tokio_postgres::Client, tid: Uuid, raw: Option<&str>) -> Result<Option<Uuid>> {
    let Some(raw) = raw.filter(|r| !r.is_empty()) else {
        return Ok(None);
    };
    let id = Uuid::parse_str(raw).map_err(|_| fail(400, "Invalid company id"))?;
    match c
        .query_opt(
            "SELECT 1 FROM companies WHERE id=$1 AND tenant_id=$2",
            &[&id, &tid],
        )
        .await
    {
        Ok(Some(_)) => Ok(Some(id)),
        Ok(None) => Err(fail(404, "Unknown company")),
        Err(_) => Err(Box::new(server_error())),
    }
}
fn can_edit(u: &owner::User) -> bool {
    matches!(u.role.as_str(), "owner" | "editor")
}
fn key(s: &str) -> String {
    truncate_chars(&py_strip(s).to_lowercase(), 200)
}
pub(crate) async fn contact_company(
    AxState(state): AxState<State>,
    Path(raw): Path<String>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    single(state, raw, headers, bytes, Kind::Company).await
}
pub(crate) async fn contact_assignee(
    AxState(state): AxState<State>,
    Path(raw): Path<String>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    single(state, raw, headers, bytes, Kind::Contact).await
}
pub(crate) async fn lead_assignee(
    AxState(state): AxState<State>,
    Path(raw): Path<String>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    single(state, raw, headers, bytes, Kind::Lead).await
}
enum Kind {
    Company,
    Contact,
    Lead,
}
async fn single(
    state: State,
    raw: String,
    headers: HeaderMap,
    bytes: Bytes,
    kind: Kind,
) -> Response {
    if let Some(r) = crate::unroutable(&raw) {
        return r;
    }
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let v = if matches!(kind, Kind::Company) {
        match serde_json::from_slice::<Value>(&bytes) {
            Ok(v) if v.is_object() => v,
            _ => return detail(422, "Value is not valid."),
        }
    } else {
        match owner_validation::parse(&bytes, &headers, "Assignee") {
            Ok(v) => v,
            Err(e) => return detail(422, &e),
        }
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
    let target = if matches!(kind, Kind::Company) {
        if v.get("company_id")
            .is_some_and(|v| !v.is_null() && v != false && v != 0 && v != "")
            && !v["company_id"].is_string()
        {
            return detail(400, "Invalid company id");
        }
        company(&c, u.tenant_id, v["company_id"].as_str()).await
    } else {
        member(&c, u.tenant_id, v["user_id"].as_str()).await
    };
    let target = match target {
        Ok(t) => t,
        Err(r) => return *r,
    };
    match kind {
        Kind::Company | Kind::Contact => {
            let company = matches!(kind, Kind::Company);
            let col = if company { "company_id" } else { "assigned_to" };
            let sql=format!("UPDATE customer_cases SET {col}=$3,updated_at=now() WHERE tenant_id=$1 AND case_key=$2 RETURNING case_key");
            match c
                .query_opt(&sql, &[&u.tenant_id, &key(&raw), &target])
                .await
            {
                Ok(Some(r)) => {
                    let mut v = json!({"case_key":r.get::<_,String>(0)});
                    v[col] = json!(target);
                    Json(v).into_response()
                }
                Ok(None) => detail(404, "Unknown contact"),
                Err(_) => server_error(),
            }
        }
        Kind::Lead => {
            let id = match Uuid::parse_str(&raw) {
                Ok(id) => id,
                Err(_) => return detail(404, "Enquiry not found"),
            };
            match c.query_opt("UPDATE leads SET assigned_to=$3,updated_at=now() WHERE id=$1 AND tenant_id=$2 RETURNING id,assigned_to",&[&id,&u.tenant_id,&target]).await{Ok(Some(r))=>Json(json!({"id":r.get::<_,Uuid>(0),"assigned_to":r.get::<_,Option<Uuid>>(1)})).into_response(),_=>detail(404,"Enquiry not found")}
        }
    }
}
pub(crate) async fn bulk(
    AxState(state): AxState<State>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let v = match owner_validation::parse(&bytes, &headers, "BulkAssign") {
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
    let target = match member(&c, u.tenant_id, v["user_id"].as_str()).await {
        Ok(t) => t,
        Err(r) => return *r,
    };
    let keys: Vec<_> = v["case_keys"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(Value::as_str)
        .filter(|s| !py_strip(s).is_empty())
        .map(key)
        .collect();
    match c.query("UPDATE customer_cases SET assigned_to=$3,updated_at=now() WHERE tenant_id=$1 AND case_key=ANY($2::text[]) RETURNING case_key",&[&u.tenant_id,&keys,&target]).await{Ok(rows)=>Json(json!({"updated":rows.len(),"assigned_to":target,"case_keys":rows.iter().map(|r|r.get::<_,String>(0)).collect::<Vec<_>>()})).into_response(),Err(_)=>server_error()}
}
