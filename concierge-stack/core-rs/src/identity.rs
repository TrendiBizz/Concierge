//! Conservative message identity extraction, matching app/identity.py.
use crate::{contact::normalize_phone, py_strip, pyval::truncate_chars};
use regex::Regex;
use serde_json::{json, Value};
const _EMAIL: &str = r#"[\w.+-]+@[\w-]+\.[\w.-]{2,}"#;
const _PHONE: &str = r#"(?:\+\d{1,3}[\s-]?)?(?:\(?0\d{1,4}\)?[\s-]?)?\d{3,4}[\s-]?\d{3,4}"#;
const _NAME: &str = r#"\b(?i:my\s+name\s+is|i'?m|i\s+am|this\s+is|call\s+me|it'?s|name\s*:)\s+([A-Z][a-z'’-]+(?:\s+[A-Z][a-z'’-]+){0,2})\b"#;
const _COMPANY: &str = r#"\b(?:from|at|with)\s+([A-Z][\w&.'’-]*(?:\s+[A-Z][\w&.'’-]*){0,3}(?:\s+(?:Ltd|Limited|LLC|Inc|Group|Construction|Builders|Building|Plumbing|Electrical|Design|Studio|Agency|Consulting|Services|Solutions)))\b"#;
const _COMPANY_BARE: &str = r#"\b([A-Z][\w&.'’-]*(?:[ \t]+[A-Z][\w&.'’-]*){0,3}[ \t]+(?:Ltd|Limited|LLC|Inc|Group|Co|Company|Construction|Builders|Building|Plumbing|Electrical|Joinery|Roofing|Landscaping|Painting|Contracting|Contractors|Services|Solutions|Engineering|Design|Studio|Agency|Consulting|Enterprises|Holdings|Partners|Associates))\b"#;
fn clean_name(s: &str) -> String {
    let words: Vec<_> = s.split_whitespace().collect();
    let excluded="interested looking after sorry just having trying thinking wondering keen based working planning hoping writing following in on at the a an not sure new here good fine okay ok";
    if words.is_empty()
        || excluded
            .split_whitespace()
            .any(|w| w == words[0].to_lowercase())
        || !words
            .iter()
            .all(|w| w.chars().next().is_some_and(char::is_uppercase))
    {
        return String::new();
    }
    truncate_chars(&words.join(" "), 80)
}
pub fn extract_details(text: &str, cc: &str, allow_phone: bool) -> Value {
    let body = text.replace('\r', "");
    let mut out = json!({"name":"","email":"","phone":"","company":""});
    if py_strip(&body).is_empty() {
        return out;
    }
    if let Some(m) = Regex::new(_EMAIL).unwrap().find(&body) {
        out["email"] = json!(m
            .as_str()
            .trim_end_matches(['.', ',', ';', ':', ')', ']'])
            .to_lowercase())
    }
    if allow_phone {
        for m in Regex::new(_PHONE).unwrap().find_iter(&body) {
            let forbidden =
                |c: char| c == '/' || Regex::new(r"\d").unwrap().is_match(&c.to_string());
            if body[..m.start()].chars().next_back().is_some_and(forbidden)
                || body[m.end()..].chars().next().is_some_and(forbidden)
            {
                continue;
            }
            if let Some(n) = normalize_phone(m.as_str(), cc) {
                out["phone"] = json!(n);
                break;
            }
        }
    }
    if let Some(m) = Regex::new(_NAME).unwrap().captures(&body) {
        out["name"] = json!(clean_name(&m[1]))
    }
    if out["name"] == "" {
        if let Some(tail) = body
            .lines()
            .map(py_strip)
            .filter(|l| !l.is_empty())
            .next_back()
        {
            if tail.split_whitespace().count() <= 2
                && tail.chars().count() > 2
                && tail.chars().count() < 40
                && !tail.contains('@')
                && !tail.chars().any(char::is_numeric)
            {
                out["name"] = json!(clean_name(tail))
            }
        }
    }
    for pattern in [_COMPANY, _COMPANY_BARE] {
        if let Some(m) = Regex::new(pattern).unwrap().captures(&body) {
            out["company"] = json!(truncate_chars(&m[1], 120));
            break;
        }
    }
    out
}
