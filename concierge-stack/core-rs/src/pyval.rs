//! Helpers that mirror Python's `str(x or "")` on JSON-derived values.
use serde_json::Value;

/// `str(value or "")` for the JSON shapes the API receives (string, number, bool, null). Containers and floats
/// have Python reprs this port does not reproduce, so they return `None` rather than guess.
pub fn str_or_empty(v: Option<&Value>) -> Option<String> {
    match v {
        None | Some(Value::Null) => Some(String::new()),
        Some(Value::String(s)) => Some(s.clone()),
        Some(Value::Bool(false)) => Some(String::new()),
        Some(Value::Bool(true)) => Some("True".into()),
        Some(Value::Number(n)) if n.is_i64() || n.is_u64() => Some(if n.as_i64() == Some(0) {
            String::new()
        } else {
            n.to_string()
        }),
        _ => None,
    }
}

/// `s[:n]` by characters.
pub fn truncate_chars(s: &str, n: usize) -> String {
    s.chars().take(n).collect()
}

/// Python truthiness for the same shapes.
pub fn truthy(v: Option<&Value>) -> bool {
    match v {
        None | Some(Value::Null) | Some(Value::Bool(false)) => false,
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Number(n)) => n.as_f64() != Some(0.0),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
        Some(Value::Bool(true)) => true,
    }
}
