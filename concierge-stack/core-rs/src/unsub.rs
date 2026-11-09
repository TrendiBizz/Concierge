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

/// Return `(tenant_id, contact)` for a valid token, otherwise `None`.
pub fn read_token(secret: &str, token: &str) -> Option<(String, String)> {
    if secret.is_empty() || token.is_empty() {
        return None;
    }
    let (payload, signature) = token.split_once('.').unwrap_or((token, ""));
    if payload.is_empty() {
        return None;
    }
    let expected = sign(secret.as_bytes(), payload);
    if !bool::from(expected.as_bytes().ct_eq(signature.as_bytes())) {
        return None;
    }
    let raw =
        String::from_utf8(URL_SAFE_NO_PAD.decode(payload.trim_end_matches('=')).ok()?).ok()?;
    let (tenant, contact) = raw.split_once('|')?;
    (!tenant.is_empty() && !contact.is_empty()).then(|| (tenant.to_string(), contact.to_string()))
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
