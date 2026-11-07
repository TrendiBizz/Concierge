//! LinkedIn member OAuth authorization-code account linking.
//! Official: https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow
//! Identity endpoint: https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2
//! LinkedIn documentation specifies confidential client + state (not PKCE).
//! Customer tokens stay server-side; no publishing is performed here.
use crate::{store::Store, vault::Vault};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use rand::RngCore;
use serde::Deserialize;

const AUTHORIZE: &str = "https://www.linkedin.com/oauth/v2/authorization";
const TOKEN: &str = "https://www.linkedin.com/oauth/v2/accessToken";
const USERINFO: &str = "https://api.linkedin.com/v2/userinfo";
const SCOPE: &str = "openid profile w_member_social";

#[derive(Clone)]
pub struct Config {
    pub client_id: String,
    pub client_secret: String,
    pub callback: String,
}
#[derive(Deserialize)]
struct Token {
    access_token: String,
    expires_in: i64,
    #[serde(default)]
    refresh_token: Option<String>,
    #[serde(default)]
    scope: String,
}
#[derive(Deserialize)]
struct Profile {
    sub: String,
    #[serde(default)]
    name: String,
}
fn random_state() -> String {
    let mut bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut bytes);
    URL_SAFE_NO_PAD.encode(bytes)
}
pub fn from_env() -> Result<Config, String> {
    let client_id = std::env::var("SOCIAL_LINKEDIN_CLIENT_ID")
        .map_err(|_| "LinkedIn OAuth is not configured")?;
    let client_secret = std::env::var("SOCIAL_LINKEDIN_CLIENT_SECRET")
        .map_err(|_| "LinkedIn OAuth is not configured")?;
    let callback = std::env::var("SOCIAL_LINKEDIN_CALLBACK")
        .map_err(|_| "LinkedIn OAuth is not configured")?;
    let url = reqwest::Url::parse(&callback).map_err(|_| "Invalid LinkedIn callback")?;
    if url.scheme() != "https"
        || url.host_str().is_none()
        || url.username() != ""
        || url.password().is_some()
        || url.fragment().is_some()
        || url.query().is_some()
        || client_id.len() < 8
        || client_secret.len() < 8
    {
        return Err("Invalid LinkedIn OAuth configuration".into());
    }
    Ok(Config {
        client_id,
        client_secret,
        callback,
    })
}
pub fn start(
    store: &Store,
    vault: &Vault,
    customer: &str,
    cfg: &Config,
) -> Result<crate::oauth::Start, String> {
    store.rules(customer)?;
    let state = random_state();
    // LinkedIn code flow relies on confidential app credentials and state.
    // Encrypt a per-request nonce to satisfy the common bounded state store;
    // it is never transmitted to LinkedIn.
    let nonce = vault.seal(&random_state(), &format!("oauth:linkedin:{customer}"))?;
    store.oauth_begin(customer, "linkedin", &state, &nonce, 600)?;
    let mut url = reqwest::Url::parse(AUTHORIZE).map_err(|e| e.to_string())?;
    url.query_pairs_mut()
        .append_pair("response_type", "code")
        .append_pair("client_id", &cfg.client_id)
        .append_pair("redirect_uri", &cfg.callback)
        .append_pair("scope", SCOPE)
        .append_pair("state", &state);
    Ok(crate::oauth::Start {
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
        return Err("Invalid LinkedIn authorization code".into());
    }
    // Consume once before external exchange. Wrong-tenant and expired callbacks fail closed.
    let _ = store.oauth_consume(customer, "linkedin", state)?;
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(12))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "LinkedIn OAuth client unavailable")?;
    let response = client
        .post(TOKEN)
        .form(&[
            ("grant_type", "authorization_code"),
            ("code", code),
            ("client_id", cfg.client_id.as_str()),
            ("client_secret", cfg.client_secret.as_str()),
            ("redirect_uri", cfg.callback.as_str()),
        ])
        .send()
        .await
        .map_err(|_| "LinkedIn authorization unavailable")?;
    if !response.status().is_success() {
        return Err("LinkedIn authorization was rejected".into());
    }
    let token: Token = response
        .json()
        .await
        .map_err(|_| "Invalid LinkedIn OAuth token response")?;
    if token.access_token.is_empty() || !(1..=31_536_000).contains(&token.expires_in) {
        return Err("Invalid LinkedIn OAuth token expiry".into());
    }
    if !SCOPE.split_whitespace().all(|required| {
        token
            .scope
            .split_whitespace()
            .any(|actual| actual == required)
    }) {
        return Err("LinkedIn did not grant the requested permissions".into());
    }
    let response = client
        .get(USERINFO)
        .bearer_auth(&token.access_token)
        .send()
        .await
        .map_err(|_| "LinkedIn profile lookup unavailable")?;
    if !response.status().is_success() {
        return Err("LinkedIn profile verification failed".into());
    }
    let profile: Profile = response
        .json()
        .await
        .map_err(|_| "Invalid LinkedIn profile")?;
    if profile.sub.is_empty() || profile.sub.len() > 256 {
        return Err("LinkedIn profile missing identity".into());
    }
    let label = crate::vault::account_label(customer, "linkedin", &profile.sub);
    let access_enc = vault.seal(&token.access_token, &label)?;
    let refresh_enc = token
        .refresh_token
        .as_deref()
        .map(|value| vault.seal(value, &label))
        .transpose()?;
    store.upsert_verified_account(crate::store::VerifiedAccount {
        customer,
        network: "linkedin",
        external_id: &profile.sub,
        display_name: if profile.name.trim().is_empty() {
            "LinkedIn account"
        } else {
            &profile.name
        },
        token_enc: &access_enc,
        refresh_enc: refresh_enc.as_deref(),
        expires_at: Some(crate::now_unix() + token.expires_in),
        granted_scopes: &token.scope,
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn reauthorizing_preserves_id_and_expired_tokens_are_blocked() {
        let store = Store::open_memory().unwrap();
        store.create_customer("a", "A", "").unwrap();
        store.create_customer("b", "B", "").unwrap();
        let first = store
            .upsert_verified_account(crate::store::VerifiedAccount {
                customer: "a",
                network: "linkedin",
                external_id: "member-1",
                display_name: "Name",
                token_enc: "sealed-1",
                refresh_enc: None,
                expires_at: Some(crate::now_unix() + 100),
                granted_scopes: SCOPE,
            })
            .unwrap();
        let second = store
            .upsert_verified_account(crate::store::VerifiedAccount {
                customer: "a",
                network: "linkedin",
                external_id: "member-1",
                display_name: "Name changed",
                token_enc: "sealed-2",
                refresh_enc: None,
                expires_at: Some(crate::now_unix() + 200),
                granted_scopes: SCOPE,
            })
            .unwrap();
        assert_eq!(first, second);
        assert_eq!(store.list_accounts("a").unwrap().len(), 1);
        assert_eq!(store.account("a", &first).unwrap().2, "sealed-2");
        let other = store
            .upsert_verified_account(crate::store::VerifiedAccount {
                customer: "b",
                network: "linkedin",
                external_id: "member-1",
                display_name: "Other",
                token_enc: "sealed-other",
                refresh_enc: None,
                expires_at: Some(crate::now_unix() - 1),
                granted_scopes: SCOPE,
            })
            .unwrap();
        assert_ne!(first, other);
        assert!(store.account("b", &other).is_err());
        let entry = store.list_accounts("b").unwrap();
        assert!(entry[0].needs_reauth);
    }
    #[test]
    fn linkedin_scopes_and_cross_tenant_state_are_enforced() {
        let store = Store::open_memory().unwrap();
        store.create_customer("a", "A", "").unwrap();
        store.create_customer("b", "B", "").unwrap();
        let vault =
            Vault::from_base64_key(&base64::engine::general_purpose::STANDARD.encode([2u8; 32]))
                .unwrap();
        let cfg = Config {
            client_id: "linked-client".into(),
            client_secret: "linked-secret".into(),
            callback: "https://example.org/owner-ui".into(),
        };
        let created = start(&store, &vault, "a", &cfg).unwrap();
        let url = reqwest::Url::parse(&created.authorization_url).unwrap();
        assert_eq!(url.host_str(), Some("www.linkedin.com"));
        let params: std::collections::HashMap<_, _> = url.query_pairs().into_owned().collect();
        assert_eq!(params["scope"], SCOPE);
        assert_eq!(params["state"], created.state);
        assert!(!created.authorization_url.contains("linked-secret"));
        assert!(store
            .oauth_consume("b", "linkedin", &created.state)
            .is_err());
        assert!(store
            .oauth_consume("a", "mastodon", &created.state)
            .is_err());
        assert!(store.oauth_consume("a", "linkedin", &created.state).is_ok());
        assert!(store
            .oauth_consume("a", "linkedin", &created.state)
            .is_err());
    }
}
