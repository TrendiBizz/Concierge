//! Official Meta Graph API publishing adapters. Disabled unless explicit operator flags
//! and approved customer posts allow invocation. A remote timeout is ambiguous and
//! never retried automatically by Concierge's scheduler.
use crate::connector::{Connector, ConnectorError, PublishRequest, Published};
use async_trait::async_trait;
use reqwest::Url;
use serde::Deserialize;

#[derive(Deserialize)]
struct GraphCreated {
    id: String,
}
pub struct Facebook {
    http: reqwest::Client,
    version: String,
}
pub struct Instagram {
    http: reqwest::Client,
    version: String,
    via_facebook: bool,
}
fn http() -> reqwest::Client {
    reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(20))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .expect("Meta HTTP client")
}
fn safe_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 256
        && value.bytes().all(|b| b.is_ascii_digit() || b == b'_')
}
fn safe_media(value: &str) -> bool {
    let Ok(url) = Url::parse(value) else {
        return false;
    };
    if url.scheme() != "https"
        || url.username() != ""
        || url.password().is_some()
        || url.port().is_some()
        || url.fragment().is_some()
    {
        return false;
    }
    let Some(host) = url.host_str() else {
        return false;
    };
    let host = host.trim_end_matches('.').to_ascii_lowercase();
    if host == "localhost"
        || host.ends_with(".localhost")
        || host.ends_with(".local")
        || host.ends_with(".internal")
        || host.ends_with(".test")
        || host.ends_with(".example")
        || host.parse::<std::net::IpAddr>().is_ok()
        || !host.contains('.')
    {
        return false;
    }
    value.len() <= 2048
}
fn classify(status: reqwest::StatusCode, kind: &str) -> ConnectorError {
    if matches!(status.as_u16(), 400 | 401 | 403) {
        // 400 can mean policy/media input failure, not always token expiry.
        if matches!(status.as_u16(), 401 | 403) {
            return ConnectorError::AuthExpired(format!("{kind} authorization rejected"));
        }
        return ConnectorError::Permanent(format!("{kind} rejected post content"));
    }
    if status.is_server_error() || status.as_u16() == 429 {
        return ConnectorError::Retryable(format!("{kind} response uncertain"));
    }
    ConnectorError::Permanent(format!("{kind} refused approved post"))
}
impl Facebook {
    pub fn new(version: &str) -> Result<Self, String> {
        if !version.starts_with('v')
            || !version[1..].chars().all(|c| c.is_ascii_digit() || c == '.')
        {
            return Err("Invalid Graph API version".into());
        }
        Ok(Self {
            http: http(),
            version: version.into(),
        })
    }
}
impl Default for Instagram {
    fn default() -> Self {
        Self::new()
    }
}
impl Instagram {
    pub fn new() -> Self {
        let version = std::env::var("SOCIAL_META_GRAPH_VERSION").unwrap_or_else(|_| "v27.0".into());
        let via_facebook =
            std::env::var("SOCIAL_INSTAGRAM_LOGIN_MODE").as_deref() != Ok("instagram");
        Self {
            http: http(),
            version,
            via_facebook,
        }
    }
    fn graph_endpoint(&self, id: &str, suffix: &str) -> String {
        if self.via_facebook {
            format!("https://graph.facebook.com/{}/{id}/{suffix}", self.version)
        } else {
            format!("https://graph.instagram.com/{id}/{suffix}")
        }
    }
    fn status_endpoint(&self, id: &str) -> String {
        if self.via_facebook {
            format!("https://graph.facebook.com/{}/{id}", self.version)
        } else {
            format!("https://graph.instagram.com/{id}")
        }
    }
}
#[async_trait]
impl Connector for Facebook {
    fn network(&self) -> &'static str {
        "facebook"
    }
    async fn publish(&self, request: PublishRequest) -> Result<Published, ConnectorError> {
        if !safe_id(&request.external_id) || request.access_token.is_empty() {
            return Err(ConnectorError::AuthExpired(
                "Invalid Page credentials".into(),
            ));
        }
        if !request.media.is_empty() {
            return Err(ConnectorError::Permanent(
                "Facebook media posting is not enabled; use text-only draft".into(),
            ));
        }
        if request.text.trim().is_empty() {
            return Err(ConnectorError::Permanent(
                "Facebook post text is empty".into(),
            ));
        }
        let url = format!(
            "https://graph.facebook.com/{}/{}/feed",
            self.version, request.external_id
        );
        let response = self
            .http
            .post(url)
            .bearer_auth(&request.access_token)
            .form(&[("message", request.text.as_str())])
            .send()
            .await
            .map_err(|_| ConnectorError::Retryable("Facebook post outcome uncertain".into()))?;
        if !response.status().is_success() {
            return Err(classify(response.status(), "Facebook"));
        }
        let result: GraphCreated = response
            .json()
            .await
            .map_err(|_| ConnectorError::Retryable("Facebook receipt missing".into()))?;
        if result.id.is_empty() {
            return Err(ConnectorError::Retryable(
                "Facebook post receipt missing".into(),
            ));
        }
        Ok(Published {
            external_id: result.id,
            url: None,
        })
    }
}
#[async_trait]
impl Connector for Instagram {
    fn network(&self) -> &'static str {
        "instagram"
    }
    async fn publish(&self, request: PublishRequest) -> Result<Published, ConnectorError> {
        if !safe_id(&request.external_id) || request.access_token.is_empty() {
            return Err(ConnectorError::AuthExpired(
                "Instagram credentials unavailable".into(),
            ));
        }
        if request.media.len() != 1 || !safe_media(&request.media[0]) {
            return Err(ConnectorError::Permanent(
                "Instagram requires one public HTTPS image URL for this posting mode".into(),
            ));
        }
        if request.text.chars().count() > 2200 {
            return Err(ConnectorError::Permanent(
                "Instagram caption exceeds limit".into(),
            ));
        }
        let endpoint = self.graph_endpoint(&request.external_id, "media");
        let response = self
            .http
            .post(endpoint)
            .bearer_auth(&request.access_token)
            .form(&[
                ("image_url", request.media[0].as_str()),
                ("caption", request.text.as_str()),
            ])
            .send()
            .await
            .map_err(|_| ConnectorError::Retryable("Instagram media creation uncertain".into()))?;
        if !response.status().is_success() {
            return Err(classify(response.status(), "Instagram"));
        }
        let container: GraphCreated = response.json().await.map_err(|_| {
            ConnectorError::Retryable("Instagram media container receipt missing".into())
        })?;
        if !safe_id(&container.id) {
            return Err(ConnectorError::Retryable(
                "Invalid Instagram media container".into(),
            ));
        }
        // Media processing may be asynchronous; query status before publishing.
        let status_endpoint = self.status_endpoint(&container.id);
        let mut ready = false;
        for _ in 0..6 {
            let result = self
                .http
                .get(&status_endpoint)
                .bearer_auth(&request.access_token)
                .query(&[("fields", "status_code")])
                .send()
                .await
                .map_err(|_| {
                    ConnectorError::Retryable("Instagram processing status uncertain".into())
                })?;
            if !result.status().is_success() {
                return Err(classify(result.status(), "Instagram"));
            }
            let parsed: serde_json::Value = result.json().await.map_err(|_| {
                ConnectorError::Retryable("Instagram processing receipt invalid".into())
            })?;
            match parsed.get("status_code").and_then(|v| v.as_str()) {
                Some("FINISHED") => {
                    ready = true;
                    break;
                }
                Some("ERROR") | Some("EXPIRED") => {
                    return Err(ConnectorError::Permanent(
                        "Instagram media processing failed".into(),
                    ))
                }
                Some("IN_PROGRESS") | Some("PUBLISHED") | None => {
                    tokio::time::sleep(std::time::Duration::from_secs(2)).await
                }
                _ => {
                    return Err(ConnectorError::Permanent(
                        "Instagram media processing status unsupported".into(),
                    ))
                }
            }
        }
        if !ready {
            return Err(ConnectorError::Retryable(
                "Instagram media processing not finished; reconcile before retry".into(),
            ));
        }
        let endpoint = self.graph_endpoint(&request.external_id, "media_publish");
        let response = self
            .http
            .post(endpoint)
            .bearer_auth(&request.access_token)
            .form(&[("creation_id", container.id.as_str())])
            .send()
            .await
            .map_err(|_| ConnectorError::Retryable("Instagram publish outcome uncertain".into()))?;
        if !response.status().is_success() {
            return Err(classify(response.status(), "Instagram"));
        }
        let result: GraphCreated = response
            .json()
            .await
            .map_err(|_| ConnectorError::Retryable("Instagram publish receipt missing".into()))?;
        if result.id.is_empty() {
            return Err(ConnectorError::Retryable(
                "Instagram publish receipt missing".into(),
            ));
        }
        Ok(Published {
            external_id: result.id,
            url: None,
        })
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn unsafe_media_is_blocked() {
        for value in [
            "http://example.com/a.png",
            "https://localhost/a.png",
            "https://127.0.0.1/a.png",
            "https://10.0.0.1/a.png",
            "https://example.local/a.png",
            "https://test.com:8443/a.png",
            "https://example.com@localhost/a.png",
            "https://example.com/a.png#frag",
        ] {
            assert!(!safe_media(value), "{value}");
        }
        assert!(safe_media("https://media.example-cdn.com/photo.png"));
    }
    #[test]
    fn instagram_graph_hosts_match_login_product() {
        let facebook = Instagram {
            http: http(),
            version: "v27.0".into(),
            via_facebook: true,
        };
        assert_eq!(
            facebook.graph_endpoint("123", "media"),
            "https://graph.facebook.com/v27.0/123/media"
        );
        assert_eq!(
            facebook.status_endpoint("456"),
            "https://graph.facebook.com/v27.0/456"
        );
        let standalone = Instagram {
            http: http(),
            version: "v27.0".into(),
            via_facebook: false,
        };
        assert_eq!(
            standalone.graph_endpoint("123", "media_publish"),
            "https://graph.instagram.com/123/media_publish"
        );
    }
    #[test]
    fn identifier_validation() {
        assert!(safe_id("123456789"));
        assert!(!safe_id("../abc"));
        assert!(!safe_id("abc:123"));
    }
}
