//! Port of `owner_onboarding.py`: validation of the owner's business profile (a pydantic model that forbids unknown
//! keys) and the website channel status. Saving, phone/SMS device state and activation stay in Python; nothing here
//! enables a channel.
use crate::pydantic::{err, extras, parse_bool, FieldErr};
use crate::pyurl::{hostname, port, urlsplit, userinfo, Fail};
use crate::{is_py_space, py_strip};
use regex::Regex;
use serde_json::{json, Map, Value};
use std::sync::OnceLock;

#[derive(Debug, PartialEq)]
pub enum Outcome {
    Errors(Vec<FieldErr>),
    /// The port declines to answer (the Python answer depends on something it does not reproduce).
    Unsupported(&'static str),
}

fn hhmm() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    R.get_or_init(|| Regex::new(r"^([01]\d|2[0-3]):[0-5]\d$").unwrap())
}
fn phone() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    R.get_or_init(|| Regex::new(r"^\+[1-9][0-9]{7,14}$").unwrap())
}

/// pydantic lax `int`: ints, integral floats, bools, and strings of digits (surrounding space and single underscores
/// between digits allowed).
fn parse_int(v: &Value) -> Result<i128, &'static str> {
    match v {
        Value::Bool(b) => Ok(*b as i128),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i as i128)
            } else if let Some(u) = n.as_u64() {
                Ok(u as i128)
            } else {
                let f = n.as_f64().unwrap();
                if f.is_finite() && f.fract() == 0.0 {
                    Ok(if f > 1e30 {
                        i128::MAX
                    } else if f < -1e30 {
                        i128::MIN
                    } else {
                        f as i128
                    })
                } else {
                    Err("int_from_float")
                }
            }
        }
        Value::String(s) => {
            let t = py_strip(s);
            let (neg, digits) = match t.strip_prefix('-') {
                Some(r) => (true, r),
                None => (false, t.strip_prefix('+').unwrap_or(t)),
            };
            let ok = !digits.is_empty()
                && !digits.starts_with('_')
                && !digits.ends_with('_')
                && !digits.contains("__")
                && digits.bytes().all(|b| b.is_ascii_digit() || b == b'_');
            if !ok {
                return Err("int_parsing");
            }
            let clean: String = digits.chars().filter(|c| *c != '_').collect();
            match clean.parse::<i128>() {
                Ok(n) => Ok(if neg { -n } else { n }),
                Err(_) => Err("int_parsing_size"),
            }
        }
        _ => Err("int_type"),
    }
}

fn hours(map: &Map<String, Value>, errors: &mut Vec<FieldErr>) -> Option<Value> {
    let v = map.get("business_hours")?;
    if v.is_null() {
        return None;
    }
    let Some(days) = v.as_object() else {
        errors.push(err("business_hours", "dict_type"));
        return None;
    };
    let mut typed: Vec<(&String, Vec<Vec<String>>)> = Vec::new();
    let mut type_errors = Vec::new();
    for (day, windows) in days {
        let Some(list) = windows.as_array() else {
            type_errors.push(FieldErr {
                loc: format!("business_hours.{day}"),
                ty: "list_type",
            });
            continue;
        };
        let mut out = Vec::new();
        for (i, w) in list.iter().enumerate() {
            let Some(pair) = w.as_array() else {
                type_errors.push(FieldErr {
                    loc: format!("business_hours.{day}.{i}"),
                    ty: "list_type",
                });
                continue;
            };
            let mut strs = Vec::new();
            for (j, x) in pair.iter().enumerate() {
                match x.as_str() {
                    Some(s) => strs.push(s.to_string()),
                    None => type_errors.push(FieldErr {
                        loc: format!("business_hours.{day}.{i}.{j}"),
                        ty: "string_type",
                    }),
                }
            }
            out.push(strs);
        }
        typed.push((day, out));
    }
    if !type_errors.is_empty() {
        errors.extend(type_errors);
        return None;
    }
    // hours_safe
    let invalid = |errors: &mut Vec<FieldErr>| {
        errors.push(err("business_hours", "value_error"));
        None
    };
    if typed.len() > 7 {
        return invalid(errors);
    }
    for (day, windows) in &typed {
        if !["mon", "tue", "wed", "thu", "fri", "sat", "sun"].contains(&day.as_str())
            || windows.len() > 4
        {
            return invalid(errors);
        }
        let mut sorted = windows.clone();
        sorted.sort();
        let mut last = String::new();
        for w in &sorted {
            if w.len() != 2 || !w.iter().all(|x| hhmm().is_match(x)) || w[0] >= w[1] || w[0] < last
            {
                return invalid(errors);
            }
            last = w[1].clone();
        }
    }
    Some(v.clone())
}

fn text<'a>(
    map: &'a Map<String, Value>,
    name: &str,
    max: usize,
    errors: &mut Vec<FieldErr>,
) -> Option<&'a str> {
    match map.get(name) {
        None | Some(Value::Null) => None,
        Some(Value::String(s)) => {
            if s.chars().count() > max {
                errors.push(err(name, "string_too_long"));
                None
            } else {
                Some(s)
            }
        }
        Some(_) => {
            errors.push(err(name, "string_type"));
            None
        }
    }
}

fn valid_timezone(name: &str) -> bool {
    // tzdata also ships the placeholder zone "Factory", which chrono-tz omits
    !name.is_empty() && (name == "Factory" || name.parse::<chrono_tz::Tz>().is_ok())
}

