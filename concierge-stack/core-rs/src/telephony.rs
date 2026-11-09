//! Telephony rules (port of the pure parts of `phone_sip.py`, `phone_relay.py`, `managed_phone.py`, `mobile_connections.py`
//! and `tenants.slugify`): webhook verification, number parsing, TwiML and forwarding instructions.
use crate::py_strip;
use crate::sms;
use base64::{engine::general_purpose::STANDARD, Engine};
use hmac::{Hmac, Mac};
use regex::Regex;
use serde_json::{json, Value};
use sha2::Sha256;
use std::sync::OnceLock;
use subtle::ConstantTimeEq;

fn eq_ct(a: &str, b: &str) -> bool {
    a.len() == b.len() && bool::from(a.as_bytes().ct_eq(b.as_bytes()))
}

/// Standard-Webhooks style check used for xAI SIP calls (`phone_sip.valid_signature`): `whsec_<base64 key>`, an id, a
/// timestamp within 300 s, and any `v1,<base64 HMAC-SHA256>` in the signature header. A timestamp that Python's `int()`
/// accepts but this port does not (underscores) is refused.
pub fn sip_signature_valid(
    secret: &str,
    body: &[u8],
    webhook_id: &str,
    timestamp: &str,
    signatures: &str,
    now: f64,
) -> bool {
    let Some(encoded) = secret.strip_prefix("whsec_") else {
        return false;
    };
    let Ok(key) = STANDARD.decode(encoded) else {
        return false;
    };
    if key.len() < 24 || webhook_id.is_empty() || webhook_id.chars().count() > 200 {
        return false;
    }
    let Ok(stamp) = py_strip(timestamp).parse::<i64>() else {
        return false;
    };
    if (now - stamp as f64).abs() > 300.0 {
        return false;
    }
    let mut mac = Hmac::<Sha256>::new_from_slice(&key).expect("any key length");
    mac.update(webhook_id.as_bytes());
    mac.update(b".");
    mac.update(timestamp.as_bytes());
    mac.update(b".");
    mac.update(body);
    let expected = STANDARD.encode(mac.finalize().into_bytes());
    for part in signatures
        .split_whitespace()
        .filter(|p| p.starts_with("v1,"))
    {
        if !part.is_ascii() {
            return false; // Python's compare_digest raises on non-ASCII text, which the caller treats as invalid
        }
        if eq_ct(&part[3..], &expected) {
            return true;
        }
    }
    false
}

/// Python `str(x)` for the JSON shapes a header name can take; a missing key is Python's default `""`. Floats and containers
/// have reprs this port does not reproduce, so they never match.
fn py_str(v: Option<&Value>) -> Option<String> {
    match v {
        None => Some(String::new()),
        Some(Value::Null) => Some("None".into()),
        Some(Value::Bool(b)) => Some(if *b { "True" } else { "False" }.into()),
        Some(Value::String(s)) => Some(s.clone()),
        Some(Value::Number(n)) if n.is_i64() || n.is_u64() => Some(n.to_string()),
        _ => None,
    }
}

/// `phone_sip.header_number`: exactly one header of that name holding exactly one `+<7-15 digits>` number, else "".
pub fn header_number(headers: &Value, name: &str) -> String {
    let values: Vec<&Value> = headers
        .as_array()
        .into_iter()
        .flatten()
        .filter(|h| {
            h.is_object()
                && py_str(h.get("name")).is_some_and(|n| n.to_lowercase() == name.to_lowercase())
        })
        .map(|h| h.get("value").unwrap_or(&Value::Null))
        .collect();
    if values.len() != 1 {
        return String::new();
    }
    let Some(text) = values[0]
        .as_str()
        .or(if values[0].is_null() { Some("") } else { None })
    else {
        return String::new();
    };
    let chars: Vec<char> = text.chars().collect();
    let mut found = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        if chars[i] == '+' {
            let mut j = i + 1;
            while j < chars.len() && chars[j].is_ascii_digit() {
                j += 1;
            }
            let digits = j - i - 1;
            if (7..=15).contains(&digits) && chars[i + 1] != '0' {
                found.push(chars[i..j].iter().collect::<String>());
                i = j;
                continue;
            }
        }
        i += 1;
    }
    if found.len() == 1 {
        found.remove(0)
    } else {
        String::new()
    }
}

