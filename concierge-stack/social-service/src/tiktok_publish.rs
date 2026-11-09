//! TikTok Direct Post video support. A provider receipt is NOT a completed post.
//! Only HTTPS media from an operator-verified owned origin is sent via PULL_FROM_URL.
use crate::connector::{Connector, ConnectorError, PublishRequest, Published};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Creator {
    pub creator_username: String,
    pub creator_nickname: String,
    pub privacy_level_options: Vec<String>,
    pub comment_disabled: bool,
    pub duet_disabled: bool,
    pub stitch_disabled: bool,
    pub max_video_post_duration_sec: u32,
}
fn http() -> reqwest::Client {
    reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(20))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .expect("TikTok client")
}
pub async fn creator_info(token: &str) -> Result<Creator, String> {
    let r = http()
        .post("https://open.tiktokapis.com/v2/post/publish/creator_info/query/")
        .bearer_auth(token)
        .json(&json!({}))
        .send()
        .await
        .map_err(|_| "TikTok creator information is unavailable")?;
    if !r.status().is_success() {
        return Err("Reconnect TikTok with approved video publishing permissions".into());
    }
    let body: Value = r
        .json()
        .await
        .map_err(|_| "TikTok creator information is invalid")?;
    if body["error"]["code"] != "ok" {
        return Err("TikTok has not granted video publishing access".into());
    }
    serde_json::from_value(body["data"].clone())
        .map_err(|_| "TikTok creator information is incomplete".into())
}
fn payload(
    request: &PublishRequest,
    creator: &Creator,
    _origins: &[String],
) -> Result<Value, String> {
    if request.media.len() != 1 {
        return Err("TikTok requires exactly one video".into());
    }
    if request.local_media.is_none() {
        return Err("Upload the TikTok video so its duration can be verified by the server".into());
    }
    let privacy = request.options["privacy_level"]
        .as_str()
        .ok_or("Choose who can view the TikTok video")?;
    if !creator.privacy_level_options.iter().any(|v| v == privacy) {
        return Err("TikTok privacy choices changed; review this post again".into());
    }
    let duration = request.options["duration_seconds"]
        .as_f64()
        .ok_or("Video duration is required")?;
    if !duration.is_finite()
        || duration <= 0.0
        || duration > creator.max_video_post_duration_sec as f64
    {
        return Err("Video duration exceeds this TikTok account's current limit".into());
    }
    if request.options["music_usage_consent"] != true {
        return Err("Confirm TikTok Music Usage before publishing".into());
    }
    if request.options["brand_content_toggle"] == true && privacy == "SELF_ONLY" {
        return Err("Branded content cannot use private visibility".into());
    }
    if request.options["brand_content_toggle"] == true
        && request.options["branded_content_consent"] != true
    {
        return Err("Agree to TikTok Branded Content Policy before publishing".into());
    }
    if request.options["creator_consent"] != true {
        return Err("Explicit creator consent is required for this video".into());
    }
    if request.text.encode_utf16().count() > 2200 {
        return Err("TikTok caption exceeds 2200 UTF-16 characters".into());
    }
    let source = if let Some(asset) = &request.local_media {
        if asset.kind != "video" || (asset.duration_seconds - duration).abs() > 0.5 {
            return Err("The uploaded video changed; prepare the post again".into());
        }
        json!({"source":"FILE_UPLOAD","video_size":asset.bytes,"chunk_size":asset.bytes,"total_chunk_count":1})
    } else {
        json!({"source":"PULL_FROM_URL","video_url":request.media[0]})
    };
    Ok(
        json!({"post_info":{"title":request.text,"privacy_level":privacy,
 "disable_comment":creator.comment_disabled || request.options["allow_comments"]!=true,
 "disable_duet":creator.duet_disabled || request.options["allow_duet"]!=true,
 "disable_stitch":creator.stitch_disabled || request.options["allow_stitch"]!=true,
 "brand_content_toggle":request.options["brand_content_toggle"]==true,
 "brand_organic_toggle":request.options["brand_organic_toggle"]==true},
 "source_info":source}),
    )
}
pub struct TikTok {
    origins: Vec<String>,
}
impl TikTok {
    pub fn new(origins: &str) -> Result<Self, String> {
        let origins: Vec<_> = origins
            .split(',')
            .map(str::trim)
            .filter(|v| !v.is_empty())
            .map(str::to_string)
            .collect();
        if origins.iter().any(|v| {
            reqwest::Url::parse(v).map_or(true, |u| {
                u.scheme() != "https"
                    || u.host_str().is_none()
                    || !u.username().is_empty()
                    || u.password().is_some()
                    || u.origin().ascii_serialization() != *v
            })
        }) {
            return Err("TikTok requires explicit verified HTTPS media origins".into());
        }
        Ok(Self { origins })
    }
}
#[async_trait]
impl Connector for TikTok {
    fn network(&self) -> &'static str {
        "tiktok"
    }
    async fn publish(&self, request: PublishRequest) -> Result<Published, ConnectorError> {
        let creator = creator_info(&request.access_token)
            .await
            .map_err(ConnectorError::AuthExpired)?;
        let body = payload(&request, &creator, &self.origins).map_err(ConnectorError::Permanent)?;
        // Persist the initialized publish ID before querying it. Never initialize a second
        // video after an ambiguous provider response; scheduler reconciliation prevents duplicates.
        let r = http()
            .post("https://open.tiktokapis.com/v2/post/publish/video/init/")
            .bearer_auth(&request.access_token)
            .json(&body)
            .send()
            .await
            .map_err(|_| {
                ConnectorError::Retryable(
                    "TikTok video submission outcome uncertain; reconcile before retrying".into(),
                )
            })?;
        if !r.status().is_success() {
            return Err(ConnectorError::Permanent(
                "TikTok rejected video submission; check app approval and account permissions"
                    .into(),
            ));
        }
        let b: Value = r.json().await.map_err(|_| {
            ConnectorError::Retryable(
                "TikTok video receipt unreadable; reconcile before retrying".into(),
            )
        })?;
        if b["error"]["code"] != "ok" {
            return Err(ConnectorError::Permanent("TikTok did not accept the video; check app audit, permissions and media verification".into()));
        }
        let id = b["data"]["publish_id"]
            .as_str()
            .filter(|id| !id.is_empty())
            .ok_or_else(|| {
                ConnectorError::Retryable(
                    "TikTok video receipt missing; reconcile before retrying".into(),
                )
            })?;
        if let Some(asset) = &request.local_media {
            let upload = b["data"]["upload_url"].as_str().ok_or_else(|| {
                ConnectorError::Retryable(
                    "TikTok upload URL missing; reconcile this submission".into(),
                )
            })?;
            let url = reqwest::Url::parse(upload)
                .map_err(|_| ConnectorError::Permanent("TikTok upload URL invalid".into()))?;
            let host = url.host_str().unwrap_or("");
            if url.scheme() != "https"
                || !url.username().is_empty()
                || url.password().is_some()
                || !(host.ends_with(".tiktokapis.com") || host.ends_with(".tiktok.com"))
            {
                return Err(ConnectorError::Permanent(
                    "TikTok upload host was not trusted".into(),
                ));
            }
            let path = asset.path.clone();
            let bytes = tokio::task::spawn_blocking(move || std::fs::read(path))
                .await
                .map_err(|_| ConnectorError::Permanent("Video cannot be opened".into()))?
                .map_err(|_| ConnectorError::Permanent("Video cannot be opened".into()))?;
            let r=http().put(upload).header("Content-Type","video/mp4").header("Content-Range",format!("bytes 0-{}/{}",asset.bytes-1,asset.bytes)).body(bytes).send().await.map_err(|_|ConnectorError::Retryable(format!("TikTok upload outcome uncertain; publish receipt {id} requires reconciliation")))?;
            if !r.status().is_success() {
                return Err(ConnectorError::Retryable(format!(
                    "TikTok upload was not confirmed; reconcile publish receipt {id}"
                )));
            }
        }
        // A pending receipt must not be labelled published. The scheduler persists this
        // receipt and marks processing; subsequent status checks use this ID only.
        Ok(Published {
            external_id: format!("pending:tiktok:{id}"),
            url: None,
        })
    }
}
pub async fn post_status(token: &str, publish_id: &str) -> Result<Value, String> {
    let r = http()
        .post("https://open.tiktokapis.com/v2/post/publish/status/fetch/")
        .bearer_auth(token)
        .json(&json!({"publish_id":publish_id}))
        .send()
        .await
        .map_err(|_| "TikTok status unavailable")?;
    if !r.status().is_success() {
        return Err("TikTok status unavailable".into());
    }
    let b: Value = r.json().await.map_err(|_| "TikTok status invalid")?;
    if b["error"]["code"] != "ok" {
        return Err("TikTok status unavailable".into());
    }
    Ok(b["data"].clone())
}
#[cfg(test)]
mod tests {
    use super::*;
    fn creator() -> Creator {
        Creator {
            creator_username: "test".into(),
            creator_nickname: "Test".into(),
            privacy_level_options: vec!["SELF_ONLY".into()],
            comment_disabled: true,
            duet_disabled: false,
            stitch_disabled: false,
            max_video_post_duration_sec: 60,
        }
    }
    fn request() -> PublishRequest {
        PublishRequest {
            local_media: Some(crate::media::Asset {
                id: "test".into(),
                kind: "video".into(),
                mime: "video/mp4".into(),
                bytes: 100,
                width: 1080,
                height: 1920,
                duration_seconds: 20.0,
                path: "/unused-test-video".into(),
            }),
            options: json!({"privacy_level":"SELF_ONLY","creator_consent":true,"music_usage_consent":true,"duration_seconds":20,"allow_comments":true}),
            external_id: "id".into(),
            idempotency_key: "key".into(),
            access_token: "not-a-real-token".into(),
            refresh_token: None,
            text: "Reviewed caption".into(),
            link: String::new(),
            media: vec!["https://media.example.com/post.mp4".into()],
        }
    }
    #[test]
    fn owned_video_and_explicit_creator_choices_are_required() {
        let mut r = request();
        let p = payload(&r, &creator(), &["https://media.example.com".into()]).unwrap();
        assert_eq!(p["source_info"]["source"], "FILE_UPLOAD");
        assert_eq!(p["post_info"]["disable_comment"], true);
        r.local_media = None;
        assert!(payload(&r, &creator(), &["https://media.example.com".into()]).is_err());
    }
    #[test]
    fn changing_privacy_or_duration_requires_new_review() {
        let mut r = request();
        r.options["privacy_level"] = json!("PUBLIC_TO_EVERYONE");
        assert!(payload(&r, &creator(), &["https://media.example.com".into()]).is_err());
        r.options["privacy_level"] = json!("SELF_ONLY");
        r.options["duration_seconds"] = json!(61);
        assert!(payload(&r, &creator(), &["https://media.example.com".into()]).is_err());
    }
    #[test]
    fn absent_consent_never_posts() {
        let mut r = request();
        r.options["creator_consent"] = json!(false);
        assert!(payload(&r, &creator(), &["https://media.example.com".into()]).is_err());
        assert!(TikTok::new("http://127.0.0.1").is_err());
    }
}
