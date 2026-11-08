//! Explicit tenant-authorized OAuth renewal; never publishes content.
//! Instagram long-lived tokens: ig_refresh_token. LinkedIn: MDP partner refresh grant.
//! Other networks require relinking or provider-specific lifecycle implementation.
use crate::{
    store::Store,
    vault::{account_label, Vault},
};
use serde::Deserialize;

#[derive(Deserialize)]
struct Token {
    access_token: String,
    expires_in: i64,
    #[serde(default)]
    refresh_token: Option<String>,
    #[serde(default)]
    scope: Option<String>,
}
pub async fn refresh(
    store: &Store,
    vault: &Vault,
    customer: &str,
    account_id: &str,
) -> Result<i64, String> {
    let (network, external_id, encrypted, encrypted_refresh, expiry) =
        store.refresh_candidate(customer, account_id)?;
    if network == "instagram"
        && std::env::var("SOCIAL_INSTAGRAM_LOGIN_MODE").as_deref() != Ok("instagram")
    {
        return Err(
            "Facebook-linked Instagram access uses Page permissions; reconnect if revoked".into(),
        );
    }
    if expiry.is_some_and(|t| t > crate::now_unix() + 7 * 86400) {
        return Err("Account token does not need renewal yet".into());
    }
    let label = account_label(customer, &network, &external_id);
    let access = vault.open(&encrypted, &label)?;
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(12))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "OAuth refresh client unavailable")?;
    let response = match network.as_str() {
        "instagram" => client
            .get("https://graph.instagram.com/refresh_access_token")
            .query(&[
                ("grant_type", "ig_refresh_token"),
                ("access_token", access.as_str()),
            ])
            .send()
            .await
            .map_err(|_| "Instagram renewal unavailable")?,
        "google_business" => {
            let sealed =
                encrypted_refresh.ok_or("Google Business account needs reauthorization")?;
            let old_refresh = vault.open(&sealed, &label)?;
            let cfg = crate::google_business::from_env()
                .map_err(|_| "Google Business OAuth not configured")?;
            client
                .post("https://oauth2.googleapis.com/token")
                .form(&[
                    ("grant_type", "refresh_token"),
                    ("refresh_token", old_refresh.as_str()),
                    ("client_id", cfg.client_id.as_str()),
                    ("client_secret", cfg.secret.as_str()),
                ])
                .send()
                .await
                .map_err(|_| "Google Business renewal unavailable")?
        }
        "x" => {
            let sealed = encrypted_refresh.ok_or("Reconnect X for offline access")?;
            let old_refresh = vault.open(&sealed, &label)?;
            let cfg = crate::x::from_env()?;
            client
                .post("https://api.x.com/2/oauth2/token")
                .basic_auth(&cfg.client_id, Some(&cfg.secret))
                .form(&[
                    ("grant_type", "refresh_token"),
                    ("refresh_token", old_refresh.as_str()),
                ])
                .send()
                .await
                .map_err(|_| "X renewal unavailable")?
        }
        "tiktok" => {
            let sealed = encrypted_refresh.ok_or("TikTok refresh credential unavailable")?;
            let old_refresh = vault.open(&sealed, &label)?;
            let cfg = crate::tiktok::from_env().map_err(|_| "TikTok OAuth is not configured")?;
            client
                .post("https://open.tiktokapis.com/v2/oauth/token/")
                .form(&[
                    ("grant_type", "refresh_token"),
                    ("refresh_token", old_refresh.as_str()),
                    ("client_key", cfg.client_key.as_str()),
                    ("client_secret", cfg.client_secret.as_str()),
                ])
                .send()
                .await
                .map_err(|_| "TikTok renewal unavailable")?
        }
        "linkedin" | "linkedin_organization" => {
            let sealed = encrypted_refresh
                .ok_or("LinkedIn account requires reconnection (refresh permission unavailable)")?;
            let old_refresh = vault.open(&sealed, &label)?;
            let cfg = if network == "linkedin_organization" {
                crate::linkedin::organizations_from_env()
            } else {
                crate::linkedin::from_env()
            }
            .map_err(|_| "LinkedIn OAuth is not configured")?;
            client
                .post("https://www.linkedin.com/oauth/v2/accessToken")
                .form(&[
                    ("grant_type", "refresh_token"),
                    ("refresh_token", old_refresh.as_str()),
                    ("client_id", cfg.client_id.as_str()),
                    ("client_secret", cfg.client_secret.as_str()),
                ])
                .send()
                .await
                .map_err(|_| "LinkedIn renewal unavailable")?
        }
        _ => return Err("Account must be reconnected to renew this network".into()),
    };
    if !response.status().is_success() {
        return Err("Provider rejected token renewal; reconnect account".into());
    }
    let token: Token = response
        .json()
        .await
        .map_err(|_| "Invalid provider renewal response")?;
    if token.access_token.is_empty() || !(1..=5_184_000).contains(&token.expires_in) {
        return Err("Invalid renewed token expiry".into());
    }
    if network == "google_business"
        && token.scope.as_deref().is_some_and(|scope| {
            !scope
                .split_whitespace()
                .any(|v| v == "https://www.googleapis.com/auth/business.manage")
        })
    {
        return Err("Google Business permission was not renewed".into());
    }
    // Account linking requires OIDC scopes only; publishing is a separate grant.
    if network == "linkedin"
        && token.scope.as_deref().is_some_and(|scope| {
            let normalized = crate::linkedin::normalize_scopes(scope);
            !["openid", "profile"].iter().all(|needed| {
                normalized
                    .split_whitespace()
                    .any(|granted| granted == *needed)
            })
        })
    {
        return Err("Renewal reduced LinkedIn permissions".into());
    }
    if network == "tiktok"
        && (token
            .refresh_token
            .as_ref()
            .is_none_or(|refresh| refresh.is_empty())
            || token
                .scope
                .as_deref()
                .is_some_and(|scopes| !scopes.split(',').any(|s| s == "user.info.basic")))
    {
        return Err("TikTok refresh token or basic grant missing".into());
    }
    if network == "x"
        && (token.refresh_token.as_deref().is_none_or(str::is_empty)
            || token
                .scope
                .as_deref()
                .is_none_or(|scope| !crate::x::has_scopes(scope)))
    {
        return Err("X renewal did not retain account and publishing permission".into());
    }
    let next = vault.seal(&token.access_token, &label)?;
    let rotated = token
        .refresh_token
        .as_deref()
        .map(|v| vault.seal(v, &label))
        .transpose()?;
    let new_expiry = crate::now_unix() + token.expires_in;
    store.update_refreshed_token(
        customer,
        account_id,
        &encrypted,
        &next,
        rotated.as_deref(),
        new_expiry,
    )?;
    Ok(new_expiry)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn refreshed_credentials_never_cross_tenants_or_revocation() {
        let store = Store::open_memory().unwrap();
        store.create_customer("a", "A", "").unwrap();
        store.create_customer("b", "B", "").unwrap();
        let id = store
            .upsert_verified_account(crate::store::VerifiedAccount {
                customer: "a",
                network: "instagram",
                external_id: "ig123",
                display_name: "A",
                token_enc: "old",
                refresh_enc: None,
                expires_at: Some(crate::now_unix() + 5),
                granted_scopes: "instagram_business_basic",
            })
            .unwrap();
        assert!(store.refresh_candidate("b", &id).is_err());
        assert!(store
            .update_refreshed_token("b", &id, "old", "next", None, crate::now_unix() + 1000)
            .is_err());
        store
            .update_refreshed_token("a", &id, "old", "new", None, crate::now_unix() + 1000)
            .unwrap();
        assert!(store
            .update_refreshed_token("a", &id, "old", "again", None, crate::now_unix() + 1000)
            .is_err());
        store.disconnect_account("a", &id).unwrap();
        assert!(store.refresh_candidate("a", &id).is_err());
        assert!(store
            .update_refreshed_token(
                "a",
                &id,
                "new",
                "after-revoke",
                None,
                crate::now_unix() + 1000
            )
            .is_err());
    }
}
