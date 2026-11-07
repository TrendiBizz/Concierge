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
const IG_FACEBOOK_SCOPE: &str =
    "pages_show_list,pages_read_engagement,instagram_basic,instagram_content_publish";

#[derive(Clone)]
pub struct Config {
    pub network: &'static str,
    pub id: String,
    pub secret: String,
    pub callback: String,
    pub version: String,
    pub via_facebook: bool,
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
    #[serde(default)]
    instagram_business_account: Option<IgProfile>,
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
    #[serde(default)]
    granular_scopes: Vec<GranularScope>,
}
#[derive(Deserialize)]
struct GranularScope {
    scope: String,
    #[serde(default)]
    target_ids: Vec<String>,
}

// Operator-owned Page IDs are *candidates*, never authorizations. Each candidate
// must be bound to the new OAuth token's Page-level grant and separately checked
// with Meta before its Page token can be encrypted and stored.
fn authorized_page_candidates(grant: &DebugData) -> Vec<String> {
    let mut ids = std::collections::BTreeSet::new();
    // These granular grants are Meta's binding of the user's OAuth consent to
    // specific Page resources. No token-free or caller-supplied IDs are trusted.
    for entry in &grant.granular_scopes {
        if [
            "pages_show_list",
            "pages_manage_posts",
            "pages_read_engagement",
        ]
        .contains(&entry.scope.as_str())
        {
            for id in &entry.target_ids {
                if !id.is_empty() && id.bytes().all(|c| c.is_ascii_digit()) && id.len() <= 30 {
                    ids.insert(id.clone());
                }
            }
        }
    }
    ids.into_iter().collect()
}
// Staging-only per-tenant hint for a Page selected by the owner.
// A hint is NOT proof of consent: Meta must return a Page token under the
// newly authorized user token and the Page must have publishing tasks.
fn operator_page_candidates(config: &str, customer: &str) -> Vec<String> {
    let mut ids = std::collections::BTreeSet::new();
    for mapping in config.split(',').take(20) {
        if let Some((tenant, id)) = mapping.trim().split_once(':') {
            if tenant == customer
                && !id.is_empty()
                && id.len() <= 30
                && id.bytes().all(|c| c.is_ascii_digit())
            {
                ids.insert(id.to_string());
            }
        }
    }
    ids.into_iter().collect()
}
fn can_manage_content(tasks: &[String]) -> bool {
    tasks.iter().any(|t| {
        matches!(
            t.as_str(),
            "CREATE_CONTENT"
                | "MANAGE"
                | "PROFILE_PLUS_CREATE_CONTENT"
                | "PROFILE_PLUS_MANAGE"
                | "PROFILE_PLUS_FULL_CONTROL"
        )
    })
}
async fn discover_selected_pages(
    http: &reqwest::Client,
    graph: &str,
    user_token: &str,
    grant: &DebugData,
    fields: &str,
    customer: &str,
) -> Result<Vec<Page>, String> {
    let response = http
        .get(format!("{graph}/me/accounts"))
        .query(&[("fields", fields), ("limit", "100")])
        .bearer_auth(user_token)
        .send()
        .await
        .map_err(|_| "Facebook Page lookup unavailable")?;
    if !response.status().is_success() {
        return Err("Facebook Page lookup rejected".into());
    }
    let listed: PageList = response
        .json()
        .await
        .map_err(|_| "Facebook Page list invalid")?;
    if listed
        .paging
        .as_ref()
        .is_some_and(|p| p.get("next").is_some())
    {
        return Err("Facebook account has too many Pages; pagination not yet supported".into());
    }
    if !listed.data.is_empty() {
        return Ok(listed.data);
    }
    let granular = authorized_page_candidates(grant);
    let mut selected = granular.clone();
    let operator = std::env::var("SOCIAL_FACEBOOK_PAGE_HINTS").unwrap_or_default();
    for id in operator_page_candidates(&operator, customer) {
        if !granular.is_empty() && !granular.contains(&id) {
            continue;
        }
        if !selected.contains(&id) {
            selected.push(id);
        }
    }
    if selected.len() > 25 {
        return Err("Too many selected Facebook Pages for safe discovery".into());
    }
    let mut result = Vec::new();
    for id in selected {
        let response = http
            .get(format!("{graph}/{id}"))
            .query(&[("fields", fields)])
            .bearer_auth(user_token)
            .send()
            .await
            .map_err(|_| "Facebook Page lookup unavailable")?;
        if !response.status().is_success() {
            // A selected Page still might not be accessible by this user.
            // Never synthesize a Page token or claim this Page is connected.
            continue;
        }
        if let Ok(page) = response.json::<Page>().await {
            if page.id == id && !page.access_token.is_empty() {
                result.push(page);
            }
        }
    }
    Ok(result)
}
fn random_state() -> String {
    let mut b = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut b);
    URL_SAFE_NO_PAD.encode(b)
}
pub fn from_env(network: &'static str) -> Result<Config, String> {
    let via_facebook = network == "instagram"
        && std::env::var("SOCIAL_INSTAGRAM_LOGIN_MODE").as_deref() != Ok("instagram");
    let prefix = match network {
        "facebook" => "SOCIAL_FACEBOOK",
        "instagram" if via_facebook => "SOCIAL_FACEBOOK",
        "instagram" => "SOCIAL_INSTAGRAM",
        _ => return Err("Unsupported Meta provider".into()),
    };
    let id =
        std::env::var(format!("{prefix}_CLIENT_ID")).map_err(|_| "Meta OAuth not configured")?;
    let secret = std::env::var(format!("{prefix}_CLIENT_SECRET"))
        .map_err(|_| "Meta OAuth not configured")?;
    let callback =
        std::env::var(format!("{prefix}_CALLBACK")).map_err(|_| "Meta OAuth not configured")?;
    let version = std::env::var("SOCIAL_META_GRAPH_VERSION").unwrap_or_else(|_| "v27.0".into());
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
        via_facebook,
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
        "instagram" if !cfg.via_facebook => "https://www.instagram.com/oauth/authorize",
        "instagram" => "https://www.facebook.com/dialog/oauth",
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
            } else if cfg.via_facebook {
                IG_FACEBOOK_SCOPE
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
/// Instagram Graph API with Facebook Login (the product installed in SocialSync).
/// Only Pages containing a linked professional Instagram account are eligible.
async fn instagram_facebook_finish(
    store: &Store,
    vault: &Vault,
    customer: &str,
    cfg: &Config,
    code: &str,
) -> Result<Vec<String>, String> {
    let http = client()?;
    let graph = format!("https://graph.facebook.com/{}", cfg.version);
    let short_resp = http
        .get(format!("{graph}/oauth/access_token"))
        .query(&[
            ("client_id", cfg.id.as_str()),
            ("client_secret", cfg.secret.as_str()),
            ("redirect_uri", cfg.callback.as_str()),
            ("code", code),
        ])
        .send()
        .await
        .map_err(|_| "Meta authorization unavailable")?;
    if !short_resp.status().is_success() {
        return Err("Meta authorization rejected".into());
    }
    let short: CodeToken = short_resp.json().await.map_err(|_| "Invalid Meta token")?;
    if short.access_token.is_empty() {
        return Err("Meta token missing".into());
    }
    let long_resp = http
        .get(format!("{graph}/oauth/access_token"))
        .query(&[
            ("grant_type", "fb_exchange_token"),
            ("client_id", cfg.id.as_str()),
            ("client_secret", cfg.secret.as_str()),
            ("fb_exchange_token", short.access_token.as_str()),
        ])
        .send()
        .await
        .map_err(|_| "Meta long-lived exchange unavailable")?;
    if !long_resp.status().is_success() {
        return Err("Meta long-lived token rejected".into());
    }
    let long: CodeToken = long_resp
        .json()
        .await
        .map_err(|_| "Invalid Meta long-lived token")?;
    if long.access_token.is_empty() || expiry(long.expires_in).is_none() {
        return Err("Meta token missing expiry".into());
    }
    // Verify actual app, scopes and validity, not just authorization dialog text.
    let app_token = format!("{}|{}", cfg.id, cfg.secret);
    let debug_resp = http
        .get(format!("{graph}/debug_token"))
        .query(&[
            ("input_token", long.access_token.as_str()),
            ("access_token", app_token.as_str()),
        ])
        .send()
        .await
        .map_err(|_| "Meta permissions unavailable")?;
    if !debug_resp.status().is_success() {
        return Err("Meta permission lookup rejected".into());
    }
    let granted: DebugResponse = debug_resp
        .json()
        .await
        .map_err(|_| "Meta permission response invalid")?;
    if !granted.data.is_valid
        || !IG_FACEBOOK_SCOPE
            .split(',')
            .all(|required| granted.data.scopes.iter().any(|actual| actual == required))
    {
        return Err("Instagram Graph API permissions not granted".into());
    }
    let pages = discover_selected_pages(
        &http,
        &graph,
        &long.access_token,
        &granted.data,
        "id,name,access_token,tasks,instagram_business_account{id,username}",
        customer,
    )
    .await?;
    let mut eligible = Vec::new();
    for page in pages {
        check_id(&page.id)?;
        let Some(profile) = page.instagram_business_account else {
            continue;
        };
        check_id(&profile.id)?;
        if !can_manage_content(&page.tasks) || page.access_token.is_empty() {
            return Err("Linked Instagram Page lacks content management access".into());
        }
        eligible.push((profile, page.access_token));
    }
    if eligible.is_empty() {
        return Err("No linked professional Instagram account found".into());
    }
    let mut linked = Vec::new();
    for (profile, page_token) in eligible {
        let label = account_label(customer, "instagram", &profile.id);
        let sealed = vault.seal(&page_token, &label)?;
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
            expires_at: None,
            granted_scopes: IG_FACEBOOK_SCOPE,
        })?;
        linked.push(id);
    }
    Ok(linked)
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
    let pages = discover_selected_pages(
        &http,
        &graph,
        &long.access_token,
        &granted.data,
        "id,name,access_token,tasks",
        customer,
    )
    .await?;
    if pages.is_empty() {
        return Err("No authorized Facebook Pages found".into());
    }
    // Validate the entire response before writing any credentials.
    for page in &pages {
        check_id(&page.id)?;
        if page.access_token.is_empty()
            || page.name.trim().is_empty()
            || !can_manage_content(&page.tasks)
        {
            return Err("Facebook Page lacks content management access".into());
        }
    }
    let mut result = Vec::new();
    for page in pages {
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
        "instagram" if cfg.via_facebook => {
            instagram_facebook_finish(store, vault, customer, cfg, code).await
        }
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
            version: "v27.0".into(),
            via_facebook: false,
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
    fn socialsync_uses_facebook_login_for_linked_instagram() {
        let store = Store::open_memory().unwrap();
        let vault =
            Vault::from_base64_key(&base64::engine::general_purpose::STANDARD.encode([9u8; 32]))
                .unwrap();
        store.create_customer("a", "A", "").unwrap();
        let cfg = Config {
            network: "instagram",
            id: "676274422041376".into(),
            secret: "some-secret".into(),
            callback: "https://example.com/owner/social/oauth/callback".into(),
            version: "v27.0".into(),
            via_facebook: true,
        };
        let started = start(&store, &vault, "a", &cfg).unwrap();
        assert!(started
            .authorization_url
            .starts_with("https://www.facebook.com/dialog/oauth"));
        assert!(started
            .authorization_url
            .contains("instagram_content_publish"));
        assert!(!started
            .authorization_url
            .contains("instagram_business_content_publish"));
    }
    #[test]
    fn page_hint_is_tenant_scoped_and_never_authorization() {
        let hints = "trendi-oauth-staging:270235042840463,tenant-b:12345,tenant-b:../1";
        assert_eq!(
            operator_page_candidates(hints, "trendi-oauth-staging"),
            vec!["270235042840463".to_string()]
        );
        assert_eq!(
            operator_page_candidates(hints, "tenant-b"),
            vec!["12345".to_string()]
        );
        assert!(operator_page_candidates(hints, "other").is_empty());
        assert!(can_manage_content(&["PROFILE_PLUS_CREATE_CONTENT".into()]));
        assert!(can_manage_content(&["PROFILE_PLUS_FULL_CONTROL".into()]));
        assert!(!can_manage_content(&["PROFILE_PLUS_ADVERTISE".into()]));
    }
    #[test]
    fn page_candidates_require_granular_oauth_grants() {
        let blank = DebugData {
            is_valid: true,
            scopes: vec!["pages_show_list".into()],
            expires_at: None,
            granular_scopes: vec![],
        };
        assert!(authorized_page_candidates(&blank).is_empty());
        let allowed = DebugData {
            granular_scopes: vec![
                GranularScope {
                    scope: "pages_show_list".into(),
                    target_ids: vec!["270235042840463".into(), "../1".into()],
                },
                GranularScope {
                    scope: "unrelated".into(),
                    target_ids: vec!["123456".into()],
                },
            ],
            ..blank
        };
        assert_eq!(
            authorized_page_candidates(&allowed),
            vec!["270235042840463".to_string()]
        );
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
            version: "v27.0".into(),
            via_facebook: false,
        };
        let a = start(&store, &vault, "a", &cfg).unwrap();
        assert!(a.authorization_url.contains("pages_manage_posts"));
        assert!(a.authorization_url.contains("www.facebook.com"));
    }
}
