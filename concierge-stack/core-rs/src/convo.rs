//! Conversation input cleaners (port of `convo.clean_utm` / `clean_session`).
use crate::pyval::truncate_chars;
use serde_json::Value;

fn py_str(v: &Value) -> Option<String> {
    match v {
        Value::Null => Some("None".into()),
        Value::Bool(b) => Some(if *b { "True" } else { "False" }.into()),
        Value::String(s) => Some(s.clone()),
        Value::Number(n) if n.is_i64() || n.is_u64() => Some(n.to_string()),
        _ => None,
    }
}

/// Keep up to ten `utm_*` parameters, key at most 40 and value at most 200 characters (insertion order preserved).
/// Floats and containers have Python reprs this port does not reproduce and make the whole call `None`.
pub fn clean_utm(utm: &serde_json::Map<String, Value>) -> Option<Vec<(String, String)>> {
    let mut out: Vec<(String, String)> = Vec::new();
    for (key, value) in utm {
        if key.starts_with("utm_") && out.len() < 10 {
            let k = truncate_chars(key, 40);
            let v = truncate_chars(&py_str(value)?, 200);
            match out.iter_mut().find(|(ek, _)| *ek == k) {
                Some(slot) => slot.1 = v,
                None => out.push((k, v)),
            }
        }
    }
    Some(out)
}

/// Strip everything but `[A-Za-z0-9_-]`, cap at 64, require at least 8 (`400 Invalid session_id` otherwise).
pub fn clean_session(session_id: &str) -> Result<String, &'static str> {
    let cleaned: String = session_id
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '_' || *c == '-')
        .take(64)
        .collect();
    if cleaned.len() < 8 {
        Err("Invalid session_id")
    } else {
        Ok(cleaned)
    }
}
