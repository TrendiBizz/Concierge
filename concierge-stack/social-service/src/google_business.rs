//! Google Business Profile OAuth / per-location identity discovery.
//! Requires approved Trendi Google Cloud application and Business Profile API access.
//! No password capture, no implicit publishing.
use crate::{
    store::{Store, VerifiedAccount},
    vault::{account_label, Vault},
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use rand::RngCore;
use serde::Deserialize;
use sha2::Digest;
const SCOPE: &str = "https://www.googleapis.com/auth/business.manage";
#[derive(Clone)]
pub struct Config {
    pub client_id: String,
    pub secret: String,
    pub callback: String,
}
#[derive(Deserialize)]
struct Token {
    access_token: String,
    expires_in: i64,
    refresh_token: Option<String>,
    scope: Option<String>,
}
#[derive(Deserialize)]
struct Accounts {
    #[serde(default)]
    accounts: Vec<BusinessAccount>,
    #[serde(rename = "nextPageToken")]
    next_page: Option<String>,
}
#[derive(Deserialize)]
struct BusinessAccount {
    name: String,
}
#[derive(Deserialize)]
struct Locations {
    #[serde(default)]
    locations: Vec<Location>,
    #[serde(rename = "nextPageToken")]
    next_page: Option<String>,
}
#[derive(Deserialize)]
struct Location {
    name: String,
    #[serde(default)]
    title: String,
}
fn rand_state() -> String {
    let mut b = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut b);
    URL_SAFE_NO_PAD.encode(b)
}
fn http() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "Google OAuth client unavailable".into())
}
pub fn from_env() -> Result<Config, String> {
    let client_id =
        std::env::var("SOCIAL_GOOGLE_CLIENT_ID").map_err(|_| "Google OAuth not configured")?;
    let secret =
        std::env::var("SOCIAL_GOOGLE_CLIENT_SECRET").map_err(|_| "Google OAuth not configured")?;
    let callback =
        std::env::var("SOCIAL_GOOGLE_CALLBACK").map_err(|_| "Google OAuth not configured")?;
    let url = reqwest::Url::parse(&callback).map_err(|_| "Invalid Google callback")?;
    if client_id.len() < 8
        || secret.len() < 8
        || url.scheme() != "https"
        || url.host_str().is_none()
        || url.username() != ""
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
        || url.path() != "/owner/social/oauth/callback"
    {
        return Err("Invalid Google OAuth configuration".into());
    }
    Ok(Config {
        client_id,
        secret,
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
    let state = rand_state();
    let verifier = rand_state();
    let digest = sha2::Sha256::digest(verifier.as_bytes());
    let challenge = URL_SAFE_NO_PAD.encode(digest);
    let encrypted = vault.seal(&verifier, &format!("oauth:google_business:{customer}"))?;
    store.oauth_begin(customer, "google_business", &state, &encrypted, 600)?;
    let mut url = reqwest::Url::parse("https://accounts.google.com/o/oauth2/v2/auth")
        .map_err(|_| "Invalid Google auth URL")?;
    url.query_pairs_mut()
        .append_pair("client_id", &cfg.client_id)
        .append_pair("redirect_uri", &cfg.callback)
        .append_pair("response_type", "code")
        .append_pair("scope", SCOPE)
        .append_pair("access_type", "offline")
        .append_pair("prompt", "consent")
        .append_pair("state", &state)
        .append_pair("code_challenge", &challenge)
        .append_pair("code_challenge_method", "S256");
    Ok(crate::oauth::Start {
        authorization_url: url.to_string(),
        state,
    })
}
fn id(text: &str) -> Result<(), String> {
    if text.is_empty() || text.len() > 128 || !text.bytes().all(|c| c.is_ascii_digit()) {
        Err("Google Business Profile identifier invalid".into())
    } else {
        Ok(())
    }
}
pub async fn finish(
    store: &Store,
    vault: &Vault,
    customer: &str,
    cfg: &Config,
    state: &str,
    code: &str,
) -> Result<Vec<String>, String> {
    if code.is_empty() || code.len() > 2048 {
        return Err("Invalid Google authorization code".into());
    }
    let encrypted = store.oauth_consume(customer, "google_business", state)?;
    let verifier = vault.open(&encrypted, &format!("oauth:google_business:{customer}"))?;
    let http = http()?;
    let resp = http
        .post("https://oauth2.googleapis.com/token")
        .form(&[
            ("grant_type", "authorization_code"),
            ("code", code),
            ("client_id", cfg.client_id.as_str()),
            ("client_secret", cfg.secret.as_str()),
            ("redirect_uri", cfg.callback.as_str()),
            ("code_verifier", verifier.as_str()),
        ])
        .send()
        .await
        .map_err(|_| "Google authorization unavailable")?;
    if !resp.status().is_success() {
        return Err("Google OAuth rejected authorization".into());
    }
    let token: Token = resp
        .json()
        .await
        .map_err(|_| "Invalid Google OAuth token response")?;
    if token.access_token.is_empty()
        || !(1..=3600 * 24).contains(&token.expires_in)
        || token.refresh_token.as_deref().unwrap_or("").is_empty()
    {
        return Err("Google offline refresh grant not received; reconnect with consent".into());
    }
    if token
        .scope
        .as_deref()
        .is_some_and(|scope| !scope.split_whitespace().any(|x| x == SCOPE))
    {
        return Err("Google Business Profile permission missing".into());
    }
    // Enumerate business accounts and their locations; never accept a location id
    // from the browser without proof it appears in Google's authorized listing.
    let resp = http
        .get("https://mybusinessaccountmanagement.googleapis.com/v1/accounts")
        .query(&[("pageSize", "20")])
        .bearer_auth(&token.access_token)
        .send()
        .await
        .map_err(|_| "Google Business accounts unavailable")?;
    if !resp.status().is_success() {
        return Err("Google Business accounts access rejected".into());
    }
    let accounts: Accounts = resp
        .json()
        .await
        .map_err(|_| "Google accounts response invalid")?;
    if accounts.next_page.is_some() {
        return Err("Google account pagination requires operator review".into());
    }
    let mut locations = Vec::new();
    for account in accounts.accounts {
        let pieces: Vec<_> = account.name.split('/').collect();
        if pieces.len() != 2 || pieces[0] != "accounts" {
            return Err("Google account identity invalid".into());
        }
        id(pieces[1])?;
        let resp = http
            .get(format!(
                "https://mybusinessbusinessinformation.googleapis.com/v1/{}/locations",
                account.name
            ))
            .query(&[("readMask", "name,title"), ("pageSize", "100")])
            .bearer_auth(&token.access_token)
            .send()
            .await
            .map_err(|_| "Google business locations unavailable")?;
        if !resp.status().is_success() {
            return Err("Google business location access denied".into());
        }
        let list: Locations = resp
            .json()
            .await
            .map_err(|_| "Google locations response invalid")?;
        if list.next_page.is_some() {
            return Err("Google location pagination requires operator review".into());
        }
        for location in list.locations {
            let pieces: Vec<_> = location.name.split('/').collect();
            // Business Information may return locations/ID or accounts/ID/locations/ID.
            let location_id = match pieces.as_slice() {
                ["locations", loc] => *loc,
                ["accounts", acct, "locations", loc] if *acct == &account.name[9..] => *loc,
                _ => return Err("Google location identifier invalid".into()),
            };
            id(location_id)?;
            locations.push((
                format!("{}/locations/{}", account.name, location_id),
                location.title,
            ));
        }
    }
    if locations.is_empty() {
        return Err("No authorized Google Business locations found".into());
    }
    let mut output = Vec::new();
    for (resource, title) in locations {
        let label = account_label(customer, "google_business", &resource);
        let sealed = vault.seal(&token.access_token, &label)?;
        let refresh = vault.seal(token.refresh_token.as_deref().unwrap_or(""), &label)?;
        let uid = store.upsert_verified_account(VerifiedAccount {
            customer,
            network: "google_business",
            external_id: &resource,
            display_name: if title.trim().is_empty() {
                "Google Business location"
            } else {
                &title
            },
            token_enc: &sealed,
            refresh_enc: Some(&refresh),
            expires_at: Some(crate::now_unix() + token.expires_in),
            granted_scopes: SCOPE,
        })?;
        output.push(uid);
    }
    Ok(output)
}
pub fn disconnect(store: &Store, customer: &str, account_id: &str) -> Result<(), String> {
    let (network, _, _, _) = store.account(customer, account_id)?;
    if network != "google_business" {
        return Err("Wrong provider account".into());
    }
    store.disconnect_account(customer, account_id)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn google_pkce_state_is_tenant_bound() {
        let store = Store::open_memory().unwrap();
        store.create_customer("a", "A", "").unwrap();
        store.create_customer("b", "B", "").unwrap();
        let vault =
            Vault::from_base64_key(&base64::engine::general_purpose::STANDARD.encode([10u8; 32]))
                .unwrap();
        let cfg = Config {
            client_id: "google-client-id".into(),
            secret: "google-secret".into(),
            callback: "https://example.org/owner/social/oauth/callback".into(),
        };
        let started = start(&store, &vault, "a", &cfg).unwrap();
        assert!(started.authorization_url.contains("business.manage"));
        assert!(started
            .authorization_url
            .contains("code_challenge_method=S256"));
        assert!(store
            .oauth_consume("b", "google_business", &started.state)
            .is_err());
        assert!(store
            .oauth_consume("a", "google_business", &started.state)
            .is_ok());
        assert!(store
            .oauth_consume("a", "google_business", &started.state)
            .is_err());
    }
}
