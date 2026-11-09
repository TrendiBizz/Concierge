//! Upload the customer-approved local asset to LinkedIn's official media API.
use crate::{connector::ConnectorError, media::Asset};
use serde_json::{json, Value};
fn upload_url(value: &str) -> Result<(), ConnectorError> {
    let u = reqwest::Url::parse(value)
        .map_err(|_| ConnectorError::Permanent("LinkedIn upload URL invalid".into()))?;
    let host = u.host_str().unwrap_or("");
    if u.scheme() != "https"
        || !u.username().is_empty()
        || u.password().is_some()
        || !(host == "www.linkedin.com"
            || host.ends_with(".linkedin.com")
            || host.ends_with(".licdn.com"))
    {
        return Err(ConnectorError::Permanent(
            "LinkedIn upload host is not trusted".into(),
        ));
    }
    Ok(())
}
fn error() -> ConnectorError {
    ConnectorError::Retryable(
        "LinkedIn media transfer outcome uncertain; review before retrying".into(),
    )
}
pub async fn upload(
    http: &reqwest::Client,
    version: &str,
    token: &str,
    owner: &str,
    asset: &Asset,
) -> Result<Value, ConnectorError> {
    let kind = if asset.kind == "video" {
        "videos"
    } else {
        "images"
    };
    let request = if asset.kind == "video" {
        json!({"initializeUploadRequest":{"owner":owner,"fileSizeBytes":asset.bytes,"uploadCaptions":false,"uploadThumbnail":false}})
    } else {
        json!({"initializeUploadRequest":{"owner":owner}})
    };
    let response = http
        .post(format!(
            "https://api.linkedin.com/rest/{kind}?action=initializeUpload"
        ))
        .bearer_auth(token)
        .header("Linkedin-Version", version)
        .header("X-Restli-Protocol-Version", "2.0.0")
        .json(&request)
        .send()
        .await
        .map_err(|_| error())?;
    if !response.status().is_success() {
        return Err(ConnectorError::Permanent(
            "LinkedIn media permission or upload initialization was rejected".into(),
        ));
    }
    let body: Value = response.json().await.map_err(|_| error())?;
    let value = &body["value"];
    let path = asset.path.clone();
    let bytes = tokio::task::spawn_blocking(move || std::fs::read(path))
        .await
        .map_err(|_| error())?
        .map_err(|_| error())?;
    let urn = if kind == "videos" {
        let urn = value["video"].as_str().ok_or_else(error)?;
        let instructions = value["uploadInstructions"].as_array().ok_or_else(error)?;
        let mut parts = Vec::new();
        let mut expected = 0u64;
        for part in instructions {
            let first = part["firstByte"].as_u64().ok_or_else(error)?;
            let last = part["lastByte"].as_u64().ok_or_else(error)?;
            if first != expected || last < first || last >= asset.bytes {
                return Err(ConnectorError::Permanent(
                    "LinkedIn media upload ranges were invalid".into(),
                ));
            }
            expected = last + 1;
            let url = part["uploadUrl"].as_str().ok_or_else(error)?;
            upload_url(url)?;
            let response = http
                .put(url)
                .header("Content-Type", "application/octet-stream")
                .body(bytes[first as usize..=last as usize].to_vec())
                .send()
                .await
                .map_err(|_| error())?;
            if !response.status().is_success() {
                return Err(error());
            }
            parts.push(
                response
                    .headers()
                    .get("etag")
                    .and_then(|v| v.to_str().ok())
                    .ok_or_else(error)?
                    .trim_matches('"')
                    .to_string(),
            );
        }
        if expected != asset.bytes {
            return Err(error());
        }
        let finalized=http.post("https://api.linkedin.com/rest/videos?action=finalizeUpload").bearer_auth(token).header("Linkedin-Version",version).header("X-Restli-Protocol-Version","2.0.0").json(&json!({"finalizeUploadRequest":{"video":urn,"uploadToken":value["uploadToken"],"uploadedPartIds":parts}})).send().await.map_err(|_|error())?;
        if !finalized.status().is_success() {
            return Err(error());
        }
        urn.to_string()
    } else {
        let url = value["uploadUrl"].as_str().ok_or_else(error)?;
        upload_url(url)?;
        let response = http
            .put(url)
            .bearer_auth(token)
            .header("Content-Type", &asset.mime)
            .body(bytes)
            .send()
            .await
            .map_err(|_| error())?;
        if !response.status().is_success() {
            return Err(error());
        }
        value["image"].as_str().ok_or_else(error)?.to_string()
    };
    let encoded =
        reqwest::Url::parse_with_params("https://api.linkedin.com", &[("id", urn.as_str())])
            .map_err(|_| error())?
            .query()
            .unwrap_or("")
            .trim_start_matches("id=")
            .to_string();
    for _ in 0..45 {
        let r = http
            .get(format!("https://api.linkedin.com/rest/{kind}/{encoded}"))
            .bearer_auth(token)
            .header("Linkedin-Version", version)
            .header("X-Restli-Protocol-Version", "2.0.0")
            .send()
            .await
            .map_err(|_| error())?;
        if !r.status().is_success() {
            return Err(error());
        }
        let body: Value = r.json().await.map_err(|_| error())?;
        match body["status"].as_str() {
            Some("AVAILABLE") => return Ok(json!({"media":{"id":urn}})),
            Some("PROCESSING_FAILED") | Some("WAITING_UPLOAD") => {
                return Err(ConnectorError::Permanent(
                    "LinkedIn could not process this media".into(),
                ))
            }
            _ => tokio::time::sleep(std::time::Duration::from_secs(2)).await,
        }
    }
    Err(ConnectorError::Retryable(
        "LinkedIn media is still processing; reconcile before submitting a post".into(),
    ))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn provider_uploads_cannot_exfiltrate_customer_media() {
        assert!(upload_url("https://www.linkedin.com/dms-uploads/a").is_ok());
        assert!(upload_url("https://video.licdn.com/upload").is_ok());
        for url in [
            "https://linkedin.com.attacker.test/upload",
            "http://www.linkedin.com/upload",
            "https://www.linkedin.com@attacker.test/upload",
        ] {
            assert!(upload_url(url).is_err());
        }
    }
}
