//! Port of `channel_authorization.py` (validation, readiness report, channel allow-list). The database halves stay in
//! Python. Storing an authorization never activates a provider: every report keeps `provider_verified`/`active` false.
use crate::pydantic::{err, literal, parse_bool, FieldErr};
use crate::pyval::truthy;
use serde_json::{json, Map, Value};

pub const CHANNELS: [&str; 7] = [
    "telephone",
    "call_recording",
    "email_read",
    "email_send",
    "sms_read",
    "sms_send",
    "social",
];

#[derive(Debug, PartialEq, Eq)]
pub struct Authorization {
    pub channel: &'static str,
    pub authorized: bool,
    pub acknowledgement: bool,
}

/// `ChannelAuthorization.model_validate(body)`. `extra` keys are ignored, as pydantic's default does for this model.
pub fn validate(body: &Value) -> Result<Authorization, Vec<FieldErr>> {
    let Some(map) = body.as_object() else {
        return Err(vec![err("", "model_type")]);
    };
    let mut errors = Vec::new();
    let channel = match map.get("channel") {
        None => {
            errors.push(err("channel", "missing"));
            None
        }
        Some(v) => match literal(v, &CHANNELS) {
            Ok(c) => Some(c),
            Err(t) => {
                errors.push(err("channel", t));
                None
            }
        },
    };
    let mut flag = |name: &str| match map.get(name) {
        None => {
            errors.push(err(name, "missing"));
            None
        }
        Some(v) => match parse_bool(v) {
            Ok(b) => Some(b),
            Err(t) => {
                errors.push(err(name, t));
                None
            }
        },
    };
    let authorized = flag("authorized");
    let acknowledgement = flag("acknowledgement");
    match (channel, authorized, acknowledgement) {
        (Some(channel), Some(authorized), Some(acknowledgement)) if errors.is_empty() => {
            Ok(Authorization {
                channel,
                authorized,
                acknowledgement,
            })
        }
        _ => Err(errors),
    }
}

/// The guard at the top of `record_authorization`.
pub fn check_record(a: &Authorization) -> Result<(), &'static str> {
    if a.authorized && !a.acknowledgement {
        return Err("Explicit authorization acknowledgement required");
    }
    Ok(())
}

/// The value `record_authorization` returns once the row is stored.
pub fn record_response(channel: &str, stored_authorized: bool, updated_at: Value) -> Value {
    json!({"channel": channel, "authorized": stored_authorized, "updated_at": updated_at,
           "provider_verified": false, "active": false})
}

/// `is_authorized` fails closed for a channel that is not on the list, whatever is stored.
pub fn is_authorized(channel: &str, stored: bool) -> bool {
    CHANNELS.contains(&channel) && stored
}

/// `readiness(channels, checks)`: never activates from owner claims alone.
pub fn readiness(channels: &Map<String, Value>, checks: &Map<String, Value>) -> Value {
    let mut out = Map::new();
    for (key, value) in channels {
        let authorized = truthy(value.get("authorized"));
        let configured = truthy(checks.get(key));
        let mut missing: Vec<&str> = Vec::new();
        if !authorized {
            missing.push("owner_authorization");
        }
        if !configured {
            missing.push("provider_configuration");
        }
        missing.push("real_provider_verification");
        missing.push("operator_activation");
        out.insert(
            key.clone(),
            json!({"authorized": authorized, "configured": configured, "provider_verified": false,
                   "active": false, "missing": missing}),
        );
    }
    Value::Object(out)
}
