//! Tool specs and lead-capture input rules (port of the pure parts of `tools.py`).
use crate::contact::{is_email, normalize_phone};
use crate::py_strip;
use crate::pyval::{str_or_empty, truncate_chars, truthy};
use serde_json::{json, Value};
use std::sync::OnceLock;

/// Generated from the live Python by `parity/gen_tool_specs.py`.
const SPECS_JSON: &str = include_str!("tool_specs.json");

fn specs() -> &'static Vec<Value> {
    static S: OnceLock<Vec<Value>> = OnceLock::new();
    S.get_or_init(|| serde_json::from_str(SPECS_JSON).expect("tool_specs.json is valid"))
}

fn flag(spec: &Value, key: &str) -> bool {
    spec.get(key).and_then(Value::as_bool).unwrap_or(false)
}
fn name_of(spec: &Value) -> &str {
    spec["name"].as_str().unwrap_or("")
}

/// The `available` rule of each tool, given the tenant's fields.
pub fn available(name: &str, tenant: &Value) -> bool {
    let booking_url = truthy(tenant.get("booking_url"));
    let native = truthy(tenant.get("native_booking"));
    match name {
        "get_booking_link" => booking_url && !native,
        "check_availability" | "book_appointment" => native,
        _ => true,
    }
}

fn pick(spec: &Value) -> serde_json::Map<String, Value> {
    ["name", "description", "parameters"]
        .iter()
        .map(|k| (k.to_string(), spec[*k].clone()))
        .collect()
}

/// OpenAI-format tools for text chat / SMS.
pub fn chat_tools(tenant: &Value) -> Vec<Value> {
    specs()
        .iter()
        .filter(|s| flag(s, "chat") && available(name_of(s), tenant))
        .map(|s| json!({"type": "function", "function": pick(s)}))
        .collect()
}

/// Flat-format tools for Grok Voice; `website_only` tools appear only on the website.
pub fn voice_tools(tenant: &Value, website: bool) -> Vec<Value> {
    specs()
        .iter()
        .filter(|s| {
            flag(s, "voice")
                && available(name_of(s), tenant)
                && (website || !flag(s, "website_only"))
        })
        .map(|s| {
            let mut m = serde_json::Map::new();
            m.insert("type".into(), json!("function"));
            m.extend(pick(s));
            Value::Object(m)
        })
        .collect()
}

#[derive(Debug, PartialEq, Eq)]
pub struct CapturedLead {
    pub name: String,
    pub email: String,
    pub phone: String,
    pub message: String,
    pub consent: bool,
    pub marketing: bool,
    pub email_ok: bool,
}

/// Normalise `capture_lead` arguments exactly as `_capture_lead` does before touching the database.
/// `Ok(None)` is never returned; `Err` is the message shown to the model. `Unsupported` arguments (lists,
/// floats) are refused rather than guessed.
pub fn normalise_capture(
    args: &Value,
    sender_phone: Option<&str>,
    sms_inbound: bool,
    default_cc: &str,
) -> Result<CapturedLead, String> {
    let s = |k: &str, n: usize| -> Result<String, String> {
        let v = str_or_empty(args.get(k)).ok_or("unsupported argument type")?;
        Ok(truncate_chars(py_strip(&v), n))
    };
    let name = s("name", 120)?;
    let email = s("email", 200)?;
    let phone_raw = match str_or_empty(args.get("phone")).ok_or("unsupported argument type")? {
        p if !p.is_empty() => truncate_chars(py_strip(&p), 40),
        _ => truncate_chars(py_strip(sender_phone.unwrap_or("")), 40),
    };
    let message = s("message", 1000)?;
    let consent = truthy(args.get("consent_to_contact")) || sms_inbound;
    let marketing = truthy(args.get("consent_to_marketing"));
    let phone = normalize_phone(&phone_raw, default_cc).unwrap_or_default();
    let email_ok = is_email(&email);
    if !(email_ok || !phone.is_empty()) {
        return Err("Need a valid phone number or email address. Ask the visitor for one.".into());
    }
    // The database stores an empty string when the email is not a valid address.
    let email = if email_ok { email } else { String::new() };
    Ok(CapturedLead {
        name,
        email,
        phone,
        message,
        consent,
        marketing,
        email_ok,
    })
}

/// `_search_knowledge` query clamp: `str(query or "").strip()[:300]`; `None` means the empty-query error.
pub fn search_query(args: &Value) -> Option<String> {
    let q = truncate_chars(py_strip(&str_or_empty(args.get("query"))?), 300);
    (!q.is_empty()).then_some(q)
}
