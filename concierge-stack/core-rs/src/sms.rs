//! SMS provider rules and webhook verification (port of the pure parts of `sms.py`).
use crate::py_strip;
use crate::pyval::truncate_chars;
use base64::{engine::general_purpose::STANDARD, Engine};
use hmac::{Hmac, Mac};
use serde_json::{json, Value};
use sha1::Sha1;
use sha2::Sha256;
use subtle::ConstantTimeEq;

fn eq_ct(a: &str, b: &str) -> bool {
    a.len() == b.len() && bool::from(a.as_bytes().ct_eq(b.as_bytes()))
}

/// Twilio `X-Twilio-Signature`: base64 HMAC-SHA1 of the URL followed by each POST parameter (sorted by name) as name+value.
/// Python's `compare_digest` raises on non-ASCII text; here such a signature simply fails.
pub fn validate_signature(
    auth_token: &str,
    url: &str,
    params: &[(String, String)],
    signature: &str,
) -> bool {
    let mut sorted: Vec<&(String, String)> = params.iter().collect();
    sorted.sort_by(|a, b| a.0.cmp(&b.0));
    let mut data = url.to_string();
    for (k, v) in sorted {
        data.push_str(k);
        data.push_str(v);
    }
    let mut mac = Hmac::<Sha1>::new_from_slice(auth_token.as_bytes()).expect("any key length");
    mac.update(data.as_bytes());
    let expected = STANDARD.encode(mac.finalize().into_bytes());
    signature.is_ascii() && eq_ct(&expected, signature)
}

/// Body of a request to the self-hosted Android gateway.
pub fn smsgate_payload(to_e164: &str, body: &str, sim_number: i64) -> Value {
    let mut p =
        json!({"textMessage": {"text": truncate_chars(body, 1500)}, "phoneNumbers": [to_e164]});
    if matches!(sim_number, 1..=3) {
        p["simNumber"] = json!(sim_number);
    }
    p
}

/// Gateway webhook: HMAC-SHA256 (hex) over the raw body followed by the timestamp text, keyed by the signing key; stale
/// timestamps are refused. A timestamp that Python's `int()` accepts but this port does not (underscores) is refused.
pub fn validate_smsgate_signature(
    signing_key: &str,
    raw_body: &[u8],
    timestamp: &str,
    signature: &str,
    now: f64,
    tolerance_seconds: i64,
) -> bool {
    if signing_key.is_empty() || timestamp.is_empty() || signature.is_empty() {
        return false;
    }
    let Ok(ts) = py_strip(timestamp).parse::<i64>() else {
        return false;
    };
    if (now - ts as f64).abs() > tolerance_seconds as f64 {
        return false;
    }
    let mut mac = Hmac::<Sha256>::new_from_slice(signing_key.as_bytes()).expect("any key length");
    mac.update(raw_body);
    mac.update(timestamp.as_bytes());
    let expected: String = mac
        .finalize()
        .into_bytes()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    let given = py_strip(signature).to_lowercase();
    given.is_ascii() && eq_ct(&expected, &given)
}

#[derive(Default)]
pub struct Settings<'a> {
    pub provider: &'a str,
    pub twilio_account_sid: &'a str,
    pub twilio_auth_token: &'a str,
    pub twilio_messaging_service_sid: &'a str,
    pub twilio_from_number: &'a str,
    pub smsgate_base_url: &'a str,
    pub smsgate_username: &'a str,
    pub smsgate_password: &'a str,
}

#[derive(Default)]
pub struct TenantSms<'a> {
    pub transport: &'a str,
    pub enabled: bool,
    pub from: &'a str,
}

/// `sender_ready`: does the configured provider have everything it needs for this tenant?
pub fn sender_ready(s: &Settings, tenant: Option<&TenantSms>) -> bool {
    let default = TenantSms::default();
    let t = tenant.unwrap_or(&default);
    if t.transport == "device" {
        return t.enabled && !t.from.is_empty();
    }
    let provider = py_strip(if s.provider.is_empty() {
        "none"
    } else {
        s.provider
    })
    .to_lowercase();
    match provider.as_str() {
        "twilio" => {
            let has_sender = !s.twilio_messaging_service_sid.is_empty()
                || !t.from.is_empty()
                || !s.twilio_from_number.is_empty();
            !s.twilio_account_sid.is_empty() && !s.twilio_auth_token.is_empty() && has_sender
        }
        "smsgate" => {
            !s.smsgate_base_url.is_empty()
                && !s.smsgate_username.is_empty()
                && !s.smsgate_password.is_empty()
        }
        _ => false,
    }
}
