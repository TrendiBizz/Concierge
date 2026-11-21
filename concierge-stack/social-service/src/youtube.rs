//! Customer-owned YouTube channels. OAuth state and PKCE verifier are tenant bound.
use crate::{
    store::{Store, VerifiedAccount},
    vault::{account_label, Vault},
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use rand::RngCore;
use serde::Deserialize;
use sha2::{Digest, Sha256};

pub const UPLOAD_SCOPE: &str = "https://www.googleapis.com/auth/youtube.upload";
pub const SCOPES: &str = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly";
#[derive(Clone)]
pub struct Config {
    pub client_id: String,
    pub secret: String,
    pub callback: String,
}
/// Explicit dependency injection for offline HTTP tests; production never reads endpoint overrides.
#[derive(Clone)]
pub struct Endpoints {
    pub token: String,
    pub channels: String,
    pub revoke: String,
}
impl Default for Endpoints {
    fn default() -> Self {
        Self {
            token: "https://oauth2.googleapis.com/token".into(),
            channels: "https://www.googleapis.com/youtube/v3/channels".into(),
            revoke: "https://oauth2.googleapis.com/revoke".into(),
        }
    }
}
pub fn from_env() -> Result<Config, String> {
    let client_id =
        std::env::var("YOUTUBE_CLIENT_ID").map_err(|_| "YouTube OAuth not configured")?;
    let secret =
        std::env::var("YOUTUBE_CLIENT_SECRET").map_err(|_| "YouTube OAuth not configured")?;
    let callback =
        std::env::var("YOUTUBE_REDIRECT_URI").map_err(|_| "YouTube OAuth not configured")?;
    let u = reqwest::Url::parse(&callback).map_err(|_| "Invalid YouTube OAuth configuration")?;
    if client_id.trim().is_empty()
        || secret.trim().is_empty()
        || u.scheme() != "https"
        || u.host_str().is_none()
        || !u.username().is_empty()
        || u.password().is_some()
        || u.query().is_some()
        || u.fragment().is_some()
        || u.path() != "/owner/social/oauth/callback"
    {
        return Err("Invalid YouTube OAuth configuration".into());
    }
    Ok(Config {
        client_id,
        secret,
        callback,
    })
}
pub(crate) fn http() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(60))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "YouTube client unavailable".into())
}
fn random() -> String {
    let mut b = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut b);
    URL_SAFE_NO_PAD.encode(b)
}
pub fn start(
    store: &Store,
    vault: &Vault,
    customer: &str,
    cfg: &Config,
) -> Result<crate::oauth::Start, String> {
    store.rules(customer)?;
    let state = random();
    let verifier = random();
    let sealed = vault.seal(&verifier, &format!("oauth:youtube:{customer}"))?;
    store.oauth_begin(customer, "youtube", &state, &sealed, 600)?;
    let mut u = reqwest::Url::parse("https://accounts.google.com/o/oauth2/v2/auth").unwrap();
    u.query_pairs_mut()
        .append_pair("client_id", &cfg.client_id)
        .append_pair("redirect_uri", &cfg.callback)
        .append_pair("response_type", "code")
        .append_pair("scope", SCOPES)
        .append_pair("state", &state)
        .append_pair("access_type", "offline")
        .append_pair("prompt", "consent")
        .append_pair("include_granted_scopes", "true")
        .append_pair("code_challenge_method", "S256")
        .append_pair(
            "code_challenge",
            &URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes())),
        );
    Ok(crate::oauth::Start {
        authorization_url: u.into(),
        state,
    })
}
#[derive(Deserialize)]
struct Token {
    access_token: String,
    #[serde(default)]
    refresh_token: String,
    expires_in: i64,
    #[serde(default)]
    scope: String,
}
#[derive(Deserialize)]
struct Channels {
    items: Vec<Channel>,
}
#[derive(Deserialize)]
struct Channel {
    id: String,
    snippet: Snippet,
}
#[derive(Deserialize)]
struct Snippet {
    title: String,
}
pub async fn finish(
    store: &Store,
    vault: &Vault,
    customer: &str,
    cfg: &Config,
    state: &str,
    code: &str,
) -> Result<String, String> {
    finish_with_endpoints(
        store,
        vault,
        customer,
        cfg,
        state,
        code,
        &Endpoints::default(),
    )
    .await
}
#[allow(clippy::too_many_arguments)]
pub async fn finish_with_endpoints(
    store: &Store,
    vault: &Vault,
    customer: &str,
    cfg: &Config,
    state: &str,
    code: &str,
    endpoints: &Endpoints,
) -> Result<String, String> {
    if code.is_empty() || code.len() > 2048 {
        return Err("Invalid OAuth code".into());
    }
    let sealed = store.oauth_consume(customer, "youtube", state)?;
    let verifier = vault.open(&sealed, &format!("oauth:youtube:{customer}"))?;
    let h = http()?;
    let r = h
        .post(&endpoints.token)
        .form(&[
            ("grant_type", "authorization_code"),
            ("client_id", cfg.client_id.as_str()),
            ("client_secret", cfg.secret.as_str()),
            ("redirect_uri", cfg.callback.as_str()),
            ("code", code),
            ("code_verifier", verifier.as_str()),
        ])
        .send()
        .await
        .map_err(|_| "YouTube authorization unavailable")?;
    if !r.status().is_success() {
        return Err("YouTube authorization rejected; reconnect YouTube".into());
    }
    let t: Token = r
        .json()
        .await
        .map_err(|_| "Invalid YouTube token response")?;
    if t.refresh_token.is_empty() || !t.scope.split_whitespace().any(|s| s == UPLOAD_SCOPE) {
        return Err("YouTube did not grant upload access".into());
    }
    if t.access_token.is_empty() || !(1..=86400).contains(&t.expires_in) {
        return Err("Invalid YouTube token response".into());
    }
    let r = h
        .get(&endpoints.channels)
        .query(&[("part", "snippet"), ("mine", "true")])
        .bearer_auth(&t.access_token)
        .send()
        .await
        .map_err(|_| "YouTube channel lookup unavailable")?;
    if !r.status().is_success() {
        return Err("YouTube channel verification failed".into());
    }
    let channels: Channels = r
        .json()
        .await
        .map_err(|_| "Invalid YouTube channel response")?;
    if channels.items.len() != 1 {
        return Err("Select one YouTube channel and reconnect".into());
    }
    let channel = &channels.items[0];
    if !valid_id(&channel.id) || channel.snippet.title.trim().is_empty() {
        return Err("Invalid YouTube channel response".into());
    }
    let label = account_label(customer, "youtube", &channel.id);
    let access = vault.seal(&t.access_token, &label)?;
    let refresh = vault.seal(&t.refresh_token, &label)?;
    store.upsert_verified_account(VerifiedAccount {
        customer,
        network: "youtube",
        external_id: &channel.id,
        display_name: &channel.snippet.title,
        token_enc: &access,
        refresh_enc: Some(&refresh),
        expires_at: Some(crate::now_unix() + t.expires_in),
        granted_scopes: &t.scope,
    })
}
pub(crate) fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 128
        && id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
}
pub async fn disconnect(
    store: &Store,
    vault: &Vault,
    customer: &str,
    id: &str,
) -> Result<(), String> {
    disconnect_with_endpoints(store, vault, customer, id, &Endpoints::default()).await
}
pub async fn disconnect_with_endpoints(
    store: &Store,
    vault: &Vault,
    customer: &str,
    id: &str,
    endpoints: &Endpoints,
) -> Result<(), String> {
    let (network, external, access, refresh) = store.disconnect_credentials(customer, id)?;
    if network != "youtube" {
        return Err("Incorrect social provider".into());
    }
    let token = vault.open(
        refresh.as_deref().unwrap_or(&access),
        &account_label(customer, "youtube", &external),
    );
    // Local revocation is mandatory even when Google or the vault is unavailable.
    store.disconnect_account(customer, id)?;
    if let (Ok(token), Ok(h)) = (token, http()) {
        let _ = h
            .post(&endpoints.revoke)
            .form(&[("token", token)])
            .send()
            .await;
    }
    Ok(())
}
pub async fn refresh_with_endpoints(
    store: &Store,
    vault: &Vault,
    customer: &str,
    id: &str,
    cfg: &Config,
    endpoints: &Endpoints,
) -> Result<i64, String> {
    let (network, external, encrypted, refresh, _) = store.refresh_candidate(customer, id)?;
    if network != "youtube" {
        return Err("Incorrect social provider".into());
    }
    let label = account_label(customer, "youtube", &external);
    let refresh = vault.open(
        &refresh.ok_or("Reconnect YouTube to renew upload access")?,
        &label,
    )?;
    let r = http()?
        .post(&endpoints.token)
        .form(&[
            ("grant_type", "refresh_token"),
            ("refresh_token", refresh.as_str()),
            ("client_id", cfg.client_id.as_str()),
            ("client_secret", cfg.secret.as_str()),
        ])
        .send()
        .await
        .map_err(|_| "YouTube renewal unavailable")?;
    if !r.status().is_success() {
        let status = r.status();
        let body: serde_json::Value = r.json().await.unwrap_or_default();
        if body["error"] == "invalid_grant" || status == reqwest::StatusCode::UNAUTHORIZED {
            store.mark_reauth(customer, id)?;
            return Err("Reconnect YouTube to renew upload access".into());
        }
        return Err("YouTube renewal unavailable".into());
    }
    let t: Token = r
        .json()
        .await
        .map_err(|_| "Invalid YouTube token response")?;
    if !t.scope.is_empty() && !t.scope.split_whitespace().any(|s| s == UPLOAD_SCOPE) {
        store.mark_reauth(customer, id)?;
        return Err("YouTube did not grant upload access".into());
    }
    if t.access_token.is_empty() || !(1..=86400).contains(&t.expires_in) {
        return Err("Invalid YouTube token response".into());
    }
    let next = vault.seal(&t.access_token, &label)?;
    let rotated = if t.refresh_token.is_empty() {
        None
    } else {
        Some(vault.seal(&t.refresh_token, &label)?)
    };
    let expiry = crate::now_unix() + t.expires_in;
    store.update_refreshed_token(customer, id, &encrypted, &next, rotated.as_deref(), expiry)?;
    Ok(expiry)
}
