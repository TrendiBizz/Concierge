//! Short-lived, signed, tenant-scoped capabilities. The server derives authority from the token, never from fields the
//! model supplies. Format: `base64url(json).base64url(HMAC-SHA256(secret, "hermes-cap-v1." + payload))`.
use crate::ops::Op;
use base64::{engine::general_purpose::URL_SAFE_NO_PAD as B64, Engine};
use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use subtle::ConstantTimeEq;

type HmacSha256 = Hmac<Sha256>;

pub const MAX_TTL_SECS: i64 = 900;
const CLOCK_SKEW_SECS: i64 = 30;
const DOMAIN: &str = "hermes-cap-v1.";

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Capability {
    pub tenant_id: String,
    pub case_id: String,
    pub run_id: String,
    pub ops: Vec<Op>,
    pub issued_at: i64,
    pub expires_at: i64,
    pub nonce: String,
}

#[derive(Debug, PartialEq, Eq)]
pub enum CapError {
    Malformed,
    BadSignature,
    Expired,
    NotYetValid,
    TtlTooLong,
    EmptyScope,
    Revoked,
}

fn mac(secret: &[u8], payload: &str) -> HmacSha256 {
    let mut m = HmacSha256::new_from_slice(secret).expect("HMAC accepts any key length");
    m.update(DOMAIN.as_bytes());
    m.update(payload.as_bytes());
    m
}

/// Sign a capability. Refuses scopes the verifier would reject, so a bad mint fails loudly at the source.
pub fn mint(secret: &[u8], cap: &Capability) -> Result<String, CapError> {
    check_shape(cap)?;
    let payload = B64.encode(serde_json::to_vec(cap).map_err(|_| CapError::Malformed)?);
    let sig = B64.encode(mac(secret, &payload).finalize().into_bytes());
    Ok(format!("{payload}.{sig}"))
}

fn check_shape(cap: &Capability) -> Result<(), CapError> {
    if cap.tenant_id.is_empty()
        || cap.case_id.is_empty()
        || cap.run_id.is_empty()
        || cap.nonce.is_empty()
        || cap.ops.is_empty()
    {
        return Err(CapError::EmptyScope);
    }
    if cap.expires_at - cap.issued_at > MAX_TTL_SECS || cap.expires_at <= cap.issued_at {
        return Err(CapError::TtlTooLong);
    }
    Ok(())
}

/// Verify signature, lifetime and revocation. `revoked` is asked about the token's nonce.
pub fn verify(
    secret: &[u8],
    token: &str,
    now: i64,
    revoked: &dyn Fn(&str) -> bool,
) -> Result<Capability, CapError> {
    let (payload, sig) = token.split_once('.').ok_or(CapError::Malformed)?;
    let given = B64.decode(sig).map_err(|_| CapError::Malformed)?;
    let expected = mac(secret, payload).finalize().into_bytes();
    if !bool::from(expected.as_slice().ct_eq(&given)) {
        return Err(CapError::BadSignature);
    }
    let cap: Capability =
        serde_json::from_slice(&B64.decode(payload).map_err(|_| CapError::Malformed)?)
            .map_err(|_| CapError::Malformed)?;
    check_shape(&cap)?;
    if now >= cap.expires_at {
        return Err(CapError::Expired);
    }
    if cap.issued_at > now + CLOCK_SKEW_SECS {
        return Err(CapError::NotYetValid);
    }
    if revoked(&cap.nonce) {
        return Err(CapError::Revoked);
    }
    Ok(cap)
}

impl Capability {
    pub fn allows(&self, op: Op) -> bool {
        self.ops.contains(&op)
    }
}
