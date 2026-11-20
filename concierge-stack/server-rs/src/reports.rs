//! Accountant export: cohort limits, exact database sums and CSV escaping.
use crate::{detail, owner, server_error, State};
use axum::{
    extract::{Query, State as AxState},
    http::{header, HeaderMap},
    response::{IntoResponse, Response},
};
use concierge_core::pydantic;
use serde_json::json;
use std::collections::HashMap;
fn csv(cells: &[Option<String>]) -> String {
    cells
        .iter()
        .map(|cell| {
            let s = cell.as_deref().unwrap_or("");
            if s.contains([',', '"', '\n']) {
                format!("\"{}\"", s.replace('"', "\"\""))
            } else {
                s.to_owned()
            }
        })
        .collect::<Vec<_>>()
        .join(",")
}
pub(crate) async fn export(
    AxState(state): AxState<State>,
    headers: HeaderMap,
    Query(q): Query<HashMap<String, String>>,
) -> Response {
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let days = match q.get("days") {
        None => 30,
        Some(raw) => match pydantic::parse_int(&json!(raw)) {
            Ok(n) => n.clamp(1, 365) as i32,
            Err(_) => return detail(422, "Days is not valid."),
        },
    };
    if !matches!(u.role.as_str(), "owner" | "editor" | "viewer") {
        return detail(403, "Insufficient permissions");
    }
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    let leads=match c.query("SELECT l.status,l.channel,l.lost_reason,count(*)::text,coalesce(sum(l.value_cents),0)::text FROM leads l WHERE l.tenant_id=$1 AND l.created_at > now()-make_interval(days=>$2) GROUP BY l.status,l.channel,l.lost_reason ORDER BY l.status,count(*) DESC",&[&u.tenant_id,&days]).await {Ok(r)=>r,Err(_)=>return server_error()};
    let quotes=match c.query("SELECT status,count(*)::text,coalesce(sum(total_cents),0)::text FROM quotations WHERE tenant_id=$1 AND created_at > now()-make_interval(days=>$2) GROUP BY status ORDER BY status",&[&u.tenant_id,&days]).await {Ok(r)=>r,Err(_)=>return server_error()};
    let mut lines =
        vec!["section,stage_or_status,channel,lost_reason,count,value_cents".to_owned()];
    for r in leads {
        lines.push(csv(&[
            Some("enquiries".into()),
            r.get(0),
            r.get(1),
            r.get(2),
            r.get(3),
            r.get(4),
        ]));
    }
    for r in quotes {
        lines.push(csv(&[
            Some("quotes".into()),
            r.get(0),
            None,
            None,
            r.get(1),
            r.get(2),
        ]));
    }
    (
        [
            (header::CONTENT_TYPE, "text/csv; charset=utf-8"),
            (
                header::CONTENT_DISPOSITION,
                "attachment; filename=concierge-report.csv",
            ),
        ],
        lines.join("\n") + "\n",
    )
        .into_response()
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn preserves_python_csv_rules() {
        assert_eq!(
            csv(&[None, Some("a,\"b\n".into()), Some("\r".into())]),
            ",\"a,\"\"b\n\",\r"
        );
    }
}
