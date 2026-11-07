//! Meta OAuth for Facebook Pages and Instagram professional accounts.
//! Server-side confidential-client authorization, tenant-bound single-use state.
//! No live publication is enabled by connecting an account.
use crate::{
    store::{Store, VerifiedAccount},
    vault::{account_label, Vault},
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use rand::RngCore;
use serde::Deserialize;

const CALLBACK: &str = "/owner/social/oauth/callback";
const FB_SCOPE: &str = "pages_show_list,pages_manage_posts,pages_read_engagement";
const IG_SCOPE: &str = "instagram_business_basic,instagram_business_content_publish";

#[derive(Clone)]
pub struct Config {
    pub network: &'static str,
    pub id: String,
    pub secret: String,
    pub callback: String,
    pub version: String,
}
#[derive(Deserialize)]
struct CodeToken {
    access_token: String,
    #[serde(default)]
    expires_in: Option<i64>,
}
#[derive(Deserialize)]
struct Page {
    id: String,
    name: String,
    access_token: String,
    #[serde(default)]
    tasks: Vec<String>,
}
#[derive(Deserialize)]
struct PageList {
    data: Vec<Page>,
    #[serde(default)]
    paging: Option<serde_json::Value>,
}
#[derive(Deserialize)]
struct IgProfile {
    id: String,
    #[serde(default)]
    username: String,
}
#[derive(Deserialize)]
struct DebugResponse {
    data: DebugData,
}
#[derive(Deserialize)]
struct DebugData {
    is_valid: bool,
    #[serde(default)]
    scopes: Vec<String>,
    #[serde(default)]
    expires_at: Option<i64>,
}

fn random_state() -> String {
    let mut b = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut b);
    URL_SAFE_NO_PAD.encode(b)
}
pub fn from_env(network: &'static str) -> Result<Config, String> {
    let prefix = match network {
        "facebook" => "SOCIAL_FACEBOOK",
        "instagram" => "SOCIAL_INSTAGRAM",
        _ => return Err("Unsupported Meta provider".into()),
    };
    let id =
        std::env::var(format!("{prefix}_CLIENT_ID")).map_err(|_| "Meta OAuth not configured")?;
    let secret = std::env::var(format!("{prefix}_CLIENT_SECRET"))
        .map_err(|_| "Meta OAuth not configured")?;
    let callback =
        std::env::var(format!("{prefix}_CALLBACK")).map_err(|_| "Meta OAuth not configured")?;
    let version = std::env::var("SOCIAL_META_GRAPH_VERSION").unwrap_or_else(|_| "v24.0".into());
    let url = reqwest::Url::parse(&callback).map_err(|_| "Invalid Meta callback")?;
    if id.len() < 5
        || secret.len() < 8
        || !version.starts_with('v')
        || !version[1..].chars().all(|c| c.is_ascii_digit() || c == '.')
        || url.scheme() != "https"
        || url.host_str().is_none()
        || url.username() != ""
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
        || url.path() != CALLBACK
    {
        return Err("Invalid Meta OAuth configuration".into());
    }
    Ok(Config {
        network,
        id,
        secret,
        callback,
        version,
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
    let nonce = vault.seal(
        &random_state(),
        &format!("oauth:{}:{customer}", cfg.network),
    )?;
    store.oauth_begin(customer, cfg.network, &state, &nonce, 600)?;
    let endpoint = match cfg.network {
        "instagram" => "https://www.instagram.com/oauth/authorize",
        "facebook" => "https://www.facebook.com/dialog/oauth",
        _ => return Err("Unsupported Meta provider".into()),
    };
    let mut url = reqwest::Url::parse(endpoint).map_err(|_| "Meta authorization URL invalid")?;
    url.query_pairs_mut()
        .append_pair("client_id", &cfg.id)
        .append_pair("redirect_uri", &cfg.callback)
        .append_pair("response_type", "code")
        .append_pair(
            "scope",
            if cfg.network == "facebook" {
                FB_SCOPE
            } else {
                IG_SCOPE
            },
        )
        .append_pair("state", &state);
    Ok(crate::oauth::Start {
        authorization_url: url.to_string(),
        state,
    })
}
fn client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "Meta HTTP client unavailable".into())
}
fn expiry(seconds: Option<i64>) -> Option<i64> {
    seconds
        .filter(|v| (1..=5_184_000).contains(v))
        .map(|v| crate::now_unix() + v)
}
fn check_id(value: &str) -> Result<(), String> {
    if value.is_empty()
        || value.len() > 256
        || !value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-' || b == b'.')
    {
        return Err("Meta account identity invalid".into());
    }
    Ok(())
}
async fn instagram_finish(
    store: &Store,
    vault: &Vault,
    customer: &str,
    cfg: &Config,
    code: &str,
) -> Result<Vec<String>, String> {
    let http = client()?;
    let resp = http
        .post("https://api.instagram.com/oauth/access_token")
        .form(&[
            ("client_id", cfg.id.as_str()),
            ("client_secret", cfg.secret.as_str()),
            ("grant_type", "authorization_code"),
            ("redirect_uri", cfg.callback.as_str()),
            ("code", code),
        ])
        .send()
        .await
        .map_err(|_| "Instagram authorization unavailable")?;
    if !resp.status().is_success() {
        return Err("Instagram authorization rejected".into());
    }
    let short: CodeToken = resp
        .json()
        .await
        .map_err(|_| "Invalid Instagram token response")?;
    if short.access_token.is_empty() {
        return Err("Instagram access token missing".into());
    }
    // Instagram Login exchanges a short token for a long-lived token. Never store the short token.
    let resp = http
        .get("https://graph.instagram.com/access_token")
        .query(&[
            ("grant_type", "ig_exchange_token"),
            ("client_secret", cfg.secret.as_str()),
            ("access_token", short.access_token.as_str()),
        ])
        .send()
        .await
        .map_err(|_| "Instagram long-lived exchange unavailable")?;
    if !resp.status().is_success() {
        return Err("Instagram long-lived token rejected".into());
    }
    let long: CodeToken = resp
        .json()
        .await
        .map_err(|_| "Instagram long-lived token invalid")?;
    if long.access_token.is_empty() || expiry(long.expires_in).is_none() {
        return Err("Instagram long-lived token missing expiry".into());
    }
    let resp = http
        .get("https://graph.instagram.com/me")
        .query(&[("fields", "id,username")])
        .bearer_auth(&long.access_token)
        .send()
        .await
        .map_err(|_| "Instagram profile unavailable")?;
    if !resp.status().is_success() {
        return Err("Instagram identity not verified".into());
    }
    let profile: IgProfile = resp.json().await.map_err(|_| "Invalid Instagram profile")?;
    check_id(&profile.id)?;
    let label = account_label(customer, "instagram", &profile.id);
    let sealed = vault.seal(&long.access_token, &label)?;
    let id = store.upsert_verified_account(VerifiedAccount {
        customer,
        network: "instagram",
        external_id: &profile.id,
        display_name: if profile.username.trim().is_empty() {
            "Instagram professional account"
        } else {
            &profile.username
        },
        token_enc: &sealed,
        refresh_enc: None,
        expires_at: expiry(long.expires_in),
        granted_scopes: IG_SCOPE,
    })?;
    Ok(vec![id])
}
async fn facebook_finish(
    store: &Store,
    vault: &Vault,
    customer: &str,
    cfg: &Config,
    code: &str,
) -> Result<Vec<String>, String> {
    let http = client()?;
    let graph = format!("https://graph.facebook.com/{}", cfg.version);
    let resp = http
        .get(format!("{graph}/oauth/access_token"))
        .query(&[
            ("client_id", cfg.id.as_str()),
            ("client_secret", cfg.secret.as_str()),
            ("redirect_uri", cfg.callback.as_str()),
            ("code", code),
        ])
        .send()
        .await
        .map_err(|_| "Facebook authorization unavailable")?;
    if !resp.status().is_success() {
        return Err("Facebook authorization rejected".into());
    }
    let short: CodeToken = resp.json().await.map_err(|_| "Facebook token invalid")?;
    if short.access_token.is_empty() {
        return Err("Facebook token missing".into());
    }
    let resp = http
        .get(format!("{graph}/oauth/access_token"))
        .query(&[
            ("grant_type", "fb_exchange_token"),
            ("client_id", cfg.id.as_str()),
            ("client_secret", cfg.secret.as_str()),
            ("fb_exchange_token", short.access_token.as_str()),
        ])
        .send()
        .await
        .map_err(|_| "Facebook long-lived token unavailable")?;
    if !resp.status().is_success() {
        return Err("Facebook long-lived token rejected".into());
    }
    let long: CodeToken = resp
        .json()
        .await
        .map_err(|_| "Facebook long-lived token invalid")?;
    if long.access_token.is_empty() || expiry(long.expires_in).is_none() {
        return Err("Facebook long-lived token missing expiry".into());
    }
    // Check the actual grant, not only the scopes requested in the login dialog.
    let debug = http
        .get(format!("{graph}/debug_token"))
        .query(&[
            ("input_token", long.access_token.as_str()),
            (
                "access_token",
                format!("{}|{}", cfg.id, cfg.secret).as_str(),
            ),
        ])
        .send()
        .await
        .map_err(|_| "Facebook permission check unavailable")?;
    if !debug.status().is_success() {
        return Err("Facebook permissions not verified".into());
    }
    let granted: DebugResponse = debug
        .json()
        .await
        .map_err(|_| "Facebook permission response invalid")?;
    if !granted.data.is_valid
        || ![
            "pages_show_list",
            "pages_manage_posts",
            "pages_read_engagement",
        ]
        .iter()
        .all(|scope| granted.data.scopes.iter().any(|s| s == scope))
    {
        return Err("Facebook Page permissions not granted".into());
    }
    let response = http
        .get(format!("{graph}/me/accounts"))
        .query(&[("fields", "id,name,access_token,tasks"), ("limit", "100")])
        .bearer_auth(&long.access_token)
        .send()
        .await
        .map_err(|_| "Facebook Page lookup unavailable")?;
    if !response.status().is_success() {
        return Err("Facebook Page lookup rejected".into());
    }
    let pages: PageList = response
        .json()
        .await
        .map_err(|_| "Facebook Page list invalid")?;
    // Fail closed rather than silently omit a second page.
    if pages
        .paging
        .as_ref()
        .is_some_and(|p| p.get("next").is_some())
    {
        return Err("Facebook account has too many Pages; pagination not yet supported".into());
    }
    if pages.data.is_empty() {
        return Err("No authorized Facebook Pages found".into());
    }
    // Validate the entire response before writing any credentials.
    for page in &pages.data {
        check_id(&page.id)?;
        if page.access_token.is_empty()
            || page.name.trim().is_empty()
            || !page
                .tasks
                .iter()
                .any(|task| task == "CREATE_CONTENT" || task == "MANAGE")
        {
            return Err("Facebook Page lacks content management access".into());
        }
    }
    let mut result = Vec::new();
    for page in pages.data {
        let label = account_label(customer, "facebook", &page.id);
        let sealed = vault.seal(&page.access_token, &label)?;
        let id = store.upsert_verified_account(VerifiedAccount {
            customer,
            network: "facebook",
            external_id: &page.id,
            display_name: &page.name,
            token_enc: &sealed,
            refresh_enc: None,
            // Page tokens may not expose an expiry, but upstream grants remain revocable.
            expires_at: granted.data.expires_at.filter(|v| *v > crate::now_unix()),
            granted_scopes: FB_SCOPE,
        })?;
        result.push(id);
    }
    Ok(result)
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
        return Err("Invalid Meta authorization code".into());
    }
    let _ = store.oauth_consume(customer, cfg.network, state)?;
    match cfg.network {
        "instagram" => instagram_finish(store, vault, customer, cfg, code).await,
        "facebook" => facebook_finish(store, vault, customer, cfg, code).await,
        _ => Err("Unsupported Meta provider".into()),
    }
}
pub fn disconnect(
    store: &Store,
    customer: &str,
    account_id: &str,
    network: &str,
) -> Result<(), String> {
    let (found, _, _, _) = store.account(customer, account_id)?;
    if found != network {
        return Err("Incorrect social provider".into());
    }
    // Destroy the local token immediately. Provider-level withdrawal is done in Meta's apps/settings.
    store.disconnect_account(customer, account_id)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn link_state_is_tenant_scoped_and_single_use() {
        let store = Store::open_memory().unwrap();
        let vault =
            Vault::from_base64_key(&base64::engine::general_purpose::STANDARD.encode([7u8; 32]))
                .unwrap();
        store.create_customer("a", "A", "").unwrap();
        store.create_customer("b", "B", "").unwrap();
        let cfg = Config {
            network: "instagram",
            id: "123456".into(),
            secret: "some-secret".into(),
            callback: "https://example.com/owner/social/oauth/callback".into(),
            version: "v24.0".into(),
        };
        let a = start(&store, &vault, "a", &cfg).unwrap();
        assert!(a
            .authorization_url
            .starts_with("https://www.instagram.com/oauth/authorize"));
        assert!(store.oauth_consume("b", "instagram", &a.state).is_err());
        assert!(store.oauth_consume("a", "facebook", &a.state).is_err());
        assert!(store.oauth_consume("a", "instagram", &a.state).is_ok());
        assert!(store.oauth_consume("a", "instagram", &a.state).is_err());
    }
    #[test]
    fn facebook_scopes_and_url_are_scoped() {
        let store = Store::open_memory().unwrap();
        let vault =
            Vault::from_base64_key(&base64::engine::general_purpose::STANDARD.encode([8u8; 32]))
                .unwrap();
        store.create_customer("a", "A", "").unwrap();
        let cfg = Config {
            network: "facebook",
            id: "123456".into(),
            secret: "some-secret".into(),
            callback: "https://example.com/owner/social/oauth/callback".into(),
            version: "v24.0".into(),
        };
        let a = start(&store, &vault, "a", &cfg).unwrap();
        assert!(a.authorization_url.contains("pages_manage_posts"));
        assert!(a.authorization_url.contains("www.facebook.com"));
    }
}
