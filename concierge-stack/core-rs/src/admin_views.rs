//! The response shapes of the read-only `/admin/...` listing routes that assemble more than a SQL row (port of the
//! pure parts of `main.py`, `scoring.describe`, `sla.py`, `sales.py` and `campaigns.stats`). The SQL lives in
//! `concierge-server`; everything here takes already-fetched rows as JSON values (timestamps as ISO strings, UUIDs as
//! strings, `jsonb` as text — exactly what `row_json` produces) and returns the body FastAPI would send.
use crate::scoring::WEIGHTS;
use serde_json::{json, Map, Value};

/// Python `round(x, ndigits)` on a float: correctly rounded from the exact binary value, ties to even, which is what
/// Rust's exact decimal formatting does.
fn round_py(x: f64, digits: usize) -> f64 {
    format!("{x:.digits$}").parse().unwrap_or(x)
}

/// `scoring.describe(tenant)`: the dashboard editor's weights. `scoring` is the stored value, still JSON text for a
/// `jsonb` column. A key's override is carried through untouched whatever its JSON type (Python indexes the merged
/// dict), unknown keys are ignored, and anything that is not an object means "no overrides".
pub fn describe_scoring(scoring: Option<&Value>) -> Value {
    let parsed;
    let raw = match scoring {
        Some(Value::String(s)) => {
            parsed = serde_json::from_str::<Value>(s).unwrap_or(Value::Null);
            &parsed
        }
        Some(v) => v,
        None => &Value::Null,
    };
    let overrides = raw.as_object();
    Value::Array(
        WEIGHTS
            .iter()
            .map(|(key, default, label, kind)| {
                let value = overrides
                    .and_then(|o| o.get(*key))
                    .cloned()
                    .unwrap_or_else(|| json!(default));
                json!({"key": key, "label": label, "kind": kind.name(), "default": default, "value": value})
            })
            .collect(),
    )
}

/// `_campaign_view`: `filters` arrives as JSON text and is decoded. Python raises on undecodable text (a 500).
pub fn campaign_view(campaign: &Value) -> Result<Map<String, Value>, &'static str> {
    let mut view = campaign.as_object().ok_or("row")?.clone();
    if let Some(Value::String(text)) = view.get("filters") {
        let decoded: Value = serde_json::from_str(text).map_err(|_| "filters")?;
        view.insert("filters".into(), decoded);
    }
    Ok(view)
}

/// `{**_campaign_view(campaign), "delivery": {status: n}}`.
pub fn campaign_with_delivery(
    campaign: &Value,
    delivery: &[(String, i64)],
) -> Result<Value, &'static str> {
    let mut view = campaign_view(campaign)?;
    let mut d = Map::new();
    for (status, n) in delivery {
        d.insert(status.clone(), json!(n));
    }
    view.insert("delivery".into(), Value::Object(d));
    Ok(Value::Object(view))
}

/// `sla.reasons_of`: `score_reasons` is JSON text (or already a list); anything else is "no reasons".
fn reasons_of(raw: Option<&Value>) -> Value {
    let list = match raw {
        Some(Value::String(s)) => serde_json::from_str::<Value>(s).unwrap_or(Value::Null),
        Some(v) => v.clone(),
        None => Value::Null,
    };
    if list.is_array() {
        list
    } else {
        json!([])
    }
}

fn int_or_zero(v: Option<&Value>) -> i64 {
    v.and_then(Value::as_i64).unwrap_or(0)
}

/// The body of `GET /admin/tenants/{slug}/sla`. `rows` are the overdue leads (empty when the feature is off).
pub fn sla_response(tenant: &Value, rows: &[Value]) -> Value {
    let min_score = match tenant.get("sla_min_score").and_then(Value::as_i64) {
        Some(n) => n,
        None => 70,
    };
    let waiting: Vec<Value> = rows
        .iter()
        .map(|w| {
            let field = |k: &str| w.get(k).cloned().unwrap_or(Value::Null);
            json!({
                "id": field("id"), "name": field("name"), "phone": field("phone"), "email": field("email"),
                "message": field("message"), "channel": field("channel"), "score": field("score"),
                "score_label": field("score_label"), "reasons": reasons_of(w.get("score_reasons")),
                "minutes_waiting": field("minutes_waiting"),
                "alerted": !field("sla_alerted_at").is_null(), "created_at": field("created_at"),
            })
        })
        .collect();
    json!({
        "sla_minutes": int_or_zero(tenant.get("sla_minutes")),
        "sla_min_score": min_score,
        "waiting": waiting,
    })
}

