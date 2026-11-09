//! Email ingress rules (port of the pure parts of `cloudflare_inbound.py`, `inbound_email.py`, `enquiries.py` and
//! `email_drafts._address/_subject`): webhook authentication, payload validation, idempotency keys and what is stored.
use crate::contact::is_email;
use crate::py_strip;
use crate::pyval::truncate_chars;
use hmac::{Hmac, Mac};
use regex::Regex;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::sync::OnceLock;
use subtle::ConstantTimeEq;

pub const MAX_BYTES: usize = 30_000;

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}
pub fn sha256_hex(s: &str) -> String {
    hex(&Sha256::digest(s.as_bytes()))
}

fn address_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$").unwrap())
}
fn message_id_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[A-Za-z0-9._@:/+<>=-]{1,500}$").unwrap())
}

pub fn normalize_recipient(address: &str) -> Option<String> {
    let v = py_strip(address).to_lowercase();
    (v.chars().count() <= 320 && address_re().is_match(&v)).then_some(v)
}

/// `hex(HMAC-SHA256(secret, timestamp "." body))`.
pub fn signature(secret: &str, timestamp: &str, body: &[u8]) -> String {
    let mut m = Hmac::<Sha256>::new_from_slice(secret.as_bytes()).expect("any key length");
    m.update(timestamp.as_bytes());
    m.update(b".");
    m.update(body);
    hex(&m.finalize().into_bytes())
}

#[derive(Debug, PartialEq, Eq)]
pub struct Rejection {
    pub status: u16,
    pub detail: &'static str,
}
fn rej<T>(status: u16, detail: &'static str) -> Result<T, Rejection> {
    Err(Rejection { status, detail })
}

#[derive(Debug, PartialEq, Eq)]
pub struct Payload {
    pub message_id: String,
    pub recipient: String,
    pub sender: String,
    pub subject: String,
    pub text: String,
}

/// Everything `cloudflare_inbound.handle` does before it touches the database, in the same order and with the same
/// status codes. A timestamp using non-ASCII decimal digits (Python accepts) is refused.
pub fn verify_request(
    enabled: bool,
    secret: &str,
    timestamp: &str,
    supplied: &str,
    body: &[u8],
    now: i64,
) -> Result<Payload, Rejection> {
    if !enabled || secret.chars().count() < 32 {
        return rej(503, "Inbound email is disabled");
    }
    let sig_ok = supplied.len() == 64
        && supplied
            .bytes()
            .all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'));
    if timestamp.is_empty()
        || !timestamp.bytes().all(|b| b.is_ascii_digit())
        || timestamp.len() > 12
        || !sig_ok
    {
        return rej(401, "Invalid signature");
    }
    let ts: i64 = timestamp.parse().expect("at most 12 digits");
    if (now - ts).abs() > 300 {
        return rej(401, "Expired signature");
    }
    if body.len() > MAX_BYTES {
        return rej(413, "Email payload too large");
    }
    let expected = signature(secret, timestamp, body);
    if !bool::from(expected.as_bytes().ct_eq(supplied.as_bytes())) {
        return rej(401, "Invalid signature");
    }
    parse_payload(body).ok_or(Rejection {
        status: 400,
        detail: "Invalid email payload",
    })
}

fn parse_payload(body: &[u8]) -> Option<Payload> {
    let v: Value = serde_json::from_slice(body).ok()?;
    let obj = v.as_object()?;
    let mut keys: Vec<&str> = obj.keys().map(String::as_str).collect();
    keys.sort_unstable();
    if keys != ["message_id", "recipient", "sender", "subject", "text"] {
        return None;
    }
    let s = |k: &str| obj[k].as_str().map(str::to_string);
    let recipient = normalize_recipient(obj["recipient"].as_str()?)?;
    let (message_id, sender, subject, text) =
        (s("message_id")?, s("sender")?, s("subject")?, s("text")?);
    if sender.chars().count() > 320 || subject.chars().count() > 250 {
        return None;
    }
    Some(Payload {
        message_id,
        recipient,
        sender,
        subject,
        text,
    })
}

/// `email_drafts._address`: one valid address, no line breaks.
pub fn draft_address(value: &str) -> Option<String> {
    let a = py_strip(value);
    (is_email(a) && !a.contains(['\r', '\n'])).then(|| a.to_string())
}

/// `email_drafts._subject`: whitespace collapsed, 250 characters.
pub fn draft_subject(value: &str) -> String {
    truncate_chars(&value.split_whitespace().collect::<Vec<_>>().join(" "), 250)
}

/// What `inbound_email.ingest_verified` (+ `email_drafts.create`, `convo` and `enquiries`) store for one verified email.
#[derive(Debug, PartialEq, Eq)]
pub struct Ingest {
    pub source_key: String,
    pub draft_sender: String,
    pub draft_subject: String,
    pub draft_inbound_body: String,
    pub session_id: String,
    pub lead_message: String,
}

/// `None` where Python raises `InboundError` (every such case is a 400).
pub fn ingest_plan(
    provider: &str,
    message_id: &str,
    sender: &str,
    recipient: &str,
    subject: &str,
    text: &str,
) -> Option<Ingest> {
    if !["brevo", "mailgun", "postmark", "ses", "cloudflare"].contains(&provider)
        || !message_id_re().is_match(message_id)
    {
        return None;
    }
    if recipient.is_empty()
        || recipient.chars().count() > 320
        || py_strip(text).is_empty()
        || text.chars().count() > 20_000
        || text.contains('\0')
    {
        return None;
    }
    let draft_sender = draft_address(sender)?;
    let source_key = format!("{provider}:{}", sha256_hex(message_id));
    Some(Ingest {
        session_id: format!("email{}", &sha256_hex(&draft_sender.to_lowercase())[..50]),
        draft_subject: draft_subject(subject),
        draft_inbound_body: truncate_chars(text, 20_000),
        lead_message: truncate_chars(&format!("{subject}\n\n{text}"), 1000),
        draft_sender,
        source_key,
    })
}

/// `enquiries.capture`: the keys and the owner notice it writes. `None` for an unknown channel or empty source.
#[derive(Debug, PartialEq, Eq)]
pub struct Enquiry {
    pub lead_key: String,
    pub original_key: String,
    pub lead_email: String,
    pub lead_phone: String,
    pub lead_message: String,
    pub original_text: String,
    pub owner_subject: String,
    pub owner_body: String,
    pub owner_dedupe: String,
}

fn title(channel: &str) -> String {
    let mut c = channel.chars();
    c.next()
        .map(|f| f.to_uppercase().collect::<String>() + c.as_str())
        .unwrap_or_default()
}

pub fn enquiry_plan(
    tenant_id: &str,
    tenant_name: &str,
    channel: &str,
    source: &str,
    message: &str,
    email: &str,
    phone: &str,
) -> Option<Enquiry> {
    if !["email", "sms", "phone", "chat"].contains(&channel) || source.is_empty() {
        return None;
    }
    let original_key = sha256_hex(&format!("{source}\0{message}"));
    Some(Enquiry {
        lead_key: sha256_hex(source),
        lead_email: truncate_chars(email, 200),
        lead_phone: truncate_chars(phone, 40),
        lead_message: truncate_chars(message, 1000),
        original_text: truncate_chars(message, 30_000),
        owner_subject: format!("{} enquiry for {tenant_name}", title(channel)),
        owner_body: format!(
            "Channel: {channel}\nEmail: {email}\nPhone: {phone}\n\n{}",
            truncate_chars(message, 30_000)
        ),
        owner_dedupe: format!("enquiry-original:{tenant_id}:{channel}:{original_key}"),
        original_key,
    })
}
