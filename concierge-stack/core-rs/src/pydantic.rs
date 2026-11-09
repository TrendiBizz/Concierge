//! The slice of pydantic v2 (lax mode, Python input) the Concierge request models rely on: bool parsing, string
//! constraints, literal and pattern checks, `extra="forbid"`. Error kinds use pydantic's own `type` names so they can be
//! compared with the Python originals one for one.
use crate::py_strip;
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

/// pydantic lax `int`: ints, integral floats, bools, and strings of digits (surrounding space and single underscores
/// between digits allowed).
pub fn parse_int(v: &Value) -> Result<i128, &'static str> {
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
            // "5.0" and "5.000" are accepted; "5.", "5.5" and exponents are not
            let digits = match digits.split_once('.') {
                Some((int, frac)) if !frac.is_empty() && frac.bytes().all(|b| b == b'0') => int,
                Some(_) => return Err("int_parsing"),
                None => digits,
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
