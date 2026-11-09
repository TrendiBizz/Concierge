//! Port of the request models in `managed_phone.py` (`PhoneSetup`) and `mobile_connections.py` (`MobileConnection`).
//! Both forbid unknown keys and require E.164 numbers; nothing here stores or activates a number.
use crate::pydantic::{err, extras, literal, FieldErr};
use regex::Regex;
use serde_json::{json, Map, Value};
use std::sync::OnceLock;

fn e164() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    // pydantic compiles `pattern` with the Rust regex engine, so this is the same engine and the same `\d`.
    RE.get_or_init(|| Regex::new(r"^\+[1-9]\d{6,14}$").unwrap())
}

fn number(map: &Map<String, Value>, name: &str, errors: &mut Vec<FieldErr>) -> Option<String> {
    match map.get(name) {
        None => {
            errors.push(err(name, "missing"));
            None
        }
        Some(Value::String(s)) if e164().is_match(s) => Some(s.clone()),
        Some(Value::String(_)) => {
            errors.push(err(name, "string_pattern_mismatch"));
            None
        }
        Some(_) => {
            errors.push(err(name, "string_type"));
            None
        }
    }
}

fn choice(
    map: &Map<String, Value>,
    name: &str,
    allowed: &[&'static str],
    default: &'static str,
    errors: &mut Vec<FieldErr>,
) -> Option<&'static str> {
    match map.get(name) {
        None => Some(default),
        Some(v) => match literal(v, allowed) {
            Ok(c) => Some(c),
            Err(t) => {
                errors.push(err(name, t));
                None
            }
        },
    }
}

/// `PhoneSetup.model_validate(body)`, dumped as the model's JSON.
pub fn validate_setup(body: &Value) -> Result<Value, Vec<FieldErr>> {
    let Some(map) = body.as_object() else {
        return Err(vec![err("", "model_type")]);
    };
    let mut errors = Vec::new();
    let designated = number(map, "designated_number", &mut errors);
    let connection = choice(
        map,
        "connection",
        &["existing_sip", "existing_twilio", "mobile_forwarding"],
        "mobile_forwarding",
        &mut errors,
    );
    let mode = choice(
        map,
        "answer_mode",
        &["all_calls", "unanswered"],
        "unanswered",
        &mut errors,
    );
    let owner = number(map, "owner_number", &mut errors);
    errors.extend(extras(
        map,
        &[
            "designated_number",
            "connection",
            "answer_mode",
            "owner_number",
        ],
    ));
    match (designated, connection, mode, owner) {
        (Some(d), Some(c), Some(m), Some(o)) if errors.is_empty() => Ok(
            json!({"designated_number": d, "connection": c, "answer_mode": m, "owner_number": o}),
        ),
        _ => Err(errors),
    }
}

/// `MobileConnection.model_validate(body)`, dumped as the model's JSON.
pub fn validate_mobile(body: &Value) -> Result<Value, Vec<FieldErr>> {
    let Some(map) = body.as_object() else {
        return Err(vec![err("", "model_type")]);
    };
    let mut errors = Vec::new();
    let destination = number(map, "destination", &mut errors);
    let carrier = choice(map, "carrier", &["spark_nz", "other"], "other", &mut errors);
    errors.extend(extras(map, &["destination", "carrier"]));
    match (destination, carrier) {
        (Some(d), Some(c)) if errors.is_empty() => Ok(json!({"destination": d, "carrier": c})),
        _ => Err(errors),
    }
}
