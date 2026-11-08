//! Official X v2 publishing; ambiguous outcomes require reconciliation, never replay.
use crate::connector::{Connector, ConnectorError as E, PublishRequest, Published};
use async_trait::async_trait;
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
pub struct X {
    http: reqwest::Client,
    base: String,
}
impl X {
    pub fn new() -> Result<Self, String> {
        Ok(Self {
            http: crate::x::http()?,
            base: "https://api.x.com".into(),
        })
    }
}
fn status(s: reqwest::StatusCode) -> E {
    match s.as_u16() {
        401 | 403 => E::AuthExpired("Reconnect X with publishing permission".into()),
        402 => E::Permanent("X API credits are required".into()),
        429 => E::Permanent("X rate limit reached; review before rescheduling".into()),
        500..=599 => E::Retryable("X outcome uncertain; reconcile before retrying".into()),
        _ => E::Permanent(format!("X rejected the request (HTTP {s})")),
    }
}
fn id(v: &Value) -> Result<String, E> {
    v.as_str()
        .filter(|s| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit()))
        .map(String::from)
        .ok_or_else(|| {
            E::Retryable("X returned no usable identifier; reconcile before retrying".into())
        })
}
impl X {
    async fn checked(&self, r: reqwest::RequestBuilder) -> Result<Value, E> {
        let r = r
            .send()
            .await
            .map_err(|_| E::Retryable("X outcome uncertain; reconcile before retrying".into()))?;
        if !r.status().is_success() {
            return Err(status(r.status()));
        }
        r.json()
            .await
            .map_err(|_| E::Retryable("X response unreadable; reconcile before retrying".into()))
    }
    async fn media(&self, a: &crate::media::Asset, token: &str) -> Result<String, E> {
        if !["image", "video"].contains(&a.kind.as_str())
            || a.bytes > 64 * 1024 * 1024
            || (a.kind == "image" && a.bytes > 5 * 1024 * 1024)
            || a.kind == "video" && (a.duration_seconds > 140.0 || a.duration_seconds <= 0.0)
        {
            return Err(E::Permanent(
                "X supports an uploaded image or video up to 140 seconds and 64 MB".into(),
            ));
        }
        let b =
            std::fs::read(&a.path).map_err(|_| E::Permanent("X media is unavailable".into()))?;
        if b.len() as u64 != a.bytes {
            return Err(E::Permanent(
                "X media changed; upload and approve again".into(),
            ));
        }
        let v=self.checked(self.http.post(format!("{}/2/media/upload",self.base)).bearer_auth(token).json(&json!({"media":STANDARD.encode(b),"media_category":if a.kind=="video"{"tweet_video"}else{"tweet_image"}}))).await?;
        let media_id = id(&v["data"]["id"])?;
        let mut p = v["data"]["processing_info"].clone();
        for _ in 0..15 {
            match p["state"].as_str() {
                None | Some("succeeded") => return Ok(media_id),
                Some("failed") => return Err(E::Permanent("X media processing failed".into())),
                Some("pending" | "in_progress") => {}
                _ => return Err(E::Permanent("X media state is unsupported".into())),
            }
            tokio::time::sleep(std::time::Duration::from_secs(
                p["check_after_secs"].as_u64().unwrap_or(1).clamp(1, 3),
            ))
            .await;
            let v = self
                .checked(
                    self.http
                        .get(format!("{}/2/media/upload", self.base))
                        .bearer_auth(token)
                        .query(&[("media_id", media_id.as_str()), ("command", "STATUS")]),
                )
                .await?;
            p = v["data"]["processing_info"].clone();
        }
        Err(E::Permanent(
            "X media is still processing; review before retrying".into(),
        ))
    }
}
#[async_trait]
impl Connector for X {
    fn network(&self) -> &'static str {
        "x"
    }
    async fn publish(&self, r: PublishRequest) -> Result<Published, E> {
        if r.access_token.is_empty() {
            return Err(E::AuthExpired("Reconnect X".into()));
        }
        if r.external_id.is_empty()
            || !r.external_id.bytes().all(|b| b.is_ascii_digit())
            || r.text.trim().is_empty()
            || crate::guardrails::x_length(&r.text) > 280
            || r.media.len() > 1
            || (!r.media.is_empty() && r.local_media.is_none())
        {
            return Err(E::Permanent(
                "Review X text limits and upload one image or video".into(),
            ));
        }
        let mut body = json!({"text":r.text});
        if let Some(a) = &r.local_media {
            body["media"] = json!({"media_ids":[self.media(a,&r.access_token).await?]})
        }
        let v = self
            .checked(
                self.http
                    .post(format!("{}/2/tweets", self.base))
                    .bearer_auth(&r.access_token)
                    .json(&body),
            )
            .await?;
        let post = id(&v["data"]["id"])?;
        Ok(Published {
            url: Some(format!("https://x.com/i/web/status/{post}")),
            external_id: post,
        })
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use axum::{extract::State, routing::post, Json, Router};
    use std::sync::{Arc, Mutex};
    fn request() -> PublishRequest {
        PublishRequest {
            external_id: "123".into(),
            idempotency_key: "approved-revision".into(),
            access_token: "fixture-token".into(),
            refresh_token: None,
            text: "Approved X caption".into(),
            link: String::new(),
            media: vec![],
            options: json!({}),
            local_media: None,
        }
    }
    async fn publish(
        State(seen): State<Arc<Mutex<Vec<Value>>>>,
        Json(body): Json<Value>,
    ) -> Json<Value> {
        seen.lock().unwrap().push(body);
        Json(json!({"data":{"id":"987"}}))
    }
    async fn upload(
        State(seen): State<Arc<Mutex<Vec<Value>>>>,
        Json(body): Json<Value>,
    ) -> Json<Value> {
        seen.lock().unwrap().push(body);
        Json(json!({"data":{"id":"456"}}))
    }
    #[tokio::test]
    async fn exact_text_and_uploaded_image_reach_official_payload_shape() {
        let seen = Arc::new(Mutex::new(vec![]));
        let app = Router::new()
            .route("/2/tweets", post(publish))
            .route("/2/media/upload", post(upload))
            .with_state(seen.clone());
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let x = X {
            http: crate::x::http().unwrap(),
            base,
        };
        let first = x.publish(request()).await.unwrap();
        assert_eq!(first.external_id, "987");
        let path = std::env::temp_dir().join(format!("x-media-{}", std::process::id()));
        std::fs::write(&path, [1u8, 2, 3]).unwrap();
        let mut r = request();
        r.media = vec!["upload:fixture-media".into()];
        r.local_media = Some(crate::media::Asset {
            id: "fixture".into(),
            kind: "image".into(),
            mime: "image/jpeg".into(),
            bytes: 3,
            width: 1080,
            height: 1080,
            duration_seconds: 0.0,
            path: path.clone(),
        });
        x.publish(r).await.unwrap();
        let out = seen.lock().unwrap();
        assert_eq!(out.len(), 3);
        assert_eq!(out[0], json!({"text":"Approved X caption"}));
        assert_eq!(out[1]["media"], "AQID");
        assert_eq!(out[1]["media_category"], "tweet_image");
        assert_eq!(out[2]["media"]["media_ids"], json!(["456"]));
        std::fs::remove_file(path).unwrap();
        task.abort();
    }
    #[tokio::test]
    async fn rejects_bad_media_and_overweight_text_before_network() {
        let x = X::new().unwrap();
        let mut r = request();
        r.text = "字".repeat(141);
        assert!(matches!(x.publish(r).await, Err(E::Permanent(_))));
        let mut r = request();
        r.media = vec!["https://example.org/remote.jpg".into()];
        assert!(matches!(x.publish(r).await, Err(E::Permanent(_))));
        assert!(matches!(
            status(reqwest::StatusCode::PAYMENT_REQUIRED),
            E::Permanent(_)
        ));
        assert!(matches!(
            status(reqwest::StatusCode::UNAUTHORIZED),
            E::AuthExpired(_)
        ));
        assert!(matches!(
            status(reqwest::StatusCode::BAD_GATEWAY),
            E::Retryable(_)
        ));
    }
}
