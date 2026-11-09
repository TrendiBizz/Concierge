//! Port of the decision flow in `acknowledgements.py`: the optional enquirer acknowledgement. Every database step is a
//! `Store` call, so the Python fake-database effects can be compared one for one. Nothing is sent here: the flow only
//! ever asks to queue an outbox row, and only after a spoken confirmation and an owner-authorized channel.
use crate::contact::{is_email, normalize_phone};
use crate::py_strip;
use crate::pyjson;
use crate::pyval::{str_or_empty, truthy};
use serde_json::{json, Value};

pub struct Outbox<'a> {
    pub tenant_id: &'a str,
    pub channel: &'a str,
    pub recipient: &'a str,
    pub subject: String,
    pub body: String,
    pub dedupe_key: String,
    pub lead_id: &'a str,
}

pub trait Store {
    /// `UPDATE conversations SET pending_ack='{"declined":true}'`.
    fn decline(&mut self, tenant_id: &str, conversation_id: &str);
    /// `SELECT pending_ack ... FOR UPDATE`: `None` when there is no such conversation, else the stored value
    /// (`Some(Value::Null)` for SQL NULL, a JSON string for text the driver returns undecoded).
    fn lock_pending(&mut self, tenant_id: &str, conversation_id: &str) -> Option<Value>;
    /// `UPDATE conversations SET pending_ack=$3::jsonb`, with `json.dumps(key)` as the parameter.
    fn set_pending(&mut self, tenant_id: &str, conversation_id: &str, key_json: &str);
    fn is_authorized(&mut self, tenant_id: &str, channel: &str) -> bool;
    fn first_lead(&mut self, tenant_id: &str, conversation_id: &str) -> Option<String>;
    fn queue(&mut self, row: &Outbox);
}

/// The Python crashes or reprs this port does not reproduce are reported instead of guessed.
#[derive(Debug, PartialEq, Eq)]
pub struct Unsupported(pub &'static str);

pub fn request(
    store: &mut dyn Store,
    tenant_id: &str,
    tenant_name: &str,
    args: &Value,
    ctx: &Value,
) -> Result<Value, Unsupported> {
    if truthy(ctx.get("dry_run")) {
        return Ok(json!({"ok": true, "status": "dry_run", "note": "No acknowledgement queued"}));
    }
    let conversation_id = match ctx.get("conversation_id") {
        Some(Value::String(s)) if !s.is_empty() => s.clone(),
        v if !truthy(v) => {
            return Ok(json!({"ok": false, "error": "A saved conversation is required"}))
        }
        _ => return Err(Unsupported("non-string conversation id")),
    };
    let requested = args.get("requested");
    if requested == Some(&Value::Bool(false)) {
        store.decline(tenant_id, &conversation_id);
        return Ok(json!({"ok": true, "status": "declined",
            "note": "No enquirer acknowledgement will be sent. The owner enquiry remains separate."}));
    }
    if requested != Some(&Value::Bool(true)) {
        return Ok(
            json!({"ok": false, "error": "Ask whether the enquirer wants an acknowledgement first"}),
        );
    }
    let channel = match args.get("channel").and_then(Value::as_str) {
        Some(c @ ("email" | "sms")) => c,
        _ => {
            return Ok(
                json!({"ok": false, "error": "Ask which channel the enquirer wants: email or SMS"}),
            )
        }
    };
    let raw = str_or_empty(args.get("recipient")).ok_or(Unsupported("recipient repr"))?;
    let raw = py_strip(&raw);
    let recipient = if channel == "email" {
        Some(raw.to_lowercase())
    } else {
        normalize_phone(raw, "1")
    };
    let recipient = match recipient {
        Some(r) if !r.is_empty() && (channel != "email" || is_email(&r)) => r,
        _ => {
            return Ok(
                json!({"ok": false, "error": "A valid acknowledgement recipient is required"}),
            )
        }
    };
    let key = json!({"channel": channel, "recipient": recipient});
    let key_json = pyjson::dumps(&key).ok_or(Unsupported("key json"))?;
    let Some(stored) = store.lock_pending(tenant_id, &conversation_id) else {
        return Ok(json!({"ok": false, "error": "Conversation unavailable"}));
    };
    let pending = match stored {
        Value::String(text) => {
            serde_json::from_str::<Value>(&text).map_err(|_| Unsupported("undecodable pending"))?
        }
        other => other,
    };
    if args.get("confirmed") != Some(&Value::Bool(true)) || pending != key {
        store.set_pending(tenant_id, &conversation_id, &key_json);
        return Ok(json!({"ok": false, "needs_confirmation": true,
            "read_back": format!("Send an acknowledgement by {channel} to {recipient}? Wait for yes before confirming.")}));
    }
    let needed = if channel == "email" {
        "email_send"
    } else {
        "sms_send"
    };
    if !store.is_authorized(tenant_id, needed) {
        return Ok(
            json!({"ok": false, "error": "Business has not authorized that delivery channel"}),
        );
    }
    let Some(lead) = store.first_lead(tenant_id, &conversation_id) else {
        return Ok(
            json!({"ok": false, "error": "Save the enquiry before requesting an acknowledgement"}),
        );
    };
    store.queue(&Outbox {
        tenant_id,
        channel,
        recipient: &recipient,
        subject: format!("Your enquiry with {tenant_name}"),
        body: format!(
            "Thank you for contacting {tenant_name}. Your enquiry has been saved for the team to follow up."
        ),
        dedupe_key: format!("enquirer-ack:{tenant_id}:{conversation_id}:{channel}:{recipient}"),
        lead_id: &lead,
    });
    store.set_pending(tenant_id, &conversation_id, &key_json);
    Ok(
        json!({"ok": true, "status": "queued", "recipient": recipient,
        "note": "Acknowledgement queued; receipt has not been verified. Device SMS requires Send confirmation."}),
    )
}
