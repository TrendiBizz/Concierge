//! Independently implemented AT Protocol password-session connector.
//! Reference: https://atproto.com/guides/sdk-auth and
//! https://atproto.com/guides/writing-data
//!
//! App passwords are suitable only for an internal pilot. Customer-facing
//! connection requires official OAuth, which is NOT implemented here.
//! Service host is fixed to avoid arbitrary-URL SSRF.
use crate::connector::{Connector, ConnectorError, PublishRequest, Published};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use time::OffsetDateTime;

const HOST: &str = "https://bsky.social/xrpc";
const LOGIN: &str = "com.atproto.server.createSession";
const CREATE: &str = "com.atproto.repo.createRecord";

pub struct Bluesky {
    http: reqwest::Client,
}

#[derive(Serialize)]
struct Credentials<'a> {
    identifier: &'a str,
    password: &'a str,
}
#[derive(Deserialize)]
struct Session {
    #[serde(rename = "accessJwt")]
    access_jwt: String,
    did: String,
}
#[derive(Serialize)]
struct Record<'a> {
    #[serde(rename = "$type")]
    record_type: &'static str,
    text: &'a str,
    #[serde(rename = "createdAt")]
    created_at: String,
}
#[derive(Serialize)]
struct Create<'a> {
    repo: &'a str,
    collection: &'static str,
    record: Record<'a>,
}
#[derive(Deserialize)]
struct Created {
    uri: String,
}
impl Default for Bluesky {
    fn default() -> Self {
        Self::new()
    }
}
impl Bluesky {
    pub fn new() -> Self {
        Self {
            http: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(12))
                .redirect(reqwest::redirect::Policy::none())
                .build()
                .expect("HTTP client initialization"),
        }
    }
}
#[async_trait]
impl Connector for Bluesky {
    fn network(&self) -> &'static str {
        "bluesky"
    }

    async fn publish(&self, request: PublishRequest) -> Result<Published, ConnectorError> {
        if !request.media.is_empty() {
            return Err(ConnectorError::Permanent(
                "Bluesky media uploads not implemented".into(),
            ));
        }
        if request.text.chars().count() > 300 {
            return Err(ConnectorError::Permanent(
                "Bluesky post exceeds character limit".into(),
            ));
        }
        if request.external_id.trim().is_empty() || request.access_token.trim().is_empty() {
            return Err(ConnectorError::AuthExpired(
                "Missing Bluesky handle or app password".into(),
            ));
        }

        let resp = self
            .http
            .post(format!("{HOST}/{LOGIN}"))
            .json(&Credentials {
                identifier: &request.external_id,
                password: &request.access_token,
            })
            .send()
            .await
            .map_err(|_| ConnectorError::Retryable("Bluesky sign-in unavailable".into()))?;
        if matches!(resp.status().as_u16(), 400 | 401 | 403) {
            return Err(ConnectorError::AuthExpired(
                "Bluesky account needs reconnection".into(),
            ));
        }
        if !resp.status().is_success() {
            return Err(ConnectorError::Retryable(format!(
                "Bluesky sign-in returned HTTP {}",
                resp.status()
            )));
        }
        let session: Session = resp
            .json()
            .await
            .map_err(|_| ConnectorError::Retryable("Bluesky returned an invalid session".into()))?;

        let record = Create {
            repo: &session.did,
            collection: "app.bsky.feed.post",
            record: Record {
                record_type: "app.bsky.feed.post",
                text: &request.text,
                created_at: OffsetDateTime::now_utc()
                    .format(&time::format_description::well_known::Rfc3339)
                    .map_err(|_| ConnectorError::Permanent("Clock format failed".into()))?,
            },
        };
        let resp = self
            .http
            .post(format!("{HOST}/{CREATE}"))
            .bearer_auth(&session.access_jwt)
            .json(&record)
            .send()
            .await
            .map_err(|_| {
                ConnectorError::Retryable("Bluesky publishing outcome uncertain".into())
            })?;
        if matches!(resp.status().as_u16(), 401 | 403) {
            return Err(ConnectorError::AuthExpired(
                "Bluesky session no longer authorised".into(),
            ));
        }
        if resp.status() == reqwest::StatusCode::TOO_MANY_REQUESTS
            || resp.status().is_server_error()
        {
            return Err(ConnectorError::Retryable(format!(
                "Bluesky publishing status {}",
                resp.status()
            )));
        }
        if !resp.status().is_success() {
            return Err(ConnectorError::Permanent(format!(
                "Bluesky rejected post with status {}",
                resp.status()
            )));
        }
        let created: Created = resp.json().await.map_err(|_| {
            ConnectorError::Retryable("Bluesky may have created post, response unreadable".into())
        })?;
        Ok(Published {
            external_id: created.uri.clone(),
            url: Some(created.uri),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn create_record_matches_atproto_lexicon() {
        let record = Create {
            repo: "did:plc:test",
            collection: "app.bsky.feed.post",
            record: Record {
                record_type: "app.bsky.feed.post",
                text: "Hello",
                created_at: "2026-11-07T00:00:00Z".into(),
            },
        };
        let json = serde_json::to_value(record).unwrap();
        assert_eq!(json["record"]["$type"], "app.bsky.feed.post");
        assert_eq!(json["record"]["text"], "Hello");
        assert_eq!(json["record"]["createdAt"], "2026-11-07T00:00:00Z");
    }
}
