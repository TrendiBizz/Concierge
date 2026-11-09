use crate::py_strip;
use regex::Regex;
use std::sync::OnceLock;

fn email_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[^@\s]+@[^@\s]+\.[^@\s]+$").unwrap())
}

pub fn is_email(value: &str) -> bool {
    !value.is_empty() && email_re().is_match(py_strip(value))
}

/// Return an E.164 number (`+15551234567`) or `None` if it cannot be a real phone number.
pub fn normalize_phone(raw: &str, default_cc: &str) -> Option<String> {
    let raw = py_strip(raw);
    let digits: String = raw.chars().filter(|c| c.is_ascii_digit()).collect();
    if digits.is_empty() {
        return None;
    }
    let n = digits.len();
    if raw.starts_with('+') {
        return (8..=15).contains(&n).then(|| format!("+{digits}"));
    }
    if n == 10 {
        return Some(format!("+{default_cc}{digits}"));
    }
    if n == 11 && digits.starts_with(default_cc) {
        return Some(format!("+{digits}"));
    }
    (8..=15).contains(&n).then(|| format!("+{digits}"))
}

/// Canonical key for opt-out lookups: E.164 phone or lower-cased email.
pub fn contact_key(value: &str, default_cc: &str) -> String {
    let value = py_strip(value);
    if value.contains('@') {
        return value.to_lowercase();
    }
    normalize_phone(value, default_cc).unwrap_or_else(|| value.to_string())
}