/// `OwnerBusinessProfile.model_validate(body).model_dump(exclude_unset=True, exclude_none=True)`.
pub fn validate(body: &Value) -> Result<Value, Outcome> {
    let Some(map) = body.as_object() else {
        return Err(Outcome::Errors(vec![err("", "model_type")]));
    };
    let mut errors: Vec<FieldErr> = Vec::new();
    let mut out = Map::new();
    for name in ["email_auto_reply", "voice_enabled", "native_booking"] {
        match map.get(name) {
            None | Some(Value::Null) => {}
            Some(v) => match parse_bool(v) {
                Ok(b) => {
                    out.insert(name.into(), json!(b));
                }
                Err(t) => errors.push(err(name, t)),
            },
        }
    }
    match map.get("slot_minutes") {
        None | Some(Value::Null) => {}
        Some(v) => match parse_int(v) {
            Ok(n) if n < 5 => errors.push(err("slot_minutes", "greater_than_equal")),
            Ok(n) if n > 240 => errors.push(err("slot_minutes", "less_than_equal")),
            Ok(n) => {
                out.insert("slot_minutes".into(), json!(n as i64));
            }
            Err("int_parsing_size") => return Err(Outcome::Unsupported("huge integer text")),
            Err(t) => errors.push(err("slot_minutes", t)),
        },
    }
    if let Some(h) = hours(map, &mut errors) {
        out.insert("business_hours".into(), h);
    }
    // name
    match map.get("name") {
        None | Some(Value::Null) => {}
        Some(Value::String(s)) => {
            let n = s.chars().count();
            if n < 1 {
                errors.push(err("name", "string_too_short"));
            } else if n > 160 {
                errors.push(err("name", "string_too_long"));
            } else {
                let v = py_strip(s);
                if v.is_empty() || v.chars().any(|c| (c as u32) < 32) {
                    errors.push(err("name", "value_error"));
                } else {
                    out.insert("name".into(), json!(v));
                }
            }
        }
        Some(_) => errors.push(err("name", "string_type")),
    }
    // site_url
    if let Some(raw) = text(map, "site_url", 2048, &mut errors) {
        let v = py_strip(raw);
        if v.is_empty() {
            out.insert("site_url".into(), json!(""));
        } else {
            match urlsplit(v, "") {
                Err(Fail::Unsupported(r)) => return Err(Outcome::Unsupported(r)),
                Err(Fail::Value) => errors.push(err("site_url", "value_error")),
                Ok(u) => {
                    let host = hostname(&u.netloc);
                    let (user, pass) = userinfo(&u.netloc);
                    let bad = u.scheme != "https"
                        || host.as_deref().is_none_or(|h| !h.contains('.'))
                        || user.is_some_and(|x| !x.is_empty())
                        || pass.is_some_and(|x| !x.is_empty())
                        || !u.fragment.is_empty()
                        || v.chars().any(|c| is_py_space(c) || (c as u32) < 32)
                        || port(&u.netloc).is_err();
                    if bad {
                        errors.push(err("site_url", "value_error"));
                    } else {
                        out.insert("site_url".into(), json!(v));
                    }
                }
            }
        }
    }
    if let Some(g) = text(map, "greeting", 500, &mut errors) {
        if g.chars().any(|c| (c as u32) < 32 && c != '\n' && c != '\t') {
            errors.push(err("greeting", "value_error"));
        } else {
            out.insert("greeting".into(), json!(py_strip(g)));
        }
    }
    if let Some(p) = text(map, "notify_phone", 16, &mut errors) {
        if p.is_empty() {
            out.insert("notify_phone".into(), json!(""));
        } else {
            let v = py_strip(p);
            if phone().is_match(v) {
                out.insert("notify_phone".into(), json!(v));
            } else {
                errors.push(err("notify_phone", "value_error"));
            }
        }
    }
    if let Some(e) = text(map, "notify_email", 254, &mut errors) {
        let a = py_strip(e).to_lowercase();
        if a.is_empty() {
            out.insert("notify_email".into(), json!(""));
        } else {
            let ok = a.matches('@').count() == 1 && !a.chars().any(is_py_space) && {
                let (local, domain) = a.split_once('@').unwrap();
                !local.is_empty()
                    && !domain.is_empty()
                    && domain.contains('.')
                    && !domain.starts_with('.')
                    && !domain.ends_with('.')
            };
            if ok {
                out.insert("notify_email".into(), json!(a));
            } else {
                errors.push(err("notify_email", "value_error"));
            }
        }
    }
    if let Some(z) = text(map, "timezone", 100, &mut errors) {
        if valid_timezone(z) {
            out.insert("timezone".into(), json!(z));
        } else {
            errors.push(err("timezone", "value_error"));
        }
    }
    errors.extend(extras(
        map,
        &[
            "email_auto_reply",
            "voice_enabled",
            "native_booking",
            "slot_minutes",
            "business_hours",
            "name",
            "site_url",
            "greeting",
            "notify_phone",
            "notify_email",
            "timezone",
        ],
    ));
    if errors.is_empty() {
        Ok(Value::Object(out))
    } else {
        Err(Outcome::Errors(errors))
    }
}

/// `website_channel_status`: configured/verified flags for website chat and voice.
pub fn website_channel_status(
    slug: Option<&str>,
    site_url: Option<&str>,
    voice_enabled: bool,
    verified_csv: &str,
    effective_llm_key: &str,
    xai_api_key: &str,
) -> Value {
    let verified = slug.is_some_and(|s| {
        verified_csv
            .split(',')
            .map(py_strip)
            .any(|v| !v.is_empty() && v == s)
    });
    let chat = site_url.is_some_and(|u| !u.is_empty()) && !effective_llm_key.is_empty();
    let voice = voice_enabled && !xai_api_key.is_empty();
    json!({"website_chat": {"configured": chat, "verified": chat && verified},
           "website_voice": {"configured": voice, "verified": voice && verified}})
}
