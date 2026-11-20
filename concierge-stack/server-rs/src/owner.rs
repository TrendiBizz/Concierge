//! Owner read routes. The stored Python session hashes remain the credential;
//! tenant scope is obtained only from the authenticated database join.
use crate::{detail, iso, server_error, State};
use axum::extract::{Query, State as AxState};
use axum::http::HeaderMap;
use axum::response::{IntoResponse, Response};
use axum::Json;
use chrono::{DateTime, Duration, Utc};
use concierge_core::{owner_auth, pydantic, revenue};
use serde_json::json;
use std::collections::HashMap;
use tokio_postgres::GenericClient;

pub(crate) struct User {
    pub(crate) tenant_id: uuid::Uuid,
    pub(crate) email: String,
    pub(crate) role: String,
    slug: String,
}

pub(crate) enum OwnerError {
    Authentication(&'static str),
    Database,
}

impl OwnerError {
    pub(crate) fn response(self) -> Response {
        match self {
            Self::Authentication(message) => detail(401, message),
            Self::Database => server_error(),
        }
    }
}

/// Match Python's partition(" "): do not trim or accept a tab separator.
fn bearer(headers: &HeaderMap) -> Result<&str, OwnerError> {
    let raw = headers
        .get("authorization")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    let (scheme, token) = raw.split_once(' ').unwrap_or((raw, ""));
    if !scheme.eq_ignore_ascii_case("bearer") || token.is_empty() || token.chars().count() > 256 {
        return Err(OwnerError::Authentication("Bearer authentication required"));
    }
    Ok(token)
}

pub(crate) async fn current_user(state: &State, headers: &HeaderMap) -> Result<User, OwnerError> {
    let token = bearer(headers)?;
    let pool = state.0.pool.as_ref().ok_or(OwnerError::Database)?;
    let client = pool.get().await.map_err(|_| OwnerError::Database)?;
    let row = client
        .query_opt(
            "SELECT u.tenant_id,u.email,u.role,t.slug FROM tenant_sessions s \
         JOIN tenant_users u ON u.id=s.user_id JOIN tenants t ON t.id=u.tenant_id \
         WHERE s.token_hash=$1 AND s.expires_at>now() AND u.active",
            &[&owner_auth::digest(token)],
        )
        .await
        .map_err(|_| OwnerError::Database)?
        .ok_or(OwnerError::Authentication("Session expired or invalid"))?;
    Ok(User {
        tenant_id: row.get(0),
        email: row.get(1),
        role: row.get(2),
        slug: row.get(3),
    })
}

pub(crate) async fn me(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    match current_user(&state, &headers).await {
        Ok(user) => Json(json!({"email": user.email, "role": user.role, "tenant": user.slug}))
            .into_response(),
        Err(error) => error.response(),
    }
}

async fn period<C: GenericClient + Sync>(
    client: &C,
    tenant: uuid::Uuid,
    start: DateTime<Utc>,
    end: DateTime<Utc>,
) -> Result<revenue::Period, tokio_postgres::Error> {
    let leads = client.query(
        "SELECT channel,count(*) AS n FROM leads WHERE tenant_id=$1 AND created_at >= $2 AND created_at < $3 GROUP BY channel",
        &[&tenant, &start, &end],
    ).await?;
    let row = client.query_one(
        "SELECT count(*) FILTER (WHERE sent_at IS NOT NULL), \
         count(*) FILTER (WHERE status='accepted'), \
         COALESCE(SUM(total_cents) FILTER (WHERE status='accepted'),0)::bigint, \
         COALESCE(SUM(total_cents) FILTER (WHERE payment_confirmed_at IS NOT NULL AND payment_status='paid'),0)::bigint, \
         COALESCE(SUM(total_cents) FILTER (WHERE status='accepted' AND payment_status IN ('unpaid','declared')),0)::bigint, \
         max(currency) FROM quotations WHERE tenant_id=$1 AND created_at >= $2 AND created_at < $3",
        &[&tenant, &start, &end],
    ).await?;
    let by_channel = leads
        .iter()
        .map(|r| (r.get::<_, String>(0), r.get::<_, i64>(1)))
        .collect::<std::collections::BTreeMap<_, _>>();
    Ok(revenue::Period {
        enquiries: by_channel.values().sum(),
        by_channel,
        quotes_sent: row.get(0),
        quotes_accepted: row.get(1),
        accepted_cents: row.get(2),
        paid_cents: row.get(3),
        outstanding_cents: row.get(4),
        currency: row.get::<_, Option<String>>(5).unwrap_or_default(),
    })
}

pub(crate) async fn revenue_report(
    AxState(state): AxState<State>,
    Query(query): Query<HashMap<String, String>>,
    headers: HeaderMap,
) -> Response {
    // FastAPI resolves the session dependency before reporting query-validation
    // errors; invalid credentials cannot be used to probe report validation.
    let user = match current_user(&state, &headers).await {
        Ok(u) => u,
        Err(error) => return error.response(),
    };
    let days = match query.get("days") {
        None => 30,
        Some(raw) => match pydantic::parse_int(&json!(raw)) {
            Ok(days) => revenue::clamp_days(days),
            Err(_) => return detail(422, "Days is not valid."),
        },
    };
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(client) = pool.get().await else {
        return server_error();
    };
    let now = Utc::now();
    let start = now - Duration::days(days);
    let current = match period(&**client, user.tenant_id, start, now).await {
        Ok(p) => p,
        Err(_) => return server_error(),
    };
    let previous = match period(
        &**client,
        user.tenant_id,
        start - Duration::days(days),
        start,
    )
    .await
    {
        Ok(p) => p,
        Err(_) => return server_error(),
    };
    let mut result = revenue::build(&current, &previous);
    result["days"] = json!(days);
    result["since"] = json!(iso(start));
    result["note"] = json!(revenue::NOTE);
    Json(result).into_response()
}

/// Only the authenticated session is revoked; other devices remain signed in.
pub(crate) async fn logout(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    if let Err(error) = current_user(&state, &headers).await {
        return error.response();
    }
    let token = match bearer(&headers) {
        Ok(t) => t,
        Err(e) => return e.response(),
    };
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(client) = pool.get().await else {
        return server_error();
    };
    match client
        .execute(
            "DELETE FROM tenant_sessions WHERE token_hash=$1",
            &[&owner_auth::digest(token)],
        )
        .await
    {
        Ok(_) => Json(json!({"ok": true})).into_response(),
        Err(_) => server_error(),
    }
}
