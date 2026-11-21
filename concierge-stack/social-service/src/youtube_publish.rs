//! Bounded resumable uploads of tenant-owned video, invoked by the approval scheduler.
use crate::connector::{Connector, ConnectorError, PublishRequest, Published};
use async_trait::async_trait;
use serde_json::{json, Value};
use std::io::{Read, Seek, SeekFrom};
const CHUNK: u64 = 8 * 256 * 1024;
const UPLOAD: &str = "https://www.googleapis.com/upload/youtube/v3/videos";
pub fn enabled() -> bool {
    std::env::var("SOCIAL_ENABLE_PUBLISH").as_deref() == Ok("true")
        && std::env::var("SOCIAL_ENABLE_YOUTUBE_PUBLISH").as_deref() == Ok("true")
}
pub fn metadata(options: &Value) -> Result<Value, String> {
    let title = options["title"]
        .as_str()
        .ok_or("YouTube title is required")?;
    if title.trim().is_empty() || title.chars().count() > 100 || title.contains(['<', '>']) {
        return Err("YouTube title must be at most 100 characters without angle brackets".into());
    }
    let description = match options.get("description") {
        None => "",
        Some(v) => v.as_str().ok_or("Invalid YouTube description")?,
    };
    if description.len() > 5000 {
        return Err("YouTube description exceeds 5000 bytes".into());
    }
    let privacy = match options.get("privacy") {
        None => "private",
        Some(v) => v.as_str().ok_or("Invalid YouTube privacy")?,
    };
    if !["private", "unlisted", "public"].contains(&privacy) {
        return Err("Invalid YouTube privacy".into());
    }
    Ok(
        json!({"snippet":{"title":title,"description":description,"categoryId":"22"},"status":{"privacyStatus":privacy,"selfDeclaredMadeForKids":false}}),
    )
}
pub fn validate(media: &[String], options: &Value) -> Result<(), String> {
    metadata(options)?;
    if media.len() != 1 {
        return Err("YouTube requires exactly one uploaded video".into());
    }
    let id = media[0]
        .strip_prefix("upload:")
        .ok_or("Upload a video for YouTube")?;
    if !crate::youtube::valid_id(id) {
        return Err("Upload a video for YouTube".into());
    }
    Ok(())
}
pub fn check_rules(options: &Value, rules: &crate::guardrails::Rules) -> Result<(), String> {
    let body = metadata(options)?;
    for value in [&body["snippet"]["title"], &body["snippet"]["description"]] {
        let content = value.as_str().unwrap_or("");
        if content.is_empty() {
            continue;
        }
        let check = crate::guardrails::check_post(
            &crate::guardrails::PostInput {
                content: content.into(),
                networks: vec!["youtube".into()],
                media_count: 1,
                ..Default::default()
            },
            rules,
        );
        if !check.ok {
            return Err("Current customer posting rules reject the YouTube metadata".into());
        }
    }
    Ok(())
}
pub struct YouTube {
    http: reqwest::Client,
    upload: String,
}
impl YouTube {
    pub fn new() -> Result<Self, String> {
        Self::with_upload_endpoint(UPLOAD)
    }
    /// Production uses the pinned Google endpoint; injection is for mock servers.
    pub fn with_upload_endpoint(upload: &str) -> Result<Self, String> {
        Ok(Self {
            http: crate::youtube::http()?,
            upload: upload.into(),
        })
    }
    fn trusted_session(&self, session: &str) -> bool {
        let Ok(u) = reqwest::Url::parse(session) else {
            return false;
        };
        let Ok(base) = reqwest::Url::parse(&self.upload) else {
            return false;
        };
        u.username().is_empty()
            && u.password().is_none()
            && u.fragment().is_none()
            && if self.upload == UPLOAD {
                u.scheme() == "https"
                    && u.host_str() == Some("www.googleapis.com")
                    && u.port_or_known_default() == Some(443)
            } else {
                u.origin() == base.origin()
            }
    }
}
async fn error(r: reqwest::Response) -> ConnectorError {
    let status = r.status();
    let b: Value = r.json().await.unwrap_or_default();
    let reason = b["error"]["errors"][0]["reason"].as_str().unwrap_or("");
    if status == reqwest::StatusCode::UNAUTHORIZED || b["error"] == "invalid_grant" {
        return ConnectorError::AuthExpired("Reconnect YouTube to renew upload access".into());
    }
    let msg = match reason {
        "quotaExceeded" => "YouTube upload quota reached; try after the quota resets",
        "uploadLimitExceeded" => "YouTube channel upload limit reached; try later",
        "forbidden" => "YouTube denied upload access; check channel permissions",
        _ => "YouTube rejected this upload; review channel permissions and video settings",
    };
    ConnectorError::Permanent(msg.into())
}
fn incomplete(r: &reqwest::Response, total: u64) -> Result<u64, ConnectorError> {
    let Some(range) = r.headers().get("Range") else {
        return Ok(0);
    };
    let next = range
        .to_str()
        .ok()
        .and_then(|v| v.strip_prefix("bytes=0-"))
        .and_then(|v| v.parse::<u64>().ok())
        .and_then(|v| v.checked_add(1));
    match next {
        Some(n) if n < total => Ok(n),
        _ => Err(ConnectorError::Retryable(
            "YouTube upload progress is invalid; reconcile before retrying".into(),
        )),
    }
}
async fn published(r: reqwest::Response) -> Result<Published, ConnectorError> {
    let body: Value = r.json().await.map_err(|_| {
        ConnectorError::Retryable(
            "YouTube upload receipt unreadable; reconcile before retrying".into(),
        )
    })?;
    let id = body["id"]
        .as_str()
        .filter(|v| crate::youtube::valid_id(v))
        .ok_or_else(|| {
            ConnectorError::Retryable(
                "YouTube upload receipt missing; reconcile before retrying".into(),
            )
        })?;
    Ok(Published {
        external_id: id.into(),
        url: Some(format!("https://www.youtube.com/watch?v={id}")),
    })
}
#[async_trait]
impl Connector for YouTube {
    fn network(&self) -> &'static str {
        "youtube"
    }
    async fn publish(&self, request: PublishRequest) -> Result<Published, ConnectorError> {
        if !enabled() {
            return Err(ConnectorError::Permanent(
                "YouTube publishing is not enabled".into(),
            ));
        }
        let body = metadata(&request.options).map_err(ConnectorError::Permanent)?;
        let asset = request
            .local_media
            .ok_or_else(|| ConnectorError::Permanent("Upload a video for YouTube".into()))?;
        if request.media.len() != 1
            || asset.kind != "video"
            || !["video/mp4", "video/quicktime"].contains(&asset.mime.as_str())
            || asset.bytes == 0
        {
            return Err(ConnectorError::Permanent(
                "YouTube requires exactly one uploaded video".into(),
            ));
        }
        let mut file = std::fs::File::open(&asset.path)
            .map_err(|_| ConnectorError::Permanent("Video cannot be opened".into()))?;
        if file
            .metadata()
            .map_err(|_| ConnectorError::Permanent("Video cannot be opened".into()))?
            .len()
            != asset.bytes
        {
            return Err(ConnectorError::Permanent(
                "The uploaded video changed; prepare the post again".into(),
            ));
        }
        // Never retry initialization: an ambiguous response could create another video.
        let r = self
            .http
            .post(&self.upload)
            .query(&[("uploadType", "resumable"), ("part", "snippet,status")])
            .bearer_auth(&request.access_token)
            .header("X-Upload-Content-Type", &asset.mime)
            .header("X-Upload-Content-Length", asset.bytes)
            .json(&body)
            .send()
            .await
            .map_err(|_| {
                ConnectorError::Retryable(
                    "YouTube upload initialization uncertain; reconcile before retrying".into(),
                )
            })?;
        if !r.status().is_success() {
            return Err(error(r).await);
        }
        let session = r
            .headers()
            .get("Location")
            .and_then(|v| v.to_str().ok())
            .filter(|v| self.trusted_session(v))
            .ok_or_else(|| {
                ConnectorError::Retryable(
                    "YouTube upload location invalid; reconcile before retrying".into(),
                )
            })?
            .to_string();
        let mut offset = 0;
        let mut failures = 0u32;
        let mut query = false;
        let mut stalls = 0;
        loop {
            let builder = self.http.put(&session).bearer_auth(&request.access_token);
            let r = if query {
                builder
                    .header("Content-Length", 0)
                    .header("Content-Range", format!("bytes */{}", asset.bytes))
                    .body(Vec::new())
                    .send()
                    .await
            } else {
                let size = (asset.bytes - offset).min(CHUNK) as usize;
                let mut bytes = vec![0; size];
                file.seek(SeekFrom::Start(offset))
                    .and_then(|_| file.read_exact(&mut bytes))
                    .map_err(|_| ConnectorError::Permanent("Video cannot be opened".into()))?;
                builder
                    .header("Content-Type", &asset.mime)
                    .header("Content-Length", size)
                    .header(
                        "Content-Range",
                        format!(
                            "bytes {}-{}/{}",
                            offset,
                            offset + size as u64 - 1,
                            asset.bytes
                        ),
                    )
                    .body(bytes)
                    .send()
                    .await
            };
            match r {
                Ok(r) if r.status().is_success() => return published(r).await,
                Ok(r) if r.status().as_u16() == 308 => {
                    let next = incomplete(&r, asset.bytes)?;
                    if next < offset {
                        return Err(ConnectorError::Retryable(
                            "YouTube upload progress changed; reconcile before retrying".into(),
                        ));
                    }
                    if next == offset {
                        stalls += 1;
                    } else {
                        stalls = 0;
                    }
                    if stalls > 5 {
                        return Err(ConnectorError::Retryable(
                            "YouTube upload stalled; reconcile before retrying".into(),
                        ));
                    }
                    offset = next;
                    query = false;
                }
                Ok(r) if !r.status().is_server_error() => return Err(error(r).await),
                _ => {
                    if failures >= 5 {
                        return Err(ConnectorError::Retryable(
                            "YouTube upload interrupted; reconcile before retrying".into(),
                        ));
                    }
                    tokio::time::sleep(std::time::Duration::from_millis(250 * (1 << failures)))
                        .await;
                    failures += 1;
                    query = true;
                }
            }
        }
    }
}