// ---- Twilio relay -------------------------------------------------------------------------------------------------------
fn re(cell: &'static OnceLock<Regex>, pattern: &str) -> &'static Regex {
    cell.get_or_init(|| Regex::new(pattern).unwrap())
}

pub fn is_call_sid(s: &str) -> bool {
    static R: OnceLock<Regex> = OnceLock::new();
    re(&R, r"^CA[0-9a-fA-F]{32}$").is_match(s)
}
pub fn is_recording_sid(s: &str) -> bool {
    static R: OnceLock<Regex> = OnceLock::new();
    re(&R, r"^RE[0-9a-fA-F]{32}$").is_match(s)
}
pub fn is_e164(s: &str) -> bool {
    static R: OnceLock<Regex> = OnceLock::new();
    re(&R, r"^\+[1-9][0-9]{6,14}$").is_match(s)
}
pub fn is_recording_consent(s: &str) -> bool {
    static R: OnceLock<Regex> = OnceLock::new();
    re(
        &R,
        r"(?i)^(?:yes[,]?[ ]+)?i consent to (?:this )?(?:call )?recording[.!]?$",
    )
    .is_match(s)
}

/// `phone_relay.external_url`: HTTPS only; WebSocket URLs swap the scheme for `wss://`.
pub fn external_url(
    public_base_url: &str,
    path: &str,
    websocket: bool,
) -> Result<String, &'static str> {
    let base = public_base_url.trim_end_matches('/');
    let Some(rest) = base.strip_prefix("https://") else {
        return Err("Public HTTPS URL required for telephone reception");
    };
    Ok(if websocket {
        format!("wss://{rest}{path}")
    } else {
        format!("{base}{path}")
    })
}

/// `valid_websocket_signature`: Twilio may or may not sign a trailing slash. A non-HTTPS base is simply invalid here.
pub fn valid_websocket_signature(auth_token: &str, public_base_url: &str, signature: &str) -> bool {
    if auth_token.is_empty() || signature.is_empty() {
        return false;
    }
    let Ok(url) = external_url(public_base_url, "/api/v1/phone/relay", true) else {
        return false;
    };
    sms::validate_signature(auth_token, &url, &[], signature)
        || sms::validate_signature(auth_token, &format!("{url}/"), &[], signature)
}

/// `xml.sax.saxutils.escape(text, {'"': '&quot;'})`.
pub fn xml_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

pub fn twiml(
    business: &str,
    recording_offer: bool,
    public_base_url: &str,
) -> Result<String, &'static str> {
    let ws = xml_escape(&external_url(public_base_url, "/api/v1/phone/relay", true)?);
    let action = xml_escape(&external_url(
        public_base_url,
        "/api/v1/phone/twilio/ended",
        false,
    )?);
    let mut greeting = format!("Hello, you've reached {business}'s automated receptionist. This call may be transcribed to answer your enquiry. ");
    if recording_offer {
        greeting.push_str("Recording is optional. To record this call, say exactly 'I consent to recording' as your first response. Otherwise, just tell me how I can help and this call will not be recorded.");
    } else {
        greeting.push_str("How can I help?");
    }
    Ok(format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Connect action=\"{action}\" method=\"POST\"><ConversationRelay url=\"{ws}\" welcomeGreeting=\"{}\" echoPromptFiltering=\"true\" language=\"en-US\" /></Connect></Response>",
        xml_escape(&greeting)
    ))
}

/// ElementTree attribute escaping (`_escape_attrib`).
fn attr(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\r', "&#13;")
        .replace('\n', "&#10;")
        .replace('\t', "&#09;")
}
fn cdata(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

/// `managed_phone.sip_twiml`, serialised exactly as ElementTree does.
pub fn sip_twiml(username: &str, password: &str, number: &str) -> String {
    format!(
        "<Response><Dial answerOnBridge=\"true\" timeout=\"30\" timeLimit=\"600\"><Sip username=\"{}\" password=\"{}\">{}</Sip></Dial><Hangup /></Response>",
        attr(username),
        attr(password),
        cdata(&format!("sip:{number}@sip.voice.x.ai;transport=tls"))
    )
}

/// `mobile_connections.forwarding_steps`: Spark's published diversion codes, dialled only by the owner.
pub fn forwarding_steps(destination: &str, carrier: &str, mode: &str) -> Vec<Value> {
    if carrier != "spark_nz" {
        return vec![
            json!({"label": format!("Set call forwarding with your mobile carrier to {destination}"), "destination": destination}),
        ];
    }
    let modes: Vec<(&str, &str)> = if mode == "all_calls" {
        vec![("Forward all calls", "21")]
    } else {
        vec![
            ("Forward unanswered calls", "61"),
            ("Forward busy calls", "67"),
        ]
    };
    modes.into_iter().map(|(label, code)| json!({"label": label, "dial": format!("*{code}*{destination}*11#"), "check": format!("*#{code}*11#")})).collect()
}

/// `tenants.slugify`.
pub fn slugify(name: &str) -> String {
    let mut out = String::new();
    let mut pending = false;
    for c in name.to_lowercase().chars() {
        if c.is_ascii_lowercase() || c.is_ascii_digit() {
            if pending && !out.is_empty() {
                out.push('-');
            }
            pending = false;
            out.push(c);
        } else {
            pending = true;
        }
    }
    let cut: String = out.chars().take(80).collect();
    let slug = cut.trim_end_matches('-');
    if slug.is_empty() {
        "tenant".into()
    } else {
        slug.into()
    }
}
