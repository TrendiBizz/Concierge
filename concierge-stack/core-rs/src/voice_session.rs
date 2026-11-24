//! Google Gemini 3.8 Live voice session builder (port of `voice.build_session` and `_extract_token`).
use crate::{rag, tools};
use chrono::{DateTime, Utc};
use serde_json::{json, Value};

const WEBSITE_SUFFIX: &str = "\nIf the caller asks for a text copy or recording link, save their contact and permission with capture_lead. Read back the saved recipient and requested format, wait for yes, then use request_conversation_copy. It arranges delivery after the conversation ends; never claim it was already sent. If recording is unavailable, offer saved text instead.";

const GEMINI_VOICES: &[&str] = &[
    "Aoede", "Charon", "Fenrir", "Kore", "Puck", "Leda", "Orus", "Zephyr",
];

pub fn resolve_voice_name<'a>(requested: Option<&'a str>, fallback: &'a str) -> &'a str {
    if let Some(r) = requested {
        if GEMINI_VOICES.contains(&r) {
            return r;
        }
    }
    if GEMINI_VOICES.contains(&fallback) {
        return fallback;
    }
    "Aoede"
}

pub fn build_session(
    tenant: &Value,
    website: bool,
    voice_default: &str,
    now: DateTime<Utc>,
) -> Value {
    let voice = resolve_voice_name(tenant.get("voice").and_then(Value::as_str), voice_default);
    let mut instructions = rag::build_system_prompt(tenant, None, "voice", now);
    if website {
        instructions.push_str(WEBSITE_SUFFIX);
    }
    json!({
        "model": "models/gemini-3.8-live",
        "voice": voice,
        "gemini_voice": voice,
        "thinking_level": "",
        "instructions": instructions,
        "tools": tools::voice_tools(tenant, website),
    })
}

/// Extract the ephemeral token name returned by Google's `v1alpha/auth_tokens`.
pub fn extract_token(data: &Value) -> Option<String> {
    if let Some(v) = data.get("name").and_then(Value::as_str).map(str::trim).filter(|s| !s.is_empty()) {
        return Some(v.into());
    }
    data.get("token")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
}
