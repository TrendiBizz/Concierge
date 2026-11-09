//! The slice of pydantic v2 (lax mode, Python input) the Concierge request models rely on: bool parsing, string
//! constraints, literal and pattern checks, `extra="forbid"`. Error kinds use pydantic's own `type` names so they can be
//! compared with the Python originals one for one.
use serde_json::{Map, Value};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FieldErr {
    pub loc: String,
    pub ty: &'static str,
}

pub fn err(loc: &str, ty: &'static str) -> FieldErr {
    FieldErr {
        loc: loc.into(),
        ty,
    }
}

/// Errors as the `[[loc, type], ...]` JSON the parity vectors use.
pub fn errors_json(errors: &[FieldErr]) -> Value {
    Value::Array(
        errors
            .iter()
            .map(|e| Value::Array(vec![e.loc.clone().into(), e.ty.into()]))
            .collect(),
    )
}

/// pydantic lax `bool`: real bools, `0`/`1` (int or float), and the case-insensitive words pydantic accepts.
pub fn parse_bool(v: &Value) -> Result<bool, &'static str> {
    match v {
        Value::Bool(b) => Ok(*b),
        Value::String(s) => match s.to_lowercase().as_str() {
            "0" | "off" | "f" | "false" | "n" | "no" => Ok(false),
            "1" | "on" | "t" | "true" | "y" | "yes" => Ok(true),
            _ => Err("bool_parsing"),
        },
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                return match i {
                    0 => Ok(false),
                    1 => Ok(true),
                    _ => Err("bool_parsing"),
                };
            }
            match n.as_f64() {
                Some(0.0) => Ok(false),
                Some(1.0) => Ok(true),
                // pydantic reports any other float as the wrong type, not as an unparsable value
                _ => Err("bool_type"),
            }
        }
        _ => Err("bool_type"),
    }
}

/// `Literal[...]` over strings.
pub fn literal<'a>(v: &Value, allowed: &[&'a str]) -> Result<&'a str, &'static str> {
    match v {
        Value::String(s) => allowed
            .iter()
            .copied()
            .find(|a| *a == s)
            .ok_or("literal_error"),
        _ => Err("literal_error"),
    }
}

/// Keys of `data` that are not in `known`, in input order (what `extra="forbid"` reports).
pub fn extras(data: &Map<String, Value>, known: &[&str]) -> Vec<FieldErr> {
    data.keys()
        .filter(|k| !known.contains(&k.as_str()))
        .map(|k| FieldErr {
            loc: k.clone(),
            ty: "extra_forbidden",
        })
        .collect()
}
