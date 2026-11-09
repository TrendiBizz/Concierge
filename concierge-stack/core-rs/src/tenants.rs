//! Port of the pure parts of `tenants.py`: which fields may be updated, the UPDATE statement built from them, how a
//! new tenant's slug is chosen under conflicts, what a clone copies, and the browser-safe view.
use crate::pyjson;
use serde_json::{json, Map, Value};

pub const UPDATABLE_FIELDS: [&str; 34] = [
    "name",
    "site_url",
    "allowed_origins",
    "persona",
    "greeting",
    "cta_text",
    "accent_color",
    "voice",
    "voice_enabled",
    "voice_daily_limit",
    "phone_enabled",
    "phone_daily_limit",
    "booking_url",
    "lead_webhook_url",
    "incentive",
    "timezone",
    "business_hours",
    "slot_minutes",
    "min_notice_hours",
    "max_days_ahead",
    "native_booking",
    "notify_email",
    "notify_phone",
    "email_auto_reply",
    "sms_enabled",
    "sms_from",
    "lead_sms_template",
    "review_url",
    "lead_value_cents",
    "sla_minutes",
    "sla_min_score",
    "campaigns_enabled",
    "scoring",
    "weekly_digest",
];
pub const JSONB_FIELDS: [&str; 2] = ["business_hours", "scoring"];
pub const CLONE_FIELDS: [&str; 17] = [
    "persona",
    "greeting",
    "cta_text",
    "accent_color",
    "voice",
    "voice_enabled",
    "voice_daily_limit",
    "incentive",
    "timezone",
    "business_hours",
    "slot_minutes",
    "min_notice_hours",
    "max_days_ahead",
    "native_booking",
    "sms_enabled",
    "lead_sms_template",
    "lead_value_cents",
];

/// The UPDATE statement and parameters for `update(slug, fields)`, or `None` when no updatable value remains (Python then
/// just reads the tenant). `Err` when a JSON value needs a float repr this port does not reproduce.
pub fn update_plan(
    slug: &str,
    fields: &Map<String, Value>,
) -> Result<Option<(String, Vec<Value>)>, &'static str> {
    let mut parts = Vec::new();
    let mut values = vec![json!(slug)];
    for (k, v) in fields {
        if !UPDATABLE_FIELDS.contains(&k.as_str()) || v.is_null() {
            continue;
        }
        let i = values.len() + 1;
        if JSONB_FIELDS.contains(&k.as_str()) {
            parts.push(format!("{k} = ${i}::jsonb"));
            values.push(json!(pyjson::dumps(v).ok_or("float in JSON field")?));
        } else {
            parts.push(format!("{k} = ${i}"));
            values.push(v.clone());
        }
    }
    if parts.is_empty() {
        return Ok(None);
    }
    Ok(Some((
        format!(
            "UPDATE tenants SET {} WHERE slug = $1 RETURNING *",
            parts.join(", ")
        ),
        values,
    )))
}

/// `_load`: JSON text in the two JSON columns becomes structured data.
pub fn load(row: &Value) -> Result<Value, &'static str> {
    let mut data = row.as_object().ok_or("row")?.clone();
    for key in ["business_hours", "demo_questions"] {
        if let Some(Value::String(text)) = data.get(key) {
            let parsed: Value = serde_json::from_str(text).map_err(|_| "invalid JSON column")?;
            data.insert(key.to_string(), parsed);
        }
    }
    Ok(Value::Object(data))
}

/// The slug tried on attempt `attempt` (0 is the first): the base, then `base-2`, `base-3`, ...
pub fn slug_attempt(base: &str, attempt: usize) -> String {
    if attempt == 0 {
        base.to_string()
    } else {
        format!("{base}-{}", attempt + 1)
    }
}

/// Parameters of the tenant INSERT, in column order.
pub fn create_args(
    slug: &str,
    name: &str,
    public_key: &str,
    report_token: &str,
    site_url: Option<&str>,
    fields: &Map<String, Value>,
) -> Vec<Value> {
    let or_default = |key: &str, default: Value| match fields.get(key) {
        Some(v) if crate::pyval::truthy(Some(v)) => v.clone(),
        _ => default,
    };
    vec![
        json!(slug),
        json!(name),
        json!(public_key),
        json!(report_token),
        json!(site_url),
        or_default("allowed_origins", json!([])),
        or_default("persona", json!("")),
        or_default("greeting", json!("")),
        fields.get("booking_url").cloned().unwrap_or(Value::Null),
        fields
            .get("lead_webhook_url")
            .cloned()
            .unwrap_or(Value::Null),
        or_default("incentive", json!("")),
    ]
}

/// What a clone copies from its source: only the snapshot fields that have a value.
pub fn clone_fields(source: &Map<String, Value>) -> Map<String, Value> {
    CLONE_FIELDS
        .iter()
        .filter_map(|f| {
            source
                .get(*f)
                .filter(|v| !v.is_null())
                .map(|v| (f.to_string(), v.clone()))
        })
        .collect()
}

/// Fields safe to return to the browser.
pub fn public_view(tenant: &Value) -> Value {
    let name = tenant["name"].as_str().unwrap_or("");
    let greeting = match tenant["greeting"].as_str() {
        Some(g) if !g.is_empty() => g.to_string(),
        _ => format!("Hi! I'm {name}'s AI guide. Ask me anything about our business."),
    };
    json!({"name": tenant["name"], "greeting": greeting, "cta_text": tenant["cta_text"],
           "accent_color": tenant["accent_color"], "voice_enabled": tenant["voice_enabled"]})
}
