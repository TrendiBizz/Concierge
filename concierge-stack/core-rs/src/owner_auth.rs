//! Owner credential primitives (port of `owner_auth.digest`, `password_hash`, `verify_password`, `clean_email`).
//! Hash strings are byte-compatible with the ones Python already stored: `pbkdf2_sha256:<rounds>:<salt hex>:<key hex>`.
use crate::{py_strip, pyval::truncate_chars};
use hmac::Hmac;
use regex::Regex;
use sha2::{Digest, Sha256};
use std::sync::OnceLock;
use subtle::ConstantTimeEq;

pub const ITERATIONS: u32 = 600_000;

pub fn digest(token: &str) -> String {
    Sha256::digest(token.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

fn unhex(s: &str) -> Option<Vec<u8>> {
    if !s.len().is_multiple_of(2) || !s.is_ascii() {
        return None;
    }
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).ok())
        .collect()
}

fn derive(password: &str, salt: &[u8], rounds: u32) -> [u8; 32] {
    let mut out = [0u8; 32];
    pbkdf2::pbkdf2::<Hmac<Sha256>>(password.as_bytes(), salt, rounds, &mut out)
        .expect("HMAC accepts any key length");
    out
}

/// `password_hash` with a caller-supplied salt (production passes 16 random bytes).
pub fn password_hash_with_salt(
    password: &str,
    salt: &[u8; 16],
    rounds: u32,
) -> Result<String, &'static str> {
    let n = password.chars().count();
    if !(12..=256).contains(&n) {
        return Err("Password must contain 12-256 characters");
    }
    Ok(format!(
        "pbkdf2_sha256:{rounds}:{}:{}",
        hex(salt),
        hex(&derive(password, salt, rounds))
    ))
}

pub fn verify_password(password: &str, stored: &str) -> bool {
    let parts: Vec<&str> = stored.split(':').collect();
    let [kind, rounds, salt, expected] = parts[..] else {
        return false;
    };
    if kind != "pbkdf2_sha256" {
        return false;
    }
    let (Some(salt), Some(expected)) = (unhex(salt), unhex(expected)) else {
        return false;
    };
    let Ok(rounds) = py_strip(rounds).parse::<u32>() else {
        return false;
    };
    if rounds == 0 {
        return false; // Python's pbkdf2_hmac raises ValueError for non-positive iterations
    }
    let computed = derive(password, &salt, rounds);
    computed.len() == expected.len() && bool::from(computed.as_slice().ct_eq(&expected))
}

fn email_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[^\s@]+@[^\s@]+\.[^\s@]+$").unwrap())
}

pub fn clean_email(email: &str) -> Result<String, &'static str> {
    let value = py_strip(email).to_lowercase();
    if value.chars().count() > 320 || !email_re().is_match(&value) {
        return Err("Invalid email");
    }
    Ok(truncate_chars(&value, 320))
}
