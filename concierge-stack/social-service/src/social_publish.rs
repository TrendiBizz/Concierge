//! Text-only Mastodon and LinkedIn publishing through official APIs.
//! Disabled unless explicit per-network switches are set in main.rs.
//! The scheduler independently checks owner approval and tenant identity.
use crate::connector::{Connector, ConnectorError, PublishRequest, Published};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};

fn http_client() -> reqwest::Client {
    reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(12))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .expect("HTTP client initialization")
}

fn status_error(status: reqwest::StatusCode, network: &str) -> ConnectorError {
    if status == reqwest::StatusCode::UNAUTHORIZED || status == reqwest::StatusCode::FORBIDDEN {
        return ConnectorError::AuthExpired(format!("{network} authorization expired or revoked"));
    }
    if status == reqwest::StatusCode::TOO_MANY_REQUESTS || status.is_server_error() {
        return ConnectorError::Retryable(format!(
            "{network} remote result uncertain (HTTP {status})"
        ));
    }
    ConnectorError::Permanent(format!(
        "{network} rejected the approved post (HTTP {status})"
    ))
}

pub struct Mastodon {
    http: reqwest::Client,
    origin: String,
}
#[derive(Deserialize)]
struct MastodonResponse {
    id: String,
    url: Option<String>,
}
impl Mastodon {
    pub fn new(origin: &str) -> Result<Self, String> {
        let url = reqwest::Url::parse(origin).map_err(|_| "Invalid Mastodon origin")?;
        if url.scheme() != "https"
            || url.host_str().is_none()
            || url.username() != ""
            || url.password().is_some()
            || url.port().is_some()
            || url.path() != "/"
            || url.query().is_some()
            || url.fragment().is_some()
        {
            return Err("Mastodon requires a pinned HTTPS origin".into());
        }
        Ok(Self {
            http: http_client(),
            origin: origin.trim_end_matches('/').into(),
        })
    }
}
#[async_trait]
impl Connector for Mastodon {
    fn network(&self) -> &'static str {
        "mastodon"
    }

    async fn publish(&self, request: PublishRequest) -> Result<Published, ConnectorError> {
        if !request.external_id.ends_with(&format!("@{}", self.origin)) {
            return Err(ConnectorError::Permanent(
                "Mastodon account does not match pinned instance".into(),
            ));
        }
        if request.access_token.trim().is_empty() {
            return Err(ConnectorError::AuthExpired(
                "Mastodon account must reconnect".into(),
            ));
        }
        if request.text.trim().is_empty()
            || request.text.chars().count() > 500
            || (!request.media.is_empty() && request.local_media.is_none())
        {
            return Err(ConnectorError::Permanent(
                "Mastodon text-only post rejected by local limits".into(),
            ));
        }
        let response = self
            .http
            .post(format!("{}/api/v1/statuses", self.origin))
            .bearer_auth(&request.access_token)
            .header("Idempotency-Key", &request.idempotency_key)
            .form(&[("status", request.text.as_str()), ("visibility", "public")])
            .send()
            .await
            .map_err(|_| {
                ConnectorError::Retryable("Mastodon publishing outcome uncertain".into())
            })?;
        if !response.status().is_success() {
            return Err(status_error(response.status(), "Mastodon"));
        }
        let body: MastodonResponse = response.json().await.map_err(|_| {
            ConnectorError::Retryable("Mastodon response unreadable after publishing".into())
        })?;
        if body.id.trim().is_empty() {
            return Err(ConnectorError::Retryable(
                "Mastodon post ID missing after publishing".into(),
            ));
        }
        Ok(Published {
            external_id: body.id,
            url: body.url,
        })
    }
}

