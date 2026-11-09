//! Outbound event shaping (port of the pure parts of `events.py`).
use crate::pyval::{str_or_empty, truncate_chars};
use crate::{is_py_space, py_strip};
use chrono::DateTime;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

fn s(v: Option<&Value>) -> Option<String> {
    str_or_empty(v)
}
fn field(v: &Value, k: &str) -> Option<String> {
    s(v.get(k))
}
/// Flat `/lead` payload for the Twenty bridge, or `None` when the event is not mapped or has no contact.
/// Datetimes inside `sections` must already be Python `str()` text (space separator).
pub fn twenty_bridge_payload(tenant: &Value, event: &str, sections: &Value) -> Option<Value> {
    if !["lead.created", "appointment.booked", "voice.completed"].contains(&event) {
        return None;
    }
    let empty = json!({});
    let lead_raw = sections.get("lead");
    let appt_raw = sections.get("appointment");
    let lead_truthy = crate::pyval::truthy(lead_raw);
    let lead = if lead_truthy {
        lead_raw.unwrap()
    } else {
        &empty
    };
    let appt = if crate::pyval::truthy(appt_raw) {
        appt_raw.unwrap()
    } else {
        &empty
    };
    let person = if lead_truthy { lead } else { appt };
    if !person.is_object() {
        return None;
    }
    let email = py_strip(&field(person, "email")?).to_string();
    let phone = py_strip(&field(person, "phone")?).to_string();
    if email.is_empty() && phone.is_empty() {
        return None;
    }
    let name = field(person, "name")?;
    let mut parts = py_strip(&name)
        .splitn(2, is_py_space)
        .filter(|p| !p.is_empty());
    let first = parts.next().unwrap_or("").to_string();
    let rest = {
        let t = py_strip(&name);
        let after = t.strip_prefix(first.as_str()).unwrap_or("");
        py_strip(after).to_string()
    };
    let detail = if event == "lead.created" || event == "voice.completed" {
        truncate_chars(&field(lead, "message")?, 1400)
    } else {
        truncate_chars(
            &format!(
                "Appointment booked: {} | {}",
                field(appt, "starts_at")?,
                field(appt, "notes")?
            ),
            1400,
        )
    };
    let channel = field(lead, "channel")?;
    Some(json!({
        "first_name": truncate_chars(&first, 80), "last_name": truncate_chars(&rest, 80),
        "email": truncate_chars(&email, 200), "phone": truncate_chars(&phone, 40),
        "company": truncate_chars(&field(tenant, "name")?, 120),
        "source": format!("Concierge {}", if channel.is_empty() { "booking" } else { &channel }),
        "message": detail,
    }))
}

/// Only the internal bridge on port 4410 may be configured (`events._bridge_url`).
pub fn bridge_url_allowed(raw: &str) -> bool {
    let Ok(u) = url::Url::parse(raw) else {
        return false;
    };
    u.scheme() == "http"
        && matches!(
            u.host_str(),
            Some("127.0.0.1" | "localhost" | "host.docker.internal" | "twenty-bridge")
        )
        && u.port() == Some(4410)
        && u.path() == "/lead"
        && u.query().is_none()
        && u.fragment().is_none()
        && u.username().is_empty()
        && u.password().is_none()
}

/// `json.dumps(x, ensure_ascii=True)` for a string: escapes non-ASCII as \uXXXX (surrogate pairs above the BMP).
fn json_ascii_string(s: &str) -> String {
    let mut out = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            c if (c as u32) < 0x20 || (c as u32) > 0x7e => {
                let mut buf = [0u16; 2];
                for unit in c.encode_utf16(&mut buf) {
                    out.push_str(&format!("\\u{unit:04x}"));
                }
            }
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// Stable tenant-scoped receipt id shared with the CRM bridge: SHA-256 of the compact ASCII JSON array.
pub fn delivery_id(tenant_id: &str, event: &str, source_id: &str) -> String {
    let identity = format!(
        "[{},{},{}]",
        json_ascii_string(tenant_id),
        json_ascii_string(event),
        json_ascii_string(source_id)
    );
    Sha256::digest(identity.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// Python `datetime.isoformat()` for an aware UTC value: microseconds only when non-zero.
pub fn iso_utc(secs: i64, micros: u32) -> String {
    let d = DateTime::from_timestamp(secs, 0).expect("in range");
    let base = d.format("%Y-%m-%dT%H:%M:%S").to_string();
    if micros == 0 {
        format!("{base}+00:00")
    } else {
        format!("{base}.{micros:06}+00:00")
    }
}

fn id_text(v: Option<&Value>) -> Value {
    match v {
        Some(Value::String(t)) => json!(t),
        Some(Value::Number(n)) => json!(n.to_string()),
        _ => Value::Null,
    }
}
fn get(v: &Value, k: &str) -> Value {
    v.get(k).cloned().unwrap_or(Value::Null)
}

/// `scoring.reasons_of`: a JSON string or a list; anything else is empty.
pub fn reasons_of(lead: &Value) -> Vec<Value> {
    match lead.get("score_reasons") {
        Some(Value::String(t)) => match serde_json::from_str::<Value>(t) {
            Ok(Value::Array(a)) => a,
            _ => Vec::new(),
        },
        Some(Value::Array(a)) => a.clone(),
        _ => Vec::new(),
    }
}

/// `events.lead_view`. `created_at` is `(unix seconds, microseconds)`, UTC. Err when `utm` is invalid JSON text
/// (Python raises).
pub fn lead_view(lead: &Value, created_at: (i64, u32)) -> Result<Value, String> {
    let utm = match lead.get("utm") {
        Some(Value::String(t)) => serde_json::from_str::<Value>(t).map_err(|e| e.to_string())?,
        Some(v) if crate::pyval::truthy(Some(v)) => v.clone(),
        _ => json!({}),
    };
    Ok(json!({
        "id": id_text(lead.get("id")), "name": get(lead, "name"), "email": get(lead, "email"), "phone": get(lead, "phone"),
        "message": get(lead, "message"), "channel": get(lead, "channel"), "score": get(lead, "score"),
        "score_label": get(lead, "score_label"), "score_reasons": reasons_of(lead), "page_url": get(lead, "page_url"),
        "utm": utm, "created_at": iso_utc(created_at.0, created_at.1),
    }))
}

/// `events.appointment_view`; `starts`/`ends` are `(unix seconds, microseconds)`, UTC.
pub fn appointment_view(
    appt: &Value,
    starts: (i64, u32),
    ends: (i64, u32),
    tz_label: &str,
) -> Value {
    json!({
        "id": id_text(appt.get("id")), "starts_at": iso_utc(starts.0, starts.1), "ends_at": iso_utc(ends.0, ends.1),
        "name": get(appt, "name"), "phone": get(appt, "phone"), "email": get(appt, "email"), "notes": get(appt, "notes"),
        "status": get(appt, "status"), "timezone": tz_label,
    })
}
