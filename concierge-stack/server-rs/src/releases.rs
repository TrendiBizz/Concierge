//! Release notices persist acknowledgement per user, including across tenant sessions.
use crate::{owner, server_error, State};
use axum::{
    extract::State as AxState,
    http::HeaderMap,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use std::sync::OnceLock;

fn catalog() -> &'static Value {
    static CATALOG: OnceLock<Value> = OnceLock::new();
    CATALOG.get_or_init(|| {
        serde_json::from_str(include_str!("release_catalog.json")).expect("release catalog")
    })
}
fn version() -> i32 {
    catalog()
        .as_object()
        .unwrap()
        .keys()
        .map(|key| key.parse::<i32>().expect("release version"))
        .max()
        .expect("release catalog is nonempty")
}
pub(crate) async fn public_version() -> Json<Value> {
    let version = version();
    Json(json!({"version":version,"label":catalog()[version.to_string()]["title"]}))
}
pub(crate) async fn notice(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
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
    let seen = match c
        .query_opt(
            "SELECT last_seen_version FROM tenant_users WHERE id=$1 AND tenant_id=$2",
            &[&u.id, &u.tenant_id],
        )
        .await
    {
        Ok(Some(r)) => r.get::<_, i32>(0),
        _ => return server_error(),
    };
    let version = version();
    let cur = &catalog()[version.to_string()];
    Json(json!({"version":version,"label":cur["title"],"released":cur["released"],"summary":cur["summary"],"notes":cur["notes"],"unseen":seen<version})).into_response()
}
pub(crate) async fn seen(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
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
    let version = version();
    match c.execute("UPDATE tenant_users SET last_seen_version=GREATEST(last_seen_version,$3) WHERE id=$1 AND tenant_id=$2", &[&u.id,&u.tenant_id,&version]).await {
        Ok(1) => Json(json!({"seen":version})).into_response(),
        _ => server_error(),
    }
}
