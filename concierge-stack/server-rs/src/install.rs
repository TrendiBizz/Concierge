//! Assisted website-install requests and durable operator notifications.
use crate::{detail, owner, owner_validation, row_json, server_error, State};
use axum::{
    body::Bytes,
    extract::State as AxState,
    http::HeaderMap,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;
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
    match c.query("SELECT id,website,platform,contact_name,contact_phone,note,status,created_at,handled_at FROM install_requests WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 20",&[&u.tenant_id]).await {
        Ok(rows)=>Json(rows.iter().map(row_json).collect::<Vec<_>>()).into_response(),Err(_)=>server_error()
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
    let v = match owner_validation::parse(&bytes, &headers, "InstallRequest") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    let raw = |k: &str| v[k].as_str().unwrap();
    let clean = |k: &str, max: usize| {
        concierge_core::py_strip(raw(k))
            .chars()
            .take(max)
            .collect::<String>()
    };
    let website = clean("website", 300);
    let name = clean("contact_name", 120);
    let phone = clean("contact_phone", 40);
    let note = clean("note", 1000);
    let platform = raw("platform");
    let platform = if [
        "wordpress",
        "wix",
        "squarespace",
        "shopify",
        "webflow",
        "other",
        "unsure",
    ]
    .contains(&platform)
    {
        platform
    } else {
        "unsure"
    };
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    let row=match c.query_one("INSERT INTO install_requests(tenant_id,website,platform,contact_name,contact_phone,note) VALUES($1,$2,$3,$4,$5,$6) RETURNING id,created_at",&[&u.tenant_id,&website,&platform,&name,&phone,&note]).await {Ok(r)=>r,Err(_)=>return server_error()};
    let id: uuid::Uuid = row.get("id");
    // As in Python, a notification failure must not erase a recorded request.
    // Queue only: the separately gated outbox worker owns actual delivery.
    if let Ok(Some(tenant)) = c
        .query_opt("SELECT name,slug FROM tenants WHERE id=$1", &[&u.tenant_id])
        .await
    {
        let business: String = tenant.get("name");
        let slug: String = tenant.get("slug");
        let to=c.query_opt("SELECT coalesce(nullif(notify_email,''),'admin@trendibizz.com') FROM tenants WHERE slug='trendi-support'",&[]).await.ok().flatten().and_then(|r|r.get::<_,Option<String>>(0)).unwrap_or_else(||"admin@trendibizz.com".into());
        let contact = if raw("contact_name").is_empty() {
            "(none given)"
        } else {
            raw("contact_name")
        };
        let note = if raw("note").is_empty() {
            "(none)"
        } else {
            raw("note")
        };
        let body=format!("An install request came in.\n\nBusiness: {business} ({slug})\nWebsite:  {}\nPlatform: {platform}\nContact:  {contact} {}\nNote:     {note}\n\nInstall it for them, or reply to say what you need. When it is done, mark request {id} done:\nPOST /admin/install-requests/{id}/done\n",raw("website"),raw("contact_phone"));
        let subject = format!("Install request — {business}");
        let dedupe = format!("install-request:{id}");
        if let Err(e)=c.execute("INSERT INTO outbox(tenant_id,kind,channel,to_addr,subject,body,send_at,dedupe_key) VALUES($1,'owner_alert','email',$2,$3,$4,now(),$5) ON CONFLICT(dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING",&[&u.tenant_id,&to,&subject,&body,&dedupe]).await {eprintln!("install request {id} notification failed: {e}");}
    }
    let mut result = row_json(&row);
    result["status"] = json!("new");
    Json(result).into_response()
}
