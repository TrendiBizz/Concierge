//! X OAuth 2.0 confidential client + S256 PKCE. Tokens never leave the vault.
use crate::{
    store::{Store, VerifiedAccount},
    vault::{account_label, Vault},
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use rand::RngCore;
use serde::Deserialize;
use sha2::{Digest, Sha256};
pub const SCOPES: &str = "tweet.read tweet.write users.read media.write offline.access";
#[derive(Clone)]
pub struct Config {
    pub client_id: String,
    pub secret: String,
    pub callback: String,
}
pub fn from_env() -> Result<Config, String> {
    let client_id = std::env::var("SOCIAL_X_CLIENT_ID").map_err(|_| "X OAuth not configured")?;
    let secret = std::env::var("SOCIAL_X_CLIENT_SECRET").map_err(|_| "X OAuth not configured")?;
    let callback = std::env::var("SOCIAL_X_CALLBACK").map_err(|_| "X OAuth not configured")?;
    let u = reqwest::Url::parse(&callback).map_err(|_| "Invalid X callback")?;
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
        return Err("Invalid X OAuth configuration".into());
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
        .map_err(|_| "X client unavailable".into())
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
    let enc = vault.seal(&verifier, &format!("oauth:x:{customer}"))?;
    store.oauth_begin(customer, "x", &state, &enc, 600)?;
    let mut u = reqwest::Url::parse("https://x.com/i/oauth2/authorize").unwrap();
    u.query_pairs_mut()
        .append_pair("response_type", "code")
        .append_pair("client_id", &cfg.client_id)
        .append_pair("redirect_uri", &cfg.callback)
        .append_pair("scope", SCOPES)
        .append_pair("state", &state)
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
    token_type: String,
    expires_in: i64,
    scope: String,
    refresh_token: String,
}
#[derive(Deserialize)]
struct Identity {
    data: User,
}
#[derive(Deserialize)]
struct User {
    id: String,
    username: String,
}
pub fn has_scopes(scope: &str) -> bool {
    SCOPES
        .split_whitespace()
        .all(|s| scope.split_whitespace().any(|v| v == s))
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
    let enc = store.oauth_consume(customer, "x", state)?;
    let verifier = vault.open(&enc, &format!("oauth:x:{customer}"))?;
    let h = http()?;
    let r = h
        .post("https://api.x.com/2/oauth2/token")
        .basic_auth(&cfg.client_id, Some(&cfg.secret))
        .form(&[
            ("grant_type", "authorization_code"),
            ("code", code),
            ("redirect_uri", cfg.callback.as_str()),
            ("code_verifier", verifier.as_str()),
        ])
        .send()
        .await
        .map_err(|_| "X token exchange unavailable")?;
    if !r.status().is_success() {
        return Err("X rejected authorization".into());
    }
    let t: Token = r.json().await.map_err(|_| "Invalid X token response")?;
    if t.access_token.is_empty()
        || t.refresh_token.is_empty()
        || !t.token_type.eq_ignore_ascii_case("bearer")
        || !(1..=5_184_000).contains(&t.expires_in)
        || !has_scopes(&t.scope)
    {
        return Err("X account and publishing permissions were not granted".into());
    }
    let r = h
        .get("https://api.x.com/2/users/me")
        .bearer_auth(&t.access_token)
        .send()
        .await
        .map_err(|_| "X identity unavailable")?;
    if !r.status().is_success() {
        return Err("X identity verification failed; check API credits".into());
    }
    let p: Identity = r.json().await.map_err(|_| "Invalid X identity response")?;
    if p.data.id.is_empty()
        || !p.data.id.bytes().all(|b| b.is_ascii_digit())
        || p.data.username.is_empty()
    {
        return Err("X identity missing".into());
    }
    let label = account_label(customer, "x", &p.data.id);
    let access = vault.seal(&t.access_token, &label)?;
    let refresh = vault.seal(&t.refresh_token, &label)?;
    store.upsert_verified_account(VerifiedAccount {
        customer,
        network: "x",
        external_id: &p.data.id,
        display_name: &format!("@{}", p.data.username),
        token_enc: &access,
        refresh_enc: Some(&refresh),
        expires_at: Some(crate::now_unix() + t.expires_in),
        granted_scopes: &t.scope,
    })
}
pub async fn disconnect(
    store: &Store,
    vault: &Vault,
    customer: &str,
    id: &str,
    cfg: &Config,
) -> Result<(), String> {
    let (network, external, enc, _) = store.account(customer, id)?;
    if network != "x" {
        return Err("Not an X account".into());
    }
    let token = vault.open(&enc, &account_label(customer, "x", &external))?;
    let r = http()?
        .post("https://api.x.com/2/oauth2/revoke")
        .basic_auth(&cfg.client_id, Some(&cfg.secret))
        .form(&[
            ("token", token.as_str()),
            ("token_type_hint", "access_token"),
        ])
        .send()
        .await
        .map_err(|_| "X revocation unavailable")?;
    if !r.status().is_success() {
        return Err("X revocation could not be confirmed".into());
    }
    store.disconnect_account(customer, id)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pkce_is_tenant_bound_single_use_and_minimally_scoped() {
        let s = Store::open_memory().unwrap();
        s.create_customer("a", "A", "").unwrap();
        s.create_customer("b", "B", "").unwrap();
        let v =
            Vault::from_base64_key(&base64::engine::general_purpose::STANDARD.encode([22u8; 32]))
                .unwrap();
        let c = Config {
            client_id: "client".into(),
            secret: "server-secret".into(),
            callback: "https://example.com/owner/social/oauth/callback".into(),
        };
        let a = start(&s, &v, "a", &c).unwrap();
        let b = start(&s, &v, "a", &c).unwrap();
        assert_ne!(a.state, b.state);
        let u = reqwest::Url::parse(&a.authorization_url).unwrap();
        let q: std::collections::HashMap<_, _> = u.query_pairs().into_owned().collect();
        assert_eq!(u.host_str(), Some("x.com"));
        assert_eq!(q["scope"], SCOPES);
        assert_eq!(q["code_challenge_method"], "S256");
        assert!(!a.authorization_url.contains("server-secret"));
        assert!(s.oauth_consume("b", "x", &a.state).is_err());
        assert!(s.oauth_consume("a", "linkedin", &a.state).is_err());
        let enc = s.oauth_consume("a", "x", &a.state).unwrap();
        let verifier = v.open(&enc, "oauth:x:a").unwrap();
        assert_eq!(
            q["code_challenge"],
            URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()))
        );
        assert!(s.oauth_consume("a", "x", &a.state).is_err());
        assert!(has_scopes(SCOPES));
        assert!(!has_scopes("tweet.read users.read"));
    }
}
