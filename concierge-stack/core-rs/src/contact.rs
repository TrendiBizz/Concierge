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

/// Match the current Python dial-plan rules. Ambiguous or incomplete national
/// numbers are refused instead of fabricating an E.164 destination.
pub fn normalize_phone(raw: &str, default_cc: &str) -> Option<String> {
    fn digits(value: &str) -> String {
        static NON_DIGIT: OnceLock<Regex> = OnceLock::new();
        NON_DIGIT
            .get_or_init(|| Regex::new(r"\D").unwrap())
            .replace_all(value, "")
            .into_owned()
    }
    let raw = py_strip(raw);
    let number = digits(raw);
    let cc = digits(default_cc);
    if number.is_empty() || raw.chars().any(|c| c.is_ascii_alphabetic()) {
        return None;
    }
    if raw.starts_with('+') {
        return (8..=15)
            .contains(&number.chars().count())
            .then(|| format!("+{number}"));
    }
    let (trunk, lengths): (&str, &[usize]) = match cc.as_str() {
        "1" => ("1", &[10]),
        "44" => ("0", &[10]),
        "61" => ("0", &[9]),
        "64" => ("0", &[8, 9]),
        "353" => ("0", &[9]),
        "49" => ("0", &[10, 11]),
        "33" => ("0", &[9]),
        "91" => ("0", &[10]),
        _ => return None,
    };
    if let Some(rest) = number.strip_prefix(&cc).filter(|s| !s.is_empty()) {
        if let Some(stripped) = rest.strip_prefix(trunk).filter(|s| !s.is_empty()) {
            if lengths.contains(&stripped.chars().count()) {
                return Some(format!("+{cc}{stripped}"));
            }
        }
        if lengths.contains(&rest.chars().count()) {
            return Some(format!("+{cc}{rest}"));
        }
    }
    if let Some(stripped) = number.strip_prefix(trunk).filter(|s| !s.is_empty()) {
        return lengths
            .contains(&stripped.chars().count())
            .then(|| format!("+{cc}{stripped}"));
    }
    lengths
        .contains(&number.chars().count())
        .then(|| format!("+{cc}{number}"))
}

/// Canonical key for opt-out lookups: E.164 phone or lower-cased email.
pub fn contact_key(value: &str, default_cc: &str) -> String {
    let value = py_strip(value);
    if value.contains('@') {
        return value.to_lowercase();
    }
    normalize_phone(value, default_cc).unwrap_or_else(|| value.to_string())
}
