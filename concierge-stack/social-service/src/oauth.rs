//! Tenant-scoped Mastodon OAuth 2.0 authorization-code + PKCE.
//! Operator pins a single HTTPS instance and registered OAuth client.
//! Not an AT Protocol/Bluesky OAuth implementation.
use crate::{store::Store, vault::Vault};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use rand::RngCore;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

#[derive(Clone)]
pub struct Config {
    pub origin: String,
    pub client_id: String,
    pub client_secret: String,
    pub callback: String,
}
#[derive(Serialize)]
pub struct Start {
    pub authorization_url: String,
    pub state: String,
}
#[derive(Deserialize)]
struct Token {
    access_token: String,
    token_type: String,
    scope: String,
}
#[derive(Deserialize)]
struct Profile {
    id: String,
    acct: String,
    display_name: String,
}
fn secret() -> String {
    let mut bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut bytes);
    URL_SAFE_NO_PAD.encode(bytes)
}
pub fn from_env() -> Result<Config, String> {
    let origin =
        std::env::var("SOCIAL_MASTODON_ORIGIN").map_err(|_| "Mastodon OAuth is not configured")?;
    let client_id = std::env::var("SOCIAL_MASTODON_CLIENT_ID")
        .map_err(|_| "Mastodon OAuth is not configured")?;
    let client_secret = std::env::var("SOCIAL_MASTODON_CLIENT_SECRET")
        .map_err(|_| "Mastodon OAuth is not configured")?;
    let callback = std::env::var("SOCIAL_MASTODON_CALLBACK")
        .map_err(|_| "Mastodon OAuth is not configured")?;
    let url = reqwest::Url::parse(&origin).map_err(|_| "Invalid Mastodon origin")?;
    let cb = reqwest::Url::parse(&callback).map_err(|_| "Invalid OAuth callback")?;
    if url.scheme() != "https"
        || url.host_str().is_none()
        || url.username() != ""
        || url.password().is_some()
        || url.port().is_some()
        || url.path() != "/"
        || url.query().is_some()
        || url.fragment().is_some()
        || cb.scheme() != "https"
        || cb.host_str().is_none()
        || cb.username() != ""
        || cb.password().is_some()
        || cb.fragment().is_some()
        || cb.query().is_some()
        || cb.path() != "/owner/social/oauth/callback"
        || client_id.len() < 8
        || client_secret.len() < 8
    {
        return Err("Invalid Mastodon OAuth configuration".into());
    }
    Ok(Config {
        origin: origin.trim_end_matches('/').into(),
        client_id,
        client_secret,
        callback,
    })
}
pub fn start(store: &Store, vault: &Vault, customer: &str, cfg: &Config) -> Result<Start, String> {
    // The customer must already exist, and identity must come from Concierge owner auth.
    store.rules(customer)?;
    let state = secret();
    let verifier = secret();
    let digest = Sha256::digest(verifier.as_bytes());
    let challenge = URL_SAFE_NO_PAD.encode(digest);
    let sealed = vault.seal(&verifier, &format!("oauth:mastodon:{customer}"))?;
    store.oauth_begin(customer, "mastodon", &state, &sealed, 600)?;
    let mut url = reqwest::Url::parse(&format!("{}/oauth/authorize", cfg.origin))
        .map_err(|e| e.to_string())?;
    url.query_pairs_mut()
        .append_pair("response_type", "code")
        .append_pair("client_id", &cfg.client_id)
        .append_pair("redirect_uri", &cfg.callback)
        .append_pair("scope", "read:accounts write:statuses")
        .append_pair("state", &state)
        .append_pair("code_challenge_method", "S256")
        .append_pair("code_challenge", &challenge);
    Ok(Start {
        authorization_url: url.to_string(),
        state,
    })
}
pub async fn finish(
    store: &Store,
    vault: &Vault,
    customer: &str,
    cfg: &Config,
    state: &str,
    code: &str,
) -> Result<String, String> {
    if code.is_empty() || code.len() > 2048 {
        return Err("Invalid OAuth code".into());
    }
    let encrypted = store.oauth_consume(customer, "mastodon", state)?;
    let verifier = vault.open(&encrypted, &format!("oauth:mastodon:{customer}"))?;
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(12))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "OAuth client unavailable")?;
    let response = client
        .post(format!("{}/oauth/token", cfg.origin))
        .form(&[
            ("grant_type", "authorization_code"),
            ("code", code),
            ("client_id", cfg.client_id.as_str()),
            ("client_secret", cfg.client_secret.as_str()),
            ("redirect_uri", cfg.callback.as_str()),
            ("code_verifier", verifier.as_str()),
            ("scope", "read:accounts write:statuses"),
        ])
        .send()
        .await
        .map_err(|_| "OAuth token exchange unavailable")?;
    if !response.status().is_success() {
        return Err("OAuth authorization was rejected".into());
    }
    let token: Token = response
        .json()
        .await
        .map_err(|_| "Invalid OAuth token response")?;
    if !["read:accounts", "write:statuses"].iter().all(|required| {
        token.scope.split_whitespace().any(|scope| {
            scope == *required
                || (*required == "read:accounts" && scope == "read")
                || (*required == "write:statuses" && scope == "write")
        })
    }) {
        return Err("Mastodon did not grant account and publishing permissions".into());
    }
    if token.token_type.to_lowercase() != "bearer" || token.access_token.is_empty() {
        return Err("Unsupported OAuth token response".into());
    }
    let profile_response = client
        .get(format!("{}/api/v1/accounts/verify_credentials", cfg.origin))
        .bearer_auth(&token.access_token)
        .send()
        .await
        .map_err(|_| "OAuth profile verification unavailable")?;
    if !profile_response.status().is_success() {
        return Err("OAuth identity verification failed".into());
    }
    let profile: Profile = profile_response
        .json()
        .await
        .map_err(|_| "Invalid OAuth profile")?;
    if profile.id.is_empty() || profile.acct.is_empty() {
        return Err("OAuth profile missing identity".into());
    }
    let account_label = crate::vault::account_label(
        customer,
        "mastodon",
        &format!("{}@{}", profile.id, cfg.origin),
    );
    let sealed = vault.seal(&token.access_token, &account_label)?;
    store.upsert_verified_account(crate::store::VerifiedAccount {
        customer,
        network: "mastodon",
        external_id: &format!("{}@{}", profile.id, cfg.origin),
        display_name: if profile.display_name.trim().is_empty() {
            &profile.acct
        } else {
            &profile.display_name
        },
        token_enc: &sealed,
        refresh_enc: None,
        expires_at: None,
        granted_scopes: &token.scope,
    })
}
/// Revoke at the provider first. Failure is reported, never silently treated as revoked.
pub async fn disconnect(
    store: &Store,
    vault: &Vault,
    customer: &str,
    account_id: &str,
    cfg: &Config,
) -> Result<(), String> {
    let (network, external_id, token_enc, _) = store.account(customer, account_id)?;
    if network != "mastodon" || !external_id.ends_with(&format!("@{}", cfg.origin)) {
        return Err("Account does not belong to configured Mastodon provider".into());
    }
    let token = vault.open(
        &token_enc,
        &crate::vault::account_label(customer, "mastodon", &external_id),
    )?;
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(12))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "OAuth client unavailable")?;
    let response = client
        .post(format!("{}/oauth/revoke", cfg.origin))
        .form(&[
            ("client_id", cfg.client_id.as_str()),
            ("client_secret", cfg.client_secret.as_str()),
            ("token", token.as_str()),
        ])
        .send()
        .await
        .map_err(|_| "Provider revocation could not be confirmed")?;
    if !response.status().is_success() {
        return Err("Provider revocation could not be confirmed".into());
    }
    store.disconnect_account(customer, account_id)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn disconnect_erases_only_target_tenant_credentials() {
        let store = Store::open_memory().unwrap();
        store.create_customer("alice", "Alice", "").unwrap();
        store.create_customer("bob", "Bob", "").unwrap();
        let alice = store
            .add_account(
                "alice",
                "mastodon",
                "alice@server",
                "Alice",
                "encrypted-secret-a",
                None,
            )
            .unwrap();
        let bob = store
            .add_account(
                "bob",
                "mastodon",
                "bob@server",
                "Bob",
                "encrypted-secret-b",
                None,
            )
            .unwrap();
        assert!(store.disconnect_account("bob", &alice).is_err());
        store.disconnect_account("alice", &alice).unwrap();
        assert!(store.account("alice", &alice).is_err());
        assert_eq!(store.account("bob", &bob).unwrap().2, "encrypted-secret-b");
        let accounts = store.list_accounts("alice").unwrap();
        assert_eq!(accounts.len(), 1);
        assert!(accounts[0].needs_reauth);
    }
    #[test]
    fn oauth_pkce_and_state_are_scoped_single_use() {
        let store = Store::open_memory().unwrap();
        store.create_customer("alice", "Alice", "").unwrap();
        store.create_customer("bob", "Bob", "").unwrap();
        let vault =
            Vault::from_base64_key(&base64::engine::general_purpose::STANDARD.encode([7u8; 32]))
                .unwrap();
        let cfg = Config {
            origin: "https://mastodon.social".into(),
            client_id: "registered-client".into(),
            client_secret: "secret-client".into(),
            callback: "https://example.org/owner/social/oauth/callback".into(),
        };
        let a = start(&store, &vault, "alice", &cfg).unwrap();
        let b = start(&store, &vault, "alice", &cfg).unwrap();
        assert_ne!(a.state, b.state);
        let u = reqwest::Url::parse(&a.authorization_url).unwrap();
        let params: std::collections::HashMap<_, _> = u.query_pairs().into_owned().collect();
        assert_eq!(params["code_challenge_method"], "S256");
        assert_eq!(params["state"], a.state);
        assert!(!a.authorization_url.contains("secret-client"));
        assert!(store.oauth_consume("bob", "mastodon", &a.state).is_err());
        let sealed = store.oauth_consume("alice", "mastodon", &a.state).unwrap();
        let verifier = vault.open(&sealed, "oauth:mastodon:alice").unwrap();
        assert_eq!(
            URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes())),
            params["code_challenge"]
        );
        assert!(store.oauth_consume("alice", "mastodon", &a.state).is_err());
        assert!(store.oauth_consume("alice", "mastodon", "invalid").is_err());
    }
}
