//! Credential exchanges. Transactions serialize invitation consumption and keep
//! user activation, invitation use and session creation atomic.
use crate::{detail, owner_validation, server_error, State};
use axum::{
    body::Bytes,
    extract::{ConnectInfo, State as AxState},
    http::HeaderMap,
    response::{IntoResponse, Response},
    Extension, Json,
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use chrono::{DateTime, Utc};
use concierge_core::owner_auth;
use rand::RngCore;
use serde_json::{json, Value};
use std::net::SocketAddr;
use tokio_postgres::GenericClient;

fn token() -> String {
    let mut bytes = [0u8; 32];
    rand::rngs::OsRng.fill_bytes(&mut bytes);
    URL_SAFE_NO_PAD.encode(bytes)
}

async fn allow<C: GenericClient + Sync>(
    client: &C,
    ip: &str,
    slug: &str,
    email: &str,
) -> Result<bool, tokio_postgres::Error> {
    for identity in [
        format!("ip:{ip}"),
        format!(
            "identity:{ip}:{}:{}",
            slug.to_lowercase(),
            email.to_lowercase()
        ),
    ] {
        let count:i32=client.query_one(
            "INSERT INTO owner_login_limits(key_hash,attempts,window_until) VALUES($1,1,now()+interval '5 minutes') \
             ON CONFLICT(key_hash) DO UPDATE SET attempts=CASE WHEN owner_login_limits.window_until<=now() THEN 1 ELSE owner_login_limits.attempts+1 END, \
             window_until=CASE WHEN owner_login_limits.window_until<=now() THEN now()+interval '5 minutes' ELSE owner_login_limits.window_until END RETURNING attempts",
            &[&owner_auth::digest(&identity)]).await?.get(0);
        if count > 8 {
            return Ok(false);
        }
    }
    Ok(true)
}

pub(crate) async fn login(
    AxState(state): AxState<State>,
    peer: Option<Extension<ConnectInfo<SocketAddr>>>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    let v = match owner_validation::parse(&bytes, &headers, "OwnerLogin") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    let (slug, email, password) = (
        v["slug"].as_str().unwrap(),
        v["email"].as_str().unwrap(),
        v["password"].as_str().unwrap(),
    );
    let ip = peer
        .map(|p| p.0 .0.ip().to_string())
        .unwrap_or_else(|| "unknown".into());
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(mut client) = pool.get().await else {
        return server_error();
    };
    let Ok(tx) = client.transaction().await else {
        return server_error();
    };
    let allowed = match allow(&*tx, &ip, slug, email).await {
        Ok(a) => a,
        Err(_) => return server_error(),
    };
    if tx.commit().await.is_err() {
        return server_error();
    }
    if !allowed {
        return detail(429, "Too many login attempts");
    }
    let email = match owner_auth::clean_email(email) {
        Ok(e) => e,
        Err(_) => return detail(401, "Invalid credentials"),
    };
    let user=match client.query_opt("SELECT u.id,u.password_hash FROM tenant_users u JOIN tenants t ON t.id=u.tenant_id WHERE t.slug=$1 AND u.email=$2 AND u.active",&[&slug,&email]).await {
        Ok(Some(u))=>u,Ok(None)=>return detail(401,"Invalid credentials"),Err(_)=>return server_error()
    };
    let stored: String = user.get(1);
    let password = password.to_owned();
    // PBKDF2 runs off the async executor; request bodies are dropped before it runs.
    let valid =
        tokio::task::spawn_blocking(move || owner_auth::verify_password(&password, &stored))
            .await
            .unwrap_or(false);
    if !valid {
        return detail(401, "Invalid credentials");
    }
    let session = token();
    let id: uuid::Uuid = user.get(0);
    if client.execute("INSERT INTO tenant_sessions(user_id,token_hash,expires_at) VALUES($1,$2,now()+interval '12 hours')",&[&id,&owner_auth::digest(&session)]).await.is_err(){return server_error()}
    Json(json!({"access_token":session,"token_type":"bearer","expires_in":43200})).into_response()
}

// SQL errors remain internal; only deliberate invitation refusals reach customers.
enum ExchangeError {
    Refused(&'static str),
    Database,
}
impl From<tokio_postgres::Error> for ExchangeError {
    fn from(_: tokio_postgres::Error) -> Self {
        Self::Database
    }
}

async fn exchange(
    state: &State,
    raw: &str,
    password: Option<String>,
) -> Result<Value, ExchangeError> {
    let pwd = match password {
        None => None,
        Some(p) => {
            let mut salt = [0u8; 16];
            rand::rngs::OsRng.fill_bytes(&mut salt);
            Some(
                tokio::task::spawn_blocking(move || {
                    owner_auth::password_hash_with_salt(&p, &salt, owner_auth::ITERATIONS)
                })
                .await
                .map_err(|_| ExchangeError::Database)?
                .map_err(ExchangeError::Refused)?,
            )
        }
    };
    let pool = state.0.pool.as_ref().ok_or(ExchangeError::Database)?;
    let mut client = pool.get().await.map_err(|_| ExchangeError::Database)?;
    let tx = client.transaction().await?;
    let row=tx.query_opt("SELECT i.id,i.tenant_id,i.email,i.role,i.purpose,i.used_at,i.expires_at,t.slug FROM tenant_invites i JOIN tenants t ON t.id=i.tenant_id WHERE i.token_hash=$1 FOR UPDATE OF i",&[&owner_auth::digest(raw)]).await?.ok_or(ExchangeError::Refused("Link not recognised"))?;
    let used: Option<DateTime<Utc>> = row.get(5);
    let expires: DateTime<Utc> = row.get(6);
    let purpose: String = row.get(4);
    if expires <= Utc::now() {
        return Err(ExchangeError::Refused("This link has expired"));
    }
    if pwd.is_some() && used.is_some() {
        return Err(ExchangeError::Refused("This link has already been used"));
    }
    if purpose == "code" && used.is_some() {
        return Err(ExchangeError::Refused(
            "That code has already been used. Ask for a new one.",
        ));
    }
    if used.is_some_and(|at| Utc::now().signed_duration_since(at).num_milliseconds() > 1_800_000) {
        return Err(ExchangeError::Refused("This link has already been used"));
    }
    let tenant: uuid::Uuid = row.get(1);
    let email: String = row.get(2);
    let role: String = row.get(3);
    let slug: String = row.get(7);
    let invite_id: i64 = row.get(0);
    let existing = tx
        .query_opt(
            "SELECT id FROM tenant_users WHERE tenant_id=$1 AND email=$2",
            &[&tenant, &email],
        )
        .await?;
    if purpose == "recovery" && existing.is_none() {
        return Err(ExchangeError::Refused("Account no longer exists"));
    }
    let id: uuid::Uuid = if let Some(existing) = existing {
        let id: uuid::Uuid = existing.get(0);
        if let Some(p) = &pwd {
            tx.execute(
                "UPDATE tenant_users SET password_hash=$2,active=true WHERE id=$1",
                &[&id, p],
            )
            .await?;
            tx.execute("DELETE FROM tenant_sessions WHERE user_id=$1", &[&id])
                .await?;
        } else {
            tx.execute("UPDATE tenant_users SET active=true WHERE id=$1", &[&id])
                .await?;
        }
        id
    } else {
        tx.query_one("INSERT INTO tenant_users(tenant_id,email,role,password_hash) VALUES($1,$2,$3,$4) RETURNING id",&[&tenant,&email,&role,&pwd.as_deref().unwrap_or("no-password")]).await?.get(0)
    };
    tx.execute(
        "UPDATE tenant_invites SET used_at=now() WHERE id=$1",
        &[&invite_id],
    )
    .await?;
    if pwd.is_some() {
        tx.commit().await?;
        return Ok(json!({"email":email,"role":role,"slug":slug}));
    }
    tx.execute(
        "DELETE FROM tenant_sessions WHERE user_id=$1 AND expires_at<now()",
        &[&id],
    )
    .await?;
    let session = token();
    tx.execute("INSERT INTO tenant_sessions(user_id,token_hash,expires_at) VALUES($1,$2,now()+interval '30 days')",&[&id,&owner_auth::digest(&session)]).await?;
    tx.commit().await?;
    Ok(
        json!({"access_token":session,"token_type":"bearer","expires_in":2592000,"email":email,"role":role,"slug":slug}),
    )
}

fn answer(result: Result<Value, ExchangeError>, code: bool, redeem: bool) -> Response {
    match result {
        Ok(v) => Json(v).into_response(),
        Err(ExchangeError::Database) => server_error(),
        Err(ExchangeError::Refused(e)) => {
            let message = if redeem {
                "Invalid invitation or password"
            } else {
                match (e, code) {
                    ("Link not recognised", true) => {
                        "That code is not right. Check the email and try again."
                    }
                    ("This link has expired", true) => "That code has expired. Ask for a new one.",
                    ("Link not recognised", false) => {
                        "That link is not complete. Ask for a new one below and it will work."
                    }
                    ("This link has expired", false) => {
                        "This link has expired. Ask for a new one below."
                    }
                    ("This link has already been used", false) => {
                        "This link has already been used. Ask for a new one below."
                    }
                    ("Account no longer exists", false) => "That account no longer exists.",
                    _ => e,
                }
            };
            detail(400, message)
        }
    }
}

pub(crate) async fn invite(
    AxState(state): AxState<State>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    let v = match owner_validation::parse(&bytes, &headers, "OwnerLinkAccept") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    answer(
        exchange(&state, v["token"].as_str().unwrap(), None).await,
        false,
        false,
    )
}
pub(crate) async fn redeem(
    AxState(state): AxState<State>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    let v = match owner_validation::parse(&bytes, &headers, "OwnerRedeem") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    answer(
        exchange(
            &state,
            v["token"].as_str().unwrap(),
            Some(v["password"].as_str().unwrap().to_owned()),
        )
        .await,
        false,
        true,
    )
}
pub(crate) async fn verify_code(
    AxState(state): AxState<State>,
    peer: Option<Extension<ConnectInfo<SocketAddr>>>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    let v = match owner_validation::parse(&bytes, &headers, "OwnerCodeVerify") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    let code = v["code"].as_str().unwrap();
    if !owner_auth::valid_code(code) {
        return detail(422, "Code is not valid.");
    }
    let ip = peer
        .map(|p| p.0 .0.ip().to_string())
        .unwrap_or_else(|| "unknown".into());
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(mut client) = pool.get().await else {
        return server_error();
    };
    let Ok(tx) = client.transaction().await else {
        return server_error();
    };
    let allowed = match allow(&*tx, &ip, "code", v["email"].as_str().unwrap()).await {
        Ok(a) => a,
        Err(_) => return server_error(),
    };
    if tx.commit().await.is_err() {
        return server_error();
    }
    if !allowed {
        return detail(429, "Too many attempts. Please try again in a few minutes.");
    }
    answer(exchange(&state, code, None).await, true, false)
}
