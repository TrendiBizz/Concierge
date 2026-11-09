//! The Grok Voice session config the widget sends first (port of `voice.build_session` and `_extract_token`).
use crate::{rag, tools};
use chrono::{DateTime, Utc};
use serde_json::{json, Value};

const WEBSITE_SUFFIX: &str = "\nIf the caller asks for a text copy or recording link, save their contact and permission with capture_lead. Read back the saved recipient and requested format, wait for yes, then use request_conversation_copy. It arranges delivery after the conversation ends; never claim it was already sent. If recording is unavailable, offer saved text instead.";

pub fn build_session(
    tenant: &Value,
    website: bool,
    voice_default: &str,
    now: DateTime<Utc>,
) -> Value {
    let voice = tenant
        .get("voice")
        .and_then(Value::as_str)
        .filter(|v| !v.is_empty())
        .unwrap_or(voice_default);
    let mut instructions = rag::build_system_prompt(tenant, None, "voice", now);
    if website {
        instructions.push_str(WEBSITE_SUFFIX);
    }
    json!({
        "voice": voice,
        "instructions": instructions,
        "turn_detection": {"type": "server_vad"},
        "audio": {
            "input": {"format": {"type": "audio/pcm", "rate": 24000}, "transcription": {"model": "grok-transcribe"}},
            "output": {"format": {"type": "audio/pcm", "rate": 24000}},
        },
        "tools": tools::voice_tools(tenant, website),
    })
}

/// xAI does not document the token response shape, so the common variants are accepted, in the same order as Python.
pub fn extract_token(data: &Value) -> Option<String> {
    if let Some(v) = data.get("value").and_then(Value::as_str) {
        return Some(v.into());
    }
    match data.get("client_secret") {
        Some(Value::Object(o)) => {
            if let Some(v) = o.get("value").and_then(Value::as_str) {
                return Some(v.into());
            }
        }
        Some(Value::String(s)) => return Some(s.clone()),
        _ => {}
    }
    data.get("token")
        .and_then(Value::as_str)
        .map(str::to_string)
}
