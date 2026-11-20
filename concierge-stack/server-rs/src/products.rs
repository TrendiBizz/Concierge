//! Tenant-scoped product catalogue with owner-only costs and atomic stock audit.
use crate::{detail, owner, owner_validation, row_json, server_error, State};
use axum::{
    body::Bytes,
    extract::{Path, State as AxState},
    http::HeaderMap,
    response::{IntoResponse, Response},
    Json,
};
use concierge_core::py_strip;
use serde_json::Value;
use tokio_postgres::Row;

fn view(row: &Row, role: &str) -> Value {
    let mut value = row_json(row);
    if role != "owner" {
        value.as_object_mut().unwrap().remove("cost_price_cents");
    }
    value
}
fn permission(user: &owner::User, owner_only: bool) -> bool {
    user.role == "owner" || (!owner_only && user.role == "editor")
}
fn product_id(raw: &str) -> Result<uuid::Uuid, &'static str> {
    uuid::Uuid::parse_str(raw).map_err(|_| "Product id is not valid.")
}

pub(crate) async fn listing(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    let user = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    if !permission(&user, false) {
        return detail(403, "Insufficient permissions");
    }
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(client) = pool.get().await else {
        return server_error();
    };
    match client
        .query(
            "SELECT * FROM products WHERE tenant_id=$1 ORDER BY active DESC,name",
            &[&user.tenant_id],
        )
        .await
    {
        Ok(rows) => {
            Json(rows.iter().map(|r| view(r, &user.role)).collect::<Vec<_>>()).into_response()
        }
        Err(_) => server_error(),
    }
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
    let user = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    // FastAPI validates path/body after dependencies but before handler role checks.
    let id = match raw.as_deref().map(product_id).transpose() {
        Ok(id) => id,
        Err(e) => return detail(422, e),
    };
    let v = match owner_validation::parse(&bytes, &headers, "ProductIn") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    if !permission(&user, true) {
        return detail(403, "Insufficient permissions");
    }
    let (sku, name, description, unit) = (
        py_strip(v["sku"].as_str().unwrap()),
        py_strip(v["name"].as_str().unwrap()),
        py_strip(v["description"].as_str().unwrap()),
        py_strip(v["unit"].as_str().unwrap()),
    );
    let sale = v["sale_price_cents"].as_i64().unwrap();
    let cost = v["cost_price_cents"].as_i64();
    let stock = v["stock_quantity"].as_i64().unwrap() as i32;
    let active = v["active"].as_bool().unwrap();
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(client) = pool.get().await else {
        return server_error();
    };
    let result = if let Some(id) = id {
        client.query_opt("UPDATE products SET sku=$3,name=$4,description=$5,unit=$6,sale_price_cents=$7,cost_price_cents=$8,stock_quantity=$9,active=$10,updated_at=now() WHERE tenant_id=$1 AND id=$2 RETURNING *",&[&user.tenant_id,&id,&sku,&name,&description,&unit,&sale,&cost,&stock,&active]).await
    } else {
        client.query_opt("INSERT INTO products(tenant_id,sku,name,description,unit,sale_price_cents,cost_price_cents,stock_quantity,active) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *",&[&user.tenant_id,&sku,&name,&description,&unit,&sale,&cost,&stock,&active]).await
    };
    match result {
        Ok(Some(row)) => (
            if raw.is_some() {
                axum::http::StatusCode::OK
            } else {
                axum::http::StatusCode::CREATED
            },
            Json(view(&row, &user.role)),
        )
            .into_response(),
        Ok(None) => detail(404, "Product not found"),
        Err(_) => server_error(),
    }
}

pub(crate) async fn deactivate(
    AxState(state): AxState<State>,
    Path(raw): Path<String>,
    headers: HeaderMap,
) -> Response {
    if let Some(r) = crate::unroutable(&raw) {
        return r;
    }
    let user = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let id = match product_id(&raw) {
        Ok(id) => id,
        Err(e) => return detail(422, e),
    };
    if !permission(&user, true) {
        return detail(403, "Insufficient permissions");
    }
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(client) = pool.get().await else {
        return server_error();
    };
    match client.query_opt("UPDATE products SET active=false,updated_at=now() WHERE tenant_id=$1 AND id=$2 RETURNING *",&[&user.tenant_id,&id]).await{
        Ok(Some(row))=>Json(view(&row,&user.role)).into_response(),Ok(None)=>detail(404,"Product not found"),Err(_)=>server_error()
    }
}

pub(crate) async fn stock(
    AxState(state): AxState<State>,
    Path(raw): Path<String>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Response {
    if let Some(r) = crate::unroutable(&raw) {
        return r;
    }
    let user = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let id = match product_id(&raw) {
        Ok(id) => id,
        Err(e) => return detail(422, e),
    };
    let v = match owner_validation::parse(&bytes, &headers, "StockAdjust") {
        Ok(v) => v,
        Err(e) => return detail(422, &e),
    };
    if !permission(&user, false) {
        return detail(403, "Insufficient permissions");
    }
    let delta = v["delta"].as_i64().unwrap() as i32;
    let reason = py_strip(v["reason"].as_str().unwrap());
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(mut client) = pool.get().await else {
        return server_error();
    };
    let Ok(tx) = client.transaction().await else {
        return server_error();
    };
    match tx
        .query_opt(
            "SELECT id FROM products WHERE tenant_id=$1 AND id=$2 FOR UPDATE",
            &[&user.tenant_id, &id],
        )
        .await
    {
        Ok(Some(_)) => (),
        Ok(None) => return detail(404, "Product not found"),
        Err(_) => return server_error(),
    }
    if tx.execute("INSERT INTO product_stock_movements(tenant_id,product_id,delta,reason,actor) VALUES($1,$2,$3,$4,$5)",&[&user.tenant_id,&id,&delta,&reason,&user.email]).await.is_err(){return server_error()}
    let row=match tx.query_one("UPDATE products SET stock_quantity=stock_quantity+$3,updated_at=now() WHERE tenant_id=$1 AND id=$2 RETURNING *",&[&user.tenant_id,&id,&delta]).await{Ok(row)=>row,Err(_)=>return server_error()};
    if tx.commit().await.is_err() {
        return server_error();
    }
    Json(view(&row, &user.role)).into_response()
}
