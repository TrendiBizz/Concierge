//! TikTok Login Kit (web): authorized customer account discovery only.
//! Publishing is separately gated and NOT enabled by this connector.
use crate::{
    store::{Store, VerifiedAccount},
    vault::{account_label, Vault},
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use rand::RngCore;
use serde::Deserialize;

const AUTHORIZE: &str = "https://www.tiktok.com/v2/auth/authorize/";
const TOKEN: &str = "https://open.tiktokapis.com/v2/oauth/token/";
const USERINFO: &str = "https://open.tiktokapis.com/v2/user/info/";
const SCOPE: &str = "user.info.basic";

#[derive(Clone)]
pub struct Config {
    pub client_key: String,
    pub client_secret: String,
    pub callback: String,
}
#[derive(Deserialize)]
struct Token {
    access_token: String,
    open_id: String,
    refresh_token: String,
    expires_in: i64,
    scope: String,
}
#[derive(Deserialize)]
struct ProfileResponse {
    data: ProfileData,
    error: TikTokError,
}
#[derive(Deserialize)]
struct ProfileData {
    user: Profile,
}
#[derive(Deserialize)]
struct Profile {
    open_id: String,
    #[serde(default)]
    display_name: String,
}
#[derive(Deserialize)]
struct TikTokError {
    code: String,
}

pub fn from_env() -> Result<Config, String> {
    let client_key = std::env::var("SOCIAL_TIKTOK_CLIENT_KEY")
        .map_err(|_| "TikTok developer app not configured")?;
    let client_secret = std::env::var("SOCIAL_TIKTOK_CLIENT_SECRET")
        .map_err(|_| "TikTok developer app not configured")?;
    let callback = std::env::var("SOCIAL_TIKTOK_CALLBACK")
        .map_err(|_| "TikTok developer app not configured")?;
    let url = reqwest::Url::parse(&callback).map_err(|_| "Invalid TikTok callback")?;
    if client_key.len() < 6
        || client_secret.len() < 8
        || url.scheme() != "https"
        || url.path() != "/owner/social/oauth/callback"
        || url.query().is_some()
        || url.fragment().is_some()
        || url.username() != ""
        || url.password().is_some()
        || url.host_str().is_none()
    {
        return Err("Invalid TikTok OAuth configuration".into());
    }
    Ok(Config {
        client_key,
        client_secret,
        callback,
    })
}
fn new_state() -> String {
    let mut bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut bytes);
    URL_SAFE_NO_PAD.encode(bytes)
}
pub fn start(
    store: &Store,
    vault: &Vault,
    customer: &str,
    cfg: &Config,
) -> Result<crate::oauth::Start, String> {
    store.rules(customer)?;
    let state = new_state();
    let nonce = vault.seal(&new_state(), &format!("oauth:tiktok:{customer}"))?;
    store.oauth_begin(customer, "tiktok", &state, &nonce, 600)?;
    let mut url = reqwest::Url::parse(AUTHORIZE).map_err(|_| "TikTok authorize URL invalid")?;
    url.query_pairs_mut()
        .append_pair("client_key", &cfg.client_key)
        .append_pair("response_type", "code")
        .append_pair("scope", SCOPE)
        .append_pair("redirect_uri", &cfg.callback)
        .append_pair("state", &state);
    Ok(crate::oauth::Start {
        authorization_url: url.into(),
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
        return Err("Invalid TikTok authorization code".into());
    }
    // A one-time customer-scoped state is consumed before contacting TikTok.
    store.oauth_consume(customer, "tiktok", state)?;
    let http = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "TikTok HTTP client unavailable")?;
    let response = http
        .post(TOKEN)
        .form(&[
            ("client_key", cfg.client_key.as_str()),
            ("client_secret", cfg.client_secret.as_str()),
            ("grant_type", "authorization_code"),
            ("code", code),
            ("redirect_uri", cfg.callback.as_str()),
        ])
        .send()
        .await
        .map_err(|_| "TikTok token exchange unavailable")?;
    if !response.status().is_success() {
        return Err("TikTok token exchange rejected".into());
    }
    let token: Token = response
        .json()
        .await
        .map_err(|_| "Invalid TikTok token response")?;
    if token.access_token.is_empty()
        || token.refresh_token.is_empty()
        || token.open_id.is_empty()
        || !(1..=86_400).contains(&token.expires_in)
        || !token
            .scope
            .split(',')
            .any(|scope| scope == "user.info.basic")
    {
        return Err("TikTok did not grant valid account access".into());
    }
    let profile_response = http
        .get(USERINFO)
        .query(&[("fields", "open_id,display_name")])
        .bearer_auth(&token.access_token)
        .send()
        .await
        .map_err(|_| "TikTok profile verification unavailable")?;
    if !profile_response.status().is_success() {
        return Err("TikTok profile verification rejected".into());
    }
    let profile: ProfileResponse = profile_response
        .json()
        .await
        .map_err(|_| "Invalid TikTok profile response")?;
    if profile.error.code != "ok" || profile.data.user.open_id != token.open_id {
        return Err("TikTok identity mismatch".into());
    }
    let label = account_label(customer, "tiktok", &token.open_id);
    let encrypted = vault.seal(&token.access_token, &label)?;
    let refresh = vault.seal(&token.refresh_token, &label)?;
    store.upsert_verified_account(VerifiedAccount {
        customer,
        network: "tiktok",
        external_id: &token.open_id,
        display_name: if profile.data.user.display_name.trim().is_empty() {
            "TikTok account"
        } else {
            &profile.data.user.display_name
        },
        token_enc: &encrypted,
        refresh_enc: Some(&refresh),
        expires_at: Some(crate::now_unix().saturating_add(token.expires_in)),
        granted_scopes: SCOPE,
    })
}
pub fn disconnect(store: &Store, customer: &str, id: &str) -> Result<(), String> {
    let (network, _, _, _) = store.account(customer, id)?;
    if network != "tiktok" {
        return Err("Incorrect social provider".into());
    }
    // Local credentials destroyed immediately. User can also revoke in TikTok.
    store.disconnect_account(customer, id)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn tiktok_customer_scoped_single_use_oauth_state() {
        let store = Store::open_memory().unwrap();
        let vault =
            Vault::from_base64_key(&base64::engine::general_purpose::STANDARD.encode([23u8; 32]))
                .unwrap();
        store.create_customer("a", "A", "").unwrap();
        store.create_customer("b", "B", "").unwrap();
        let cfg = Config {
            client_key: "test-client-key".into(),
            client_secret: "test-secret-value".into(),
            callback: "https://concierge.example.com/owner/social/oauth/callback".into(),
        };
        let start = start(&store, &vault, "a", &cfg).unwrap();
        assert!(start.authorization_url.starts_with(AUTHORIZE));
        assert!(start.authorization_url.contains("user.info.basic"));
        assert!(store.oauth_consume("b", "tiktok", &start.state).is_err());
        assert!(store.oauth_consume("a", "tiktok", &start.state).is_ok());
        assert!(store.oauth_consume("a", "tiktok", &start.state).is_err());
    }
}
