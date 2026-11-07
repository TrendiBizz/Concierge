//! Google Business Profile Standard local posts (official v4).
//! Only posts to a location explicitly discovered during tenant OAuth.
use crate::connector::{Connector, ConnectorError, PublishRequest, Published};
use async_trait::async_trait;
use serde::Deserialize;

pub struct GoogleBusiness {
    http: reqwest::Client,
}
#[derive(Deserialize)]
struct LocalPostReceipt {
    name: String,
}
impl Default for GoogleBusiness {
    fn default() -> Self {
        Self::new()
    }
}
impl GoogleBusiness {
    pub fn new() -> Self {
        Self {
            http: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(18))
                .redirect(reqwest::redirect::Policy::none())
                .build()
                .expect("HTTP client"),
        }
    }
}
pub fn valid_resource(value: &str) -> bool {
    let parts: Vec<_> = value.split('/').collect();
    parts.len() == 4
        && parts[0] == "accounts"
        && parts[2] == "locations"
        && [parts[1], parts[3]]
            .iter()
            .all(|v| !v.is_empty() && v.bytes().all(|c| c.is_ascii_digit()))
}
#[async_trait]
impl Connector for GoogleBusiness {
    fn network(&self) -> &'static str {
        "google_business"
    }
    async fn publish(&self, request: PublishRequest) -> Result<Published, ConnectorError> {
        if !valid_resource(&request.external_id) || request.access_token.is_empty() {
            return Err(ConnectorError::AuthExpired(
                "Google Business location authorization unavailable".into(),
            ));
        }
        if !request.media.is_empty() {
            return Err(ConnectorError::Permanent(
                "Google Business media posting not enabled".into(),
            ));
        }
        if request.text.trim().is_empty() || request.text.chars().count() > 1500 {
            return Err(ConnectorError::Permanent(
                "Google Business Standard post must be 1-1500 characters".into(),
            ));
        }
        let url = format!(
            "https://mybusiness.googleapis.com/v4/{}/localPosts",
            request.external_id
        );
        let resp = self
            .http
            .post(url)
            .bearer_auth(&request.access_token)
            .json(&serde_json::json!({
                "topicType":"STANDARD","summary":request.text
            }))
            .send()
            .await
            .map_err(|_| ConnectorError::Retryable("Google post response uncertain".into()))?;
        if !resp.status().is_success() {
            if matches!(resp.status().as_u16(), 401 | 403) {
                return Err(ConnectorError::AuthExpired(
                    "Google business grant or API access rejected".into(),
                ));
            }
            if resp.status().is_server_error() || resp.status().as_u16() == 429 {
                return Err(ConnectorError::Retryable(
                    "Google post response uncertain".into(),
                ));
            }
            return Err(ConnectorError::Permanent(
                "Google rejected Standard local post".into(),
            ));
        }
        let published: LocalPostReceipt = resp
            .json()
            .await
            .map_err(|_| ConnectorError::Retryable("Google post receipt not verified".into()))?;
        if published.name.is_empty() {
            return Err(ConnectorError::Retryable(
                "Google post receipt missing".into(),
            ));
        }
        Ok(Published {
            external_id: published.name,
            url: None,
        })
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_canonical_google_business_resources() {
        assert!(valid_resource("accounts/123/locations/456"));
        for bad in [
            "locations/123",
            "accounts/abc/locations/456",
            "accounts/123/locations/../../admin",
            "accounts/123/locations/456/localPosts",
            "accounts/123/locations/456?x=y",
        ] {
            assert!(!valid_resource(bad), "{bad}");
        }
    }
}
