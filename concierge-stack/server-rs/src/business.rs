//! Tenant settings and payment summaries scoped to the authenticated owner.
use crate::{detail, owner, owner_validation, row_json, server_error, State};
use axum::{
    body::Bytes,
    extract::State as AxState,
    http::HeaderMap,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Map, Value};
const FIELDS:&str="name,gst_number,nzbn,business_address,business_phone,quote_terms,quote_valid_days,allow_deposit,deposit_percent,invoice_payment_terms_days";
pub(crate) async fn get(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
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
        .query_one(
            &format!("SELECT {FIELDS} FROM tenants WHERE id=$1"),
            &[&u.tenant_id],
        )
        .await
    {
        Ok(r) => Json(row_json(&r)).into_response(),
        Err(_) => server_error(),
    }
}
pub(crate) async fn put(
    AxState(state): AxState<State>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let v = match owner_validation::parse(&bytes, &headers, "BusinessDetails") {
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
    let text = |k: &str| concierge_core::py_strip(v[k].as_str().unwrap());
    let days = v["quote_valid_days"].as_i64().unwrap() as i32;
    let deposit = v["deposit_percent"].as_i64().unwrap() as i32;
    let terms = v["invoice_payment_terms_days"].as_i64().unwrap() as i32;
    let allow = v["allow_deposit"].as_bool().unwrap();
    match c.query_one(&format!("UPDATE tenants SET name=$2,gst_number=$3,nzbn=$4,business_address=$5,business_phone=$6,quote_terms=$7,quote_valid_days=$8,allow_deposit=$9,deposit_percent=$10,invoice_payment_terms_days=$11 WHERE id=$1 RETURNING {FIELDS}"),&[&u.tenant_id,&text("name"),&text("gst_number"),&text("nzbn"),&text("business_address"),&text("business_phone"),&text("quote_terms"),&days,&allow,&deposit,&terms]).await{Ok(r)=>Json(row_json(&r)).into_response(),Err(_)=>server_error()}
}
pub(crate) async fn payment_get(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
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
    let tenant = match c
        .query_one(
            "SELECT payment_instructions,payment_url FROM tenants WHERE id=$1",
            &[&u.tenant_id],
        )
        .await
    {
        Ok(r) => r,
        Err(_) => return server_error(),
    };
    let r=match c.query_one("SELECT coalesce(sum(total_cents) FILTER (WHERE payment_status='paid'),0)::text,coalesce(sum(total_cents) FILTER (WHERE payment_status='declared'),0)::text,coalesce(sum(total_cents) FILTER (WHERE status='accepted' AND payment_status IN ('unpaid','declared')),0)::text,count(*) FILTER (WHERE payment_status='declared'),count(*) FILTER (WHERE payment_status='paid') FROM quotations WHERE tenant_id=$1",&[&u.tenant_id]).await{Ok(r)=>r,Err(_)=>return server_error()};
    let mut summary = Map::new();
    for (i, k) in ["paid_cents", "declared_cents", "outstanding_cents"]
        .iter()
        .enumerate()
    {
        let Ok(n) = serde_json::from_str::<Value>(&r.get::<_, String>(i)) else {
            return server_error();
        };
        summary.insert(k.to_string(), n);
    }
    summary.insert("declared_count".into(), json!(r.get::<_, i64>(3)));
    summary.insert("paid_count".into(), json!(r.get::<_, i64>(4)));
    Json(json!({"instructions":tenant.get::<_,Option<String>>(0).unwrap_or_default(),"url":tenant.get::<_,Option<String>>(1).unwrap_or_default(),"summary":summary})).into_response()
}
pub(crate) async fn payment_put(
    AxState(state): AxState<State>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let v = match owner_validation::parse(&bytes, &headers, "PaymentSettings") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    if u.role != "owner" {
        return detail(403, "Insufficient permissions");
    };
    let url = concierge_core::py_strip(v["url"].as_str().unwrap());
    if !url.is_empty()
        && !url.to_lowercase().starts_with("http://")
        && !url.to_lowercase().starts_with("https://")
    {
        return detail(422, "The payment link must start with http:// or https://");
    };
    let url: String = url.chars().take(500).collect();
    let instructions: String = concierge_core::py_strip(v["instructions"].as_str().unwrap())
        .chars()
        .take(2000)
        .collect();
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    match c
        .execute(
            "UPDATE tenants SET payment_instructions=$2,payment_url=$3 WHERE id=$1",
            &[&u.tenant_id, &instructions, &url],
        )
        .await
    {
        Ok(_) => Json(json!({"ok":true})).into_response(),
        Err(_) => server_error(),
    }
}
