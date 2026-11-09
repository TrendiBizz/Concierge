//! Port of the pure parts of `owner_knowledge.py`: document validation, the case-folded identity of a title and the
//! document-id rule. Saving and deleting chunks stay in Python.
use crate::py_strip;
use crate::pydantic::{err, extras, FieldErr};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::sync::OnceLock;

pub const PREFIX: &str = "manual:owner:";

#[derive(Debug, PartialEq, Eq)]
pub struct Document {
    pub title: String,
    pub text: String,
}

/// `str.casefold()`: a per-character table generated from CPython (`casefold_table.json`, Python and Unicode versions
/// recorded inside). Rust's own `to_lowercase` is not the same function (`ß`, `ŉ`, `ǅ`, Cherokee, ...).
fn casefold_map() -> &'static HashMap<char, String> {
    static MAP: OnceLock<HashMap<char, String>> = OnceLock::new();
    MAP.get_or_init(|| {
        let v: Value = serde_json::from_str(include_str!("casefold_table.json")).unwrap();
        v["map"]
            .as_object()
            .unwrap()
            .iter()
            .map(|(k, v)| (k.chars().next().unwrap(), v.as_str().unwrap().to_string()))
            .collect()
    })
}

pub fn casefold(s: &str) -> String {
    let m = casefold_map();
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match m.get(&c) {
            Some(f) => out.push_str(f),
            None => out.push(c),
        }
    }
    out
}

/// sha256 hex of the case-folded title: the stable identity of an owner document.
pub fn identity(title: &str) -> String {
    Sha256::digest(casefold(title).as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// The `(label, text, title)` handed to `ingest_text` when a document is saved.
pub fn ingest_args(doc: &Document) -> (String, String, String) {
    (
        format!("owner:{}", identity(&doc.title)),
        doc.text.clone(),
        doc.title.clone(),
    )
}

/// `DOCUMENT_ID.fullmatch`: exactly 64 lowercase hex characters.
pub fn is_document_id(id: &str) -> bool {
    id.len() == 64
        && id
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

/// The `plain_text` validator.
fn plain_text(value: &str) -> Result<String, ()> {
    let v = value.replace("\r\n", "\n").replace('\r', "\n");
    let v = py_strip(&v);
    if v.is_empty() || v.chars().any(|c| (c as u32) < 32 && c != '\n' && c != '\t') {
        return Err(());
    }
    if v.len() > 100_000 {
        return Err(());
    }
    Ok(v.to_string())
}

/// `BusinessDocument.model_validate(body)`.
pub fn validate(body: &Value) -> Result<Document, Vec<FieldErr>> {
    let Some(map) = body.as_object() else {
        return Err(vec![err("", "model_type")]);
    };
    let mut errors = Vec::new();
    let mut field = |name: &str, max: usize| -> Option<String> {
        match map.get(name) {
            None => {
                errors.push(err(name, "missing"));
                None
            }
            Some(Value::String(s)) => {
                let n = s.chars().count();
                if n < 1 {
                    errors.push(err(name, "string_too_short"));
                    None
                } else if n > max {
                    errors.push(err(name, "string_too_long"));
                    None
                } else {
                    match plain_text(s) {
                        Ok(v) => Some(v),
                        Err(()) => {
                            errors.push(err(name, "value_error"));
                            None
                        }
                    }
                }
            }
            Some(_) => {
                errors.push(err(name, "string_type"));
                None
            }
        }
    };
    let title = field("title", 120);
    let text = field("text", 100_000);
    errors.extend(extras(map as &Map<String, Value>, &["title", "text"]));
    match (title, text) {
        (Some(title), Some(text)) if errors.is_empty() => Ok(Document { title, text }),
        _ => Err(errors),
    }
}