pub struct LinkedIn {
    http: reqwest::Client,
    version: String,
    organization: bool,
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct Distribution {
    feed_distribution: &'static str,
    target_entities: Vec<String>,
    third_party_distribution_channels: Vec<String>,
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct LinkedInPost<'a> {
    author: String,
    commentary: &'a str,
    visibility: &'static str,
    distribution: Distribution,
    lifecycle_state: &'static str,
    is_reshare_disabled_by_author: bool,
}
fn linkedin_body<'a>(external_id: &str, text: &'a str) -> LinkedInPost<'a> {
    LinkedInPost {
        author: format!("urn:li:person:{external_id}"),
        commentary: text,
        visibility: "PUBLIC",
        distribution: Distribution {
            feed_distribution: "MAIN_FEED",
            target_entities: vec![],
            third_party_distribution_channels: vec![],
        },
        lifecycle_state: "PUBLISHED",
        is_reshare_disabled_by_author: false,
    }
}
impl LinkedIn {
    pub fn organization(version: &str) -> Result<Self, String> {
        let mut connector = Self::new(version)?;
        connector.organization = true;
        Ok(connector)
    }
    pub fn new(version: &str) -> Result<Self, String> {
        if version.len() != 6 || !version.bytes().all(|b| b.is_ascii_digit()) {
            return Err("LinkedIn API version must be YYYYMM".into());
        }
        let month: u8 = version[4..6]
            .parse()
            .map_err(|_| "Invalid LinkedIn API month")?;
        if !(1..=12).contains(&month) {
            return Err("Invalid LinkedIn API month".into());
        }
        Ok(Self {
            http: http_client(),
            version: version.into(),
            organization: false,
        })
    }
}
#[async_trait]
impl Connector for LinkedIn {
    fn network(&self) -> &'static str {
        if self.organization {
            "linkedin_organization"
        } else {
            "linkedin"
        }
    }

    async fn publish(&self, request: PublishRequest) -> Result<Published, ConnectorError> {
        if request.external_id.is_empty()
            || request.external_id.len() > 256
            || !request
                .external_id
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
        {
            return Err(ConnectorError::Permanent(
                "LinkedIn account identity invalid".into(),
            ));
        }
        if request.access_token.trim().is_empty() {
            return Err(ConnectorError::AuthExpired(
                "LinkedIn account must reconnect".into(),
            ));
        }
        if request.text.trim().is_empty()
            || request.text.chars().count() > 3000
            || (!request.media.is_empty() && request.local_media.is_none())
        {
            return Err(ConnectorError::Permanent(
                "LinkedIn text-only post rejected by local limits".into(),
            ));
        }
        let mut body = serde_json::to_value(linkedin_body(&request.external_id, &request.text))
            .map_err(|_| ConnectorError::Permanent("LinkedIn post could not be prepared".into()))?;
        if self.organization {
            body["author"] =
                serde_json::json!(format!("urn:li:organization:{}", request.external_id));
        }
        if let Some(asset) = &request.local_media {
            body["content"] = crate::linkedin_media::upload(
                &self.http,
                &self.version,
                &request.access_token,
                body["author"].as_str().unwrap_or(""),
                asset,
            )
            .await?;
        }
        let response = self
            .http
            .post("https://api.linkedin.com/rest/posts")
            .bearer_auth(&request.access_token)
            .header("Linkedin-Version", &self.version)
            .header("X-Restli-Protocol-Version", "2.0.0")
            .json(&body)
            .send()
            .await
            .map_err(|_| {
                ConnectorError::Retryable("LinkedIn publishing outcome uncertain".into())
            })?;
        if response.status() != reqwest::StatusCode::CREATED {
            return Err(status_error(response.status(), "LinkedIn"));
        }
        let id = response
            .headers()
            .get("x-restli-id")
            .and_then(|value| value.to_str().ok())
            .unwrap_or("")
            .to_string();
        if id.is_empty() {
            return Err(ConnectorError::Retryable(
                "LinkedIn post receipt missing".into(),
            ));
        }
        Ok(Published {
            external_id: id,
            url: None,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn mastodon_pins_https_and_blocks_unknown_hosts() {
        assert!(Mastodon::new("https://mastodon.social").is_ok());
        assert!(Mastodon::new("http://mastodon.social").is_err());
        assert!(Mastodon::new("https://mastodon.social@attacker.test").is_err());
        assert!(Mastodon::new("https://mastodon.social/path").is_err());
        assert!(Mastodon::new("https://mastodon.social:8443").is_err());
    }
    #[test]
    fn linkedin_post_body_matches_official_contract() {
        let value = serde_json::to_value(linkedin_body("member123", "Approved text")).unwrap();
        assert_eq!(value["author"], "urn:li:person:member123");
        assert_eq!(value["commentary"], "Approved text");
        assert_eq!(value["lifecycleState"], "PUBLISHED");
        assert_eq!(value["distribution"]["feedDistribution"], "MAIN_FEED");
        assert_eq!(value["visibility"], "PUBLIC");
        assert_eq!(value["isReshareDisabledByAuthor"], false);
    }
    #[test]
    fn linkedin_version_validation() {
        assert!(LinkedIn::new("202603").is_ok());
        assert!(LinkedIn::new("202613").is_err());
        assert!(LinkedIn::new("v202603").is_err());
    }
}
