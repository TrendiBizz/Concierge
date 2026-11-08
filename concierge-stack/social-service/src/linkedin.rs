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
// Account linking only. Posting requires separately approved w_member_social.
const SCOPE: &str = "openid profile";

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
// Canonicalize provider response separators before permission checks and storage.
// Authorization requests still use the standard space-delimited SCOPE value.
pub(crate) fn normalize_scopes(scopes: &str) -> String {
    scopes
        .split(|c: char| c.is_whitespace() || c == ',')
        .filter(|scope| !scope.is_empty())
        .collect::<std::collections::BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>()
        .join(" ")
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
        || url.path() != "/owner/social/oauth/callback"
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
    finish_at(store, vault, customer, cfg, state, code, (TOKEN, USERINFO)).await
}
// Fixed provider URLs in production; loopback endpoints exercise the entire flow in tests.
async fn finish_at(
    store: &Store,
    vault: &Vault,
    customer: &str,
    cfg: &Config,
    state: &str,
    code: &str,
    endpoints: (&str, &str),
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
        .post(endpoints.0)
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
        eprintln!(
            "linkedin_oauth_failure phase=token_exchange status={}",
            response.status().as_u16()
        );
        return Err("LinkedIn authorization was rejected".into());
    }
    let token: Token = response
        .json()
        .await
        .map_err(|_| "Invalid LinkedIn OAuth token response")?;
    if token.access_token.is_empty() || !(1..=31_536_000).contains(&token.expires_in) {
        return Err("Invalid LinkedIn OAuth token expiry".into());
    }
    // LinkedIn may omit the scope field from a successful token response.
    // When supplied, require all requested OIDC scopes; when absent, verify
    // the token against the authenticated LinkedIn userinfo endpoint below.
    // Never infer publishing rights from a missing scope field.
    let normalized_scopes = normalize_scopes(&token.scope);
    if !token.scope.trim().is_empty()
        && !SCOPE.split_whitespace().all(|required| {
            normalized_scopes
                .split_whitespace()
                .any(|actual| actual == required)
        })
    {
        // Never log raw scopes or any provider payload, credential or identity.
        eprintln!(
            "linkedin_oauth_failure phase=scope_validation at={} comma={} whitespace={} openid={} profile={}",
            crate::now_unix(),
            token.scope.contains(','),
            token.scope.chars().any(char::is_whitespace),
            normalized_scopes.split_whitespace().any(|scope| scope == "openid"),
            normalized_scopes.split_whitespace().any(|scope| scope == "profile"),
        );
        return Err("LinkedIn did not grant the requested permissions".into());
    }
    let response = client
        .get(endpoints.1)
        .bearer_auth(&token.access_token)
        .send()
        .await
        .map_err(|_| "LinkedIn profile lookup unavailable")?;
    if !response.status().is_success() {
        eprintln!(
            "linkedin_oauth_failure phase=profile status={}",
            response.status().as_u16()
        );
        return Err("LinkedIn profile verification failed".into());
    }
    let profile: Profile = response
        .json()
        .await
        .map_err(|_| "Invalid LinkedIn profile")?;
    if profile.sub.is_empty() || profile.sub.len() > 256 {
        return Err("LinkedIn profile missing identity".into());
    }
    // Successful userinfo retrieval establishes account-linking access when
    // LinkedIn omitted scope metadata. Do not infer w_member_social.
    let verified_scopes = if token.scope.trim().is_empty() {
        SCOPE
    } else {
        &normalized_scopes
    };
    let label = crate::vault::account_label(customer, "linkedin", &profile.sub);
    let access_enc = vault.seal(&token.access_token, &label).map_err(|_| {
        eprintln!("linkedin_oauth_failure phase=credential_encryption");
        "LinkedIn credential encryption failed".to_string()
    })?;
    let refresh_enc = token
        .refresh_token
        .as_deref()
        .map(|value| vault.seal(value, &label))
        .transpose()
        .map_err(|_| {
            eprintln!("linkedin_oauth_failure phase=refresh_encryption");
            "LinkedIn credential encryption failed".to_string()
        })?;
    store
        .upsert_verified_account(crate::store::VerifiedAccount {
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
            granted_scopes: verified_scopes,
        })
        .inspect(|_| {
            eprintln!(
                "linkedin_oauth_success phase=account_storage at={}",
                crate::now_unix()
            );
        })
        .map_err(|_| {
            // Do not log SQLite details or any account, OAuth code, or token data.
            eprintln!("linkedin_oauth_failure phase=account_storage");
            "LinkedIn account storage failed".to_string()
        })
}
#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn linkedin_finish_scope_formatting_and_profile_verification() {
        use axum::{
            http::StatusCode,
            routing::{get, post},
            Json, Router,
        };
        use std::sync::{
            atomic::{AtomicUsize, Ordering},
            Arc,
        };
        // Replay token formatting through real HTTP exchange, profile lookup,
        // encryption and tenant-scoped storage, rather than duplicating the parser.
        for (scope, profile_status, subject, accepted) in [
            (Some("openid profile"), StatusCode::OK, "member-1", true),
            (
                Some(" \tprofile\n openid  "),
                StatusCode::OK,
                "member-1",
                true,
            ),
            (Some("openid,profile"), StatusCode::OK, "member-1", true),
            (
                Some(" profile, \topenid \n"),
                StatusCode::OK,
                "member-1",
                true,
            ),
            (None, StatusCode::OK, "member-1", true),
            (Some("  \t"), StatusCode::OK, "member-1", true),
            (Some("openid"), StatusCode::OK, "member-1", false),
            (
                Some("openid,profile_extra"),
                StatusCode::OK,
                "member-1",
                false,
            ),
            (Some(", ,"), StatusCode::OK, "member-1", false),
            (
                Some("openid%2520profile"),
                StatusCode::OK,
                "member-1",
                false,
            ),
            (None, StatusCode::FORBIDDEN, "member-1", false),
            (Some("openid profile"), StatusCode::OK, "", false),
        ] {
            let mut token = serde_json::json!({"access_token":"synthetic-only", "expires_in":3600});
            if let Some(value) = scope {
                token["scope"] = value.into();
            }
            let profile_hits = Arc::new(AtomicUsize::new(0));
            let hits = profile_hits.clone();
            let app = Router::new()
                .route(
                    "/token",
                    post(move || {
                        let value = token.clone();
                        async move { Json(value) }
                    }),
                )
                .route(
                    "/userinfo",
                    get(move |headers: axum::http::HeaderMap| {
                        let hits = hits.clone();
                        async move {
                            assert_eq!(headers["authorization"], "Bearer synthetic-only");
                            hits.fetch_add(1, Ordering::SeqCst);
                            (
                                profile_status,
                                Json(serde_json::json!({"sub":subject,"name":"Synthetic member"})),
                            )
                        }
                    }),
                );
            let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
            let base = format!("http://{}", listener.local_addr().unwrap());
            let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
            let store = Store::open_memory().unwrap();
            store.create_customer("a", "A", "").unwrap();
            store.create_customer("b", "B", "").unwrap();
            let vault = Vault::from_base64_key(
                &base64::engine::general_purpose::STANDARD.encode([2u8; 32]),
            )
            .unwrap();
            let cfg = Config {
                client_id: "synthetic-client".into(),
                client_secret: "synthetic-secret".into(),
                callback: "https://example.org/owner/social/oauth/callback".into(),
            };
            let pending = start(&store, &vault, "a", &cfg).unwrap();
            let token_url = format!("{base}/token");
            let profile_url = format!("{base}/userinfo");
            assert!(finish_at(
                &store,
                &vault,
                "b",
                &cfg,
                &pending.state,
                "synthetic-code",
                (&token_url, &profile_url)
            )
            .await
            .is_err());
            assert_eq!(profile_hits.load(Ordering::SeqCst), 0);
            let result = finish_at(
                &store,
                &vault,
                "a",
                &cfg,
                &pending.state,
                "synthetic-code",
                (&token_url, &profile_url),
            )
            .await;
            assert_eq!(
                result.is_ok(),
                accepted,
                "scope={scope:?} profile={profile_status} result={result:?}"
            );
            if let Ok(id) = result {
                assert!(store.account_has_scope("a", &id, "openid").unwrap());
                assert!(store.account_has_scope("a", &id, "profile").unwrap());
                assert!(!store
                    .account_has_scope("a", &id, "w_member_social")
                    .unwrap());
                assert!(store.account("b", &id).is_err());
                let (_, external_id, encrypted, _) = store.account("a", &id).unwrap();
                assert_ne!(encrypted, "synthetic-only");
                assert_eq!(
                    vault
                        .open(
                            &encrypted,
                            &crate::vault::account_label("a", "linkedin", &external_id)
                        )
                        .unwrap(),
                    "synthetic-only"
                );
                assert_eq!(profile_hits.load(Ordering::SeqCst), 1);
            } else {
                assert!(store.list_accounts("a").unwrap().is_empty());
            }
            assert!(store
                .oauth_consume("a", "linkedin", &pending.state)
                .is_err());
            server.abort();
        }
    }

    #[test]
    fn linkedin_token_response_without_scope_is_accepted_for_later_userinfo_verification() {
        // LinkedIn does not guarantee a scope field in every token response.
        let token: Token = serde_json::from_value(serde_json::json!({
            "access_token": "synthetic-only", "expires_in": 3600,
            "id_token": "synthetic-not-validated-here"
        }))
        .unwrap();
        assert!(token.scope.is_empty());
        assert_eq!(SCOPE, "openid profile");
        // Publishing must remain separately authorized.
        assert!(!SCOPE
            .split_whitespace()
            .any(|scope| scope == "w_member_social"));
    }
    #[test]
    fn linkedin_token_response_with_scope_can_be_checked_exactly() {
        let token: Token = serde_json::from_value(serde_json::json!({
            "access_token": "synthetic-only", "expires_in": 3600,
            "scope": "openid profile"
        }))
        .unwrap();
        assert!(SCOPE.split_whitespace().all(|requested| token
            .scope
            .split_whitespace()
            .any(|granted| requested == granted)));
        let token: Token = serde_json::from_value(serde_json::json!({
            "access_token": "synthetic-only", "expires_in": 3600,
            "scope": "openid"
        }))
        .unwrap();
        assert!(!SCOPE.split_whitespace().all(|requested| token
            .scope
            .split_whitespace()
            .any(|granted| requested == granted)));
    }
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
        // A login-only grant cannot be used to publish, including across tenants.
        assert!(!store
            .account_has_scope("a", &first, "w_member_social")
            .unwrap());
        assert!(store.account_has_scope("a", &first, "openid").unwrap());
        assert!(!store.account_has_scope("b", &first, "openid").unwrap());
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
