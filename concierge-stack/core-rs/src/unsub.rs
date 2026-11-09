//! Signed unsubscribe links. Token = base64url("tenant|contact") + "." + hex(HMAC-SHA256)[..32].
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use hmac::{Hmac, Mac};
use sha2::Sha256;
use subtle::ConstantTimeEq;

type HmacSha256 = Hmac<Sha256>;

fn sign(secret: &[u8], payload: &str) -> String {
    let mut mac = HmacSha256::new_from_slice(secret).expect("HMAC accepts any key length");
    mac.update(payload.as_bytes());
    let hex: String = mac
        .finalize()
        .into_bytes()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    hex[..32].to_string()
}

pub fn make_token(secret: &str, tenant_id: &str, contact: &str) -> Result<String, &'static str> {
    if secret.is_empty() {
        return Err("UNSUBSCRIBE_SECRET (or ADMIN_TOKEN) is not set");
    }
    let payload = URL_SAFE_NO_PAD.encode(format!("{tenant_id}|{contact}"));
    Ok(format!("{payload}.{}", sign(secret.as_bytes(), &payload)))
}

/// CPython's non-strict `binascii.a2b_base64` as `base64.urlsafe_b64decode` reaches it: `-`/`_` are `+`/`/`, characters outside
/// the alphabet are skipped, a `=` ends the data once the quad has two characters and enough padding, and an unfinished quad
/// is an error. `None` is the `binascii.Error` (a `ValueError`) Python would raise.
fn lenient_b64decode(s: &str) -> Option<Vec<u8>> {
    let mut out = Vec::new();
    let (mut quad, mut left, mut pads) = (0u8, 0u8, 0u8);
    for b in s.bytes() {
        if b == b'=' {
            if quad >= 2 {
                pads += 1;
                if quad + pads >= 4 {
                    return Some(out);
                }
            }
            continue;
        }
        let v = match b {
            b'A'..=b'Z' => b - b'A',
            b'a'..=b'z' => b - b'a' + 26,
            b'0'..=b'9' => b - b'0' + 52,
            b'+' | b'-' => 62,
            b'/' | b'_' => 63,
            _ => continue,
        };
        pads = 0;
        match quad {
            0 => {
                quad = 1;
                left = v;
            }
            1 => {
                quad = 2;
                out.push((left << 2) | (v >> 4));
                left = v & 0x0f;
            }
            2 => {
                quad = 3;
                out.push((left << 4) | (v >> 2));
                left = v & 0x03;
            }
            _ => {
                quad = 0;
                out.push((left << 6) | v);
                left = 0;
            }
        }
    }
    (quad == 0).then_some(out)
}

/// `read_token`, including the one way it raises: `hmac.compare_digest` refuses a `str` signature with a non-ASCII character
/// (`TypeError`, so FastAPI answers 500). `Err(())` is that exception; `Ok(None)` is Python's `None`.
#[allow(clippy::result_unit_err)]
pub fn read_token_checked(secret: &str, token: &str) -> Result<Option<(String, String)>, ()> {
    if secret.is_empty() || token.is_empty() {
        return Ok(None);
    }
    let (payload, signature) = token.split_once('.').unwrap_or((token, ""));
    if payload.is_empty() {
        return Ok(None);
    }
    if !signature.is_ascii() {
        return Err(());
    }
    let expected = sign(secret.as_bytes(), payload);
    if !bool::from(expected.as_bytes().ct_eq(signature.as_bytes())) {
        return Ok(None);
    }
    if !payload.is_ascii() {
        return Ok(None); // `str.encode("ascii")` inside b64decode raises a ValueError
    }
    let padded = format!("{payload}{}", "=".repeat(payload.len().wrapping_neg() % 4));
    let Some(raw) = lenient_b64decode(&padded).and_then(|b| String::from_utf8(b).ok()) else {
        return Ok(None);
    };
    Ok(raw
        .split_once('|')
        .filter(|(tenant, contact)| !tenant.is_empty() && !contact.is_empty())
        .map(|(tenant, contact)| (tenant.to_string(), contact.to_string())))
}

/// Return `(tenant_id, contact)` for a valid token, otherwise `None` (a token that makes Python raise is also `None` here).
pub fn read_token(secret: &str, token: &str) -> Option<(String, String)> {
    read_token_checked(secret, token).unwrap_or(None)
}

/// `_plain_page`: the small standalone page both unsubscribe routes use.
pub fn plain_page(title: &str, body_html: &str) -> String {
    let t = crate::report::html_escape(title);
    format!(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">\
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><meta name=\"robots\" content=\"noindex\">\
<title>{t}</title>\
<style>body{{font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem;color:#111}}\
button{{font:inherit;padding:.7rem 1.2rem;border-radius:8px;border:0;background:#111;color:#fff;cursor:pointer}}</style>\
</head><body><h1>{t}</h1>{body_html}</body></html>"
    )
}

/// `GET /api/v1/unsubscribe/{token}`: `Ok((status, html))`, or `Err(())` where Python raises (a plain 500).
#[allow(clippy::result_unit_err)]
pub fn unsubscribe_confirm_page(secret: &str, token: &str) -> Result<(u16, String), ()> {
    if read_token_checked(secret, token)?.is_none() {
        return Ok((
            404,
            plain_page(
                "This link is not valid",
                "<p>It may be incomplete. Reply to the email and we will remove you.</p>",
            ),
        ));
    }
    Ok((
        200,
        plain_page(
            "Unsubscribe",
            "<p>Stop receiving promotional messages from this business?</p><form method=\"post\"><button>Unsubscribe</button></form>",
        ),
    ))
}

pub fn url_for(
    secret: &str,
    public_base_url: &str,
    tenant_id: &str,
    contact: &str,
) -> Result<String, &'static str> {
    let token = make_token(secret, tenant_id, contact)?;
    Ok(format!(
        "{}/api/v1/unsubscribe/{token}",
        public_base_url.trim_end_matches('/')
    ))
}