/// `sales.pipeline`: the forecast of the board plus the client's average lead value.
pub fn pipeline_view(rows: &[Value], average_cents: i64, per_stage: usize) -> Value {
    let mut result = crate::sales::forecast(rows, Some(average_cents), per_stage);
    result["average_lead_value_cents"] = json!(average_cents);
    result
}

/// Everything `sales.summary` reads, already fetched.
pub struct SummaryInput<'a> {
    pub days: i64,
    pub new_leads: i64,
    /// `to_status -> count` of stage moves inside the window.
    pub moved: &'a [(String, i64)],
    /// `value_cents` of each lead won inside the window.
    pub won_values: &'a [i64],
    pub average_cents: i64,
    pub open_value_cents: i64,
    pub weighted_value_cents: i64,
    pub overdue_todos: i64,
    /// `None` when the client has no response target at all.
    pub leads_waiting: Option<i64>,
}

pub fn summary_view(s: &SummaryInput) -> Value {
    let moved = |k: &str| {
        s.moved
            .iter()
            .find(|(status, _)| status == k)
            .map_or(0, |(_, n)| *n)
    };
    let won_value: i64 = s
        .won_values
        .iter()
        .map(|v| if *v != 0 { *v } else { s.average_cents })
        .sum();
    let won = s.won_values.len() as i64;
    let lost = moved("lost");
    let win_rate = if won + lost != 0 {
        json!(round_py(won as f64 / (won + lost) as f64, 2))
    } else {
        Value::Null
    };
    json!({
        "days": s.days, "new_leads": s.new_leads, "contacted": moved("contacted"), "booked": moved("booked"),
        "won": won, "won_value_cents": won_value, "lost": lost, "win_rate": win_rate,
        "open_value_cents": s.open_value_cents, "weighted_value_cents": s.weighted_value_cents,
        "overdue_todos": s.overdue_todos, "leads_waiting": s.leads_waiting,
    })
}

/// Everything `_stats` reads, already fetched.
pub struct StatsInput<'a> {
    pub days: i64,
    pub conversations_by_channel: &'a [(String, i64)],
    pub leads_by_status: &'a [(String, i64)],
    pub appointments: i64,
    pub quote_guard_interventions: i64,
    pub sent_by_channel: &'a [(String, i64)],
    /// `(day, conversations, leads)`, the day as `YYYY-MM-DD`.
    pub daily: &'a [(String, i64, i64)],
    pub lead_value_cents: i64,
    pub won_value_cents: i64,
}

fn counts(pairs: &[(String, i64)]) -> Value {
    let mut m = Map::new();
    for (k, n) in pairs {
        m.insert(k.clone(), json!(n));
    }
    Value::Object(m)
}

pub fn stats_view(s: &StatsInput) -> Value {
    let total_leads: i64 = s.leads_by_status.iter().map(|(_, n)| n).sum();
    let total_convs: i64 = s.conversations_by_channel.iter().map(|(_, n)| n).sum();
    let lead_rate = if total_convs != 0 {
        json!(round_py(total_leads as f64 / total_convs as f64, 3))
    } else {
        json!(0)
    };
    json!({
        "days": s.days,
        "conversations": total_convs,
        "by_channel": counts(s.conversations_by_channel),
        "leads": total_leads,
        "leads_by_status": counts(s.leads_by_status),
        "lead_rate": lead_rate,
        "appointments": s.appointments,
        "estimated_pipeline_cents": total_leads * s.lead_value_cents,
        "won_value_cents": s.won_value_cents,
        "quote_guard_interventions": s.quote_guard_interventions,
        "messages_sent": counts(s.sent_by_channel),
        "daily": s.daily.iter().map(|(day, c, l)| json!({"day": day, "conversations": c, "leads": l})).collect::<Vec<_>>(),
    })
}
