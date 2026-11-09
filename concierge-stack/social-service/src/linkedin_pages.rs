//! Discover only approved organization roles using the customer's own LinkedIn token.
use crate::{
    store::{Store, VerifiedAccount},
    vault::{account_label, Vault},
};
use serde::Deserialize;
#[derive(Deserialize)]
struct Acls {
    #[serde(default)]
    elements: Vec<Acl>,
    paging: Paging,
}
#[derive(Deserialize)]
struct Paging {
    start: u32,
    count: u32,
    total: Option<u32>,
}
#[derive(Deserialize)]
struct Acl {
    organization: String,
    role: String,
    state: String,
}
fn organization_id(acl: &Acl) -> Option<&str> {
    if acl.state != "APPROVED"
        || !matches!(acl.role.as_str(), "ADMINISTRATOR" | "CONTENT_ADMINISTRATOR")
    {
        return None;
    }
    acl.organization
        .strip_prefix("urn:li:organization:")
        .filter(|id| !id.is_empty() && id.bytes().all(|b| b.is_ascii_digit()))
}
pub async fn discover(
    store: &Store,
    vault: &Vault,
    customer: &str,
    token: &str,
    refresh: Option<&str>,
    expires: i64,
    scopes: &str,
) -> Result<Vec<String>, String> {
    let scopes = crate::linkedin::normalize_scopes(scopes);
    if !["w_organization_social", "r_organization_admin"]
        .iter()
        .all(|s| scopes.split_whitespace().any(|v| v == *s))
    {
        return Err("LinkedIn company Page permissions are not approved; reconnect after Community Management access is granted".into());
    }
    let version = std::env::var("SOCIAL_LINKEDIN_API_VERSION").unwrap_or_else(|_| "202605".into());
    if version.len() != 6 || !version.bytes().all(|b| b.is_ascii_digit()) {
        return Err("LinkedIn API version is not configured".into());
    }
    let http = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "LinkedIn Page discovery unavailable")?;
    let mut found = std::collections::BTreeSet::new();
    let mut start = 0;
    for page in 0..10 {
        let r = http
            .get("https://api.linkedin.com/rest/organizationAcls")
            .bearer_auth(token)
            .header("Linkedin-Version", &version)
            .header("X-Restli-Protocol-Version", "2.0.0")
            .query(&[
                ("q", "roleAssignee"),
                ("state", "APPROVED"),
                ("count", "100"),
                ("start", &start.to_string()),
            ])
            .send()
            .await
            .map_err(|_| "LinkedIn Page discovery unavailable")?;
        if !r.status().is_success() {
            return Err("LinkedIn company Page discovery denied; check Community Management approval and Page administrator role".into());
        }
        let a: Acls = r
            .json()
            .await
            .map_err(|_| "Invalid LinkedIn Page discovery response")?;
        for acl in &a.elements {
            if let Some(id) = organization_id(acl) {
                found.insert(id.to_string());
            }
        }
        let count = a.elements.len() as u32;
        if count == 0
            || a.paging.total.is_some_and(|n| n <= a.paging.start + count)
            || (a.paging.total.is_none() && count < a.paging.count)
        {
            break;
        }
        if page == 9 {
            return Err("LinkedIn Page list exceeds the supported limit".into());
        }
        start = a.paging.start + count;
    }
    let mut ids = Vec::new();
    for id in found {
        let r = http
            .get(format!("https://api.linkedin.com/rest/organizations/{id}"))
            .bearer_auth(token)
            .header("Linkedin-Version", &version)
            .header("X-Restli-Protocol-Version", "2.0.0")
            .send()
            .await
            .map_err(|_| "LinkedIn Page identity unavailable")?;
        if !r.status().is_success() {
            return Err("LinkedIn Page identity verification was denied".into());
        }
        let identity: serde_json::Value = r
            .json()
            .await
            .map_err(|_| "Invalid LinkedIn Page identity")?;
        let name = identity["localizedName"]
            .as_str()
            .filter(|s| !s.trim().is_empty())
            .ok_or("LinkedIn Page name unavailable")?;
        let label = account_label(customer, "linkedin_organization", &id);
        let encrypted = vault.seal(token, &label)?;
        let sealed_refresh = refresh.map(|r| vault.seal(r, &label)).transpose()?;
        ids.push(store.upsert_verified_account(VerifiedAccount {
            customer,
            network: "linkedin_organization",
            external_id: &id,
            display_name: name,
            token_enc: &encrypted,
            refresh_enc: sealed_refresh.as_deref(),
            expires_at: Some(expires),
            granted_scopes: &scopes,
        })?);
    }
    Ok(ids)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_customer_approved_content_roles_are_accepted() {
        for role in ["ADMINISTRATOR", "CONTENT_ADMINISTRATOR"] {
            assert_eq!(
                organization_id(&Acl {
                    organization: "urn:li:organization:123".into(),
                    role: role.into(),
                    state: "APPROVED".into()
                }),
                Some("123")
            );
        }
        assert_eq!(
            organization_id(&Acl {
                organization: "urn:li:organization:999".into(),
                role: "ANALYST".into(),
                state: "APPROVED".into()
            }),
            None
        );
        assert_eq!(
            organization_id(&Acl {
                organization: "urn:li:organization:123".into(),
                role: "ADMINISTRATOR".into(),
                state: "REQUESTED".into()
            }),
            None
        );
    }
}
