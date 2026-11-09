//! Encrypts access and refresh tokens at rest with AES-256-GCM.
//! Each sealed value is bound to a label (the account it belongs to), so a token copied onto
//! another account's row will not decrypt.
use aes_gcm::aead::{Aead, KeyInit, Payload};
use aes_gcm::{Aes256Gcm, Nonce};
use base64::engine::general_purpose::STANDARD as B64;
use base64::Engine;
use rand::RngCore;

pub struct Vault {
    cipher: Aes256Gcm,
}

impl Vault {
    /// `key_b64` is 32 random bytes, base64 encoded (for example: `openssl rand -base64 32`).
    pub fn from_base64_key(key_b64: &str) -> Result<Vault, String> {
        let key = B64
            .decode(key_b64.trim())
            .map_err(|_| "The vault key is not valid base64.".to_string())?;
        if key.len() != 32 {
            return Err(format!(
                "The vault key must be 32 bytes, got {}.",
                key.len()
            ));
        }
        let cipher = Aes256Gcm::new_from_slice(&key).map_err(|_| "Bad vault key.".to_string())?;
        Ok(Vault { cipher })
    }

    /// Returns base64 of nonce (12 bytes) followed by the ciphertext.
    pub fn seal(&self, plaintext: &str, label: &str) -> Result<String, String> {
        let mut nonce_bytes = [0u8; 12];
        rand::thread_rng().fill_bytes(&mut nonce_bytes);
        let nonce = Nonce::from_slice(&nonce_bytes);
        let ciphertext = self
            .cipher
            .encrypt(
                nonce,
                Payload {
                    msg: plaintext.as_bytes(),
                    aad: label.as_bytes(),
                },
            )
            .map_err(|_| "Could not encrypt.".to_string())?;
        let mut out = nonce_bytes.to_vec();
        out.extend_from_slice(&ciphertext);
        Ok(B64.encode(out))
    }

    pub fn open(&self, sealed: &str, label: &str) -> Result<String, String> {
        let raw = B64
            .decode(sealed)
            .map_err(|_| "Stored token is not valid.".to_string())?;
        if raw.len() < 13 {
            return Err("Stored token is too short.".to_string());
        }
        let (nonce_bytes, ciphertext) = raw.split_at(12);
        let plain = self
            .cipher
            .decrypt(
                Nonce::from_slice(nonce_bytes),
                Payload {
                    msg: ciphertext,
                    aad: label.as_bytes(),
                },
            )
            .map_err(|_| "Could not decrypt: wrong key or the token was moved.".to_string())?;
        String::from_utf8(plain).map_err(|_| "Decrypted token is not text.".to_string())
    }
}

/// The label that binds a token to its account.
pub fn account_label(customer_id: &str, network: &str, external_id: &str) -> String {
    format!("{customer_id}|{network}|{external_id}")
}
