//! Tenant-owned media uploads. Native ffprobe validates type/dimensions/duration.
//! Public provider downloads use short-lived encrypted capabilities, not file paths.
use crate::vault::Vault;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Asset {
    pub id: String,
    pub kind: String,
    pub mime: String,
    pub bytes: u64,
    pub width: u32,
    pub height: u32,
    pub duration_seconds: f64,
    #[serde(skip)]
    pub path: PathBuf,
}
fn valid(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
}
fn root() -> PathBuf {
    std::env::var("SOCIAL_MEDIA_DIR")
        .unwrap_or_else(|_| "/data/media".into())
        .into()
}
pub fn load(customer: &str, id: &str) -> Result<Asset, String> {
    if !valid(customer) || !valid(id) {
        return Err("Invalid media identifier".into());
    }
    let dir = root().join(customer);
    let data = std::fs::read(dir.join(format!("{id}.json")))
        .map_err(|_| "Media is not available for this business")?;
    let mut asset: Asset = serde_json::from_slice(&data).map_err(|_| "Media record is invalid")?;
    asset.path = dir.join(format!("{id}.bin"));
    Ok(asset)
}
pub fn save(customer: &str, bytes: &[u8]) -> Result<Asset, String> {
    if !valid(customer) || bytes.is_empty() || bytes.len() > 64 * 1024 * 1024 {
        return Err("Upload an image or video smaller than 64 MB".into());
    }
    use base64::Engine;
    use rand::RngCore;
    let mut random = [0u8; 24];
    rand::thread_rng().fill_bytes(&mut random);
    let id = base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(random);
    let dir = root().join(customer);
    std::fs::create_dir_all(&dir).map_err(|_| "Media storage unavailable")?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&dir, std::fs::Permissions::from_mode(0o700))
            .map_err(|_| "Media storage permissions unavailable")?;
    }
    let path = dir.join(format!("{id}.bin"));
    std::fs::write(&path, bytes).map_err(|_| "Media upload failed")?;
    let result = (|| {
        let output = bounded_command("ffprobe")
            .args([
                "-protocol_whitelist",
                "file,pipe",
                "-format_whitelist",
                "mov,png_pipe,jpeg_pipe,image2",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height,duration:format=duration",
                "-of",
                "json",
            ])
            .arg(&path)
            .output()
            .map_err(|_| "Media processing is not installed")?;
        if !output.status.success() {
            return Err("The file is not a supported image or video".to_string());
        }
        let info: serde_json::Value =
            serde_json::from_slice(&output.stdout).map_err(|_| "Cannot inspect uploaded media")?;
        let stream = &info["streams"][0];
        let codec = stream["codec_name"]
            .as_str()
            .ok_or("Uploaded file has no video or image stream")?;
        let (kind, mut mime) = match codec {
            "png" => ("image", "image/png"),
            "mjpeg" => ("image", "image/jpeg"),
            "h264" | "hevc" | "av1" | "vp9" | "mpeg4" => ("video", "video/mp4"),
            _ => return Err("Use a JPG/PNG image or MP4/MOV video".into()),
        };
        let mut width = stream["width"].as_u64().unwrap_or(0) as u32;
        let mut height = stream["height"].as_u64().unwrap_or(0) as u32;
        if width == 0 || height == 0 || width > 16384 || height > 16384 {
            return Err("Media dimensions are unsupported".into());
        }
        let duration = info["format"]["duration"]
            .as_str()
            .or_else(|| stream["duration"].as_str())
            .and_then(|s| s.parse::<f64>().ok())
            .unwrap_or(0.0);
        if kind == "video" && (!duration.is_finite() || duration <= 0.0 || duration > 3600.0) {
            return Err("Use a video up to one hour long".into());
        }
        let mut final_bytes = bytes.len() as u64;
        if kind == "video" {
            let normalized = dir.join(format!("{id}.mp4"));
            let status = bounded_command("ffmpeg")
                .args([
                    "-nostdin",
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-format_whitelist",
                    "mov",
                    "-i",
                ])
                .arg(&path)
                .args([
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a?",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-pix_fmt",
                    "yuv420p",
                    "-vf",
                    "scale='min(1920,iw)':'min(1920,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
                    "-threads",
                    "1",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    "-y",
                ])
                .arg(&normalized)
                .status()
                .map_err(|_| "Video processing unavailable")?;
            if !status.success() {
                let _ = std::fs::remove_file(&normalized);
                return Err("This video could not be prepared for social publishing".into());
            }
            final_bytes = std::fs::metadata(&normalized)
                .map_err(|_| "Prepared video unavailable")?
                .len();
            if final_bytes > 64 * 1024 * 1024 {
                let _ = std::fs::remove_file(&normalized);
                return Err("Prepared video exceeds 64 MB; use a shorter video".into());
            }
            std::fs::rename(normalized, &path).map_err(|_| "Prepared video cannot be saved")?;
            let probe = bounded_command("ffprobe")
                .args([
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "json",
                ])
                .arg(&path)
                .output()
                .map_err(|_| "Prepared video inspection failed")?;
            let measured: serde_json::Value = serde_json::from_slice(&probe.stdout)
                .map_err(|_| "Prepared video inspection invalid")?;
            width = measured["streams"][0]["width"]
                .as_u64()
                .ok_or("Prepared width missing")? as u32;
            height = measured["streams"][0]["height"]
                .as_u64()
                .ok_or("Prepared height missing")? as u32;
        }
        if kind == "image" {
            let normalized = dir.join(format!("{id}.jpg"));
            let status = bounded_command("ffmpeg").args(["-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe", "-i"]).arg(&path)
                .args(["-frames:v", "1", "-vf", "scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2:color=white", "-q:v", "2", "-threads", "1", "-y"]).arg(&normalized).status().map_err(|_| "Image processing unavailable")?;
            if !status.success() {
                let _ = std::fs::remove_file(normalized);
                return Err("Image could not be prepared".into());
            }
            final_bytes = std::fs::metadata(&normalized)
                .map_err(|_| "Image unavailable")?
                .len();
            std::fs::rename(normalized, &path).map_err(|_| "Image cannot be saved")?;
            width = 1080;
            height = 1080;
            mime = "image/jpeg";
        }
        let asset = Asset {
            id: id.clone(),
            kind: kind.into(),
            mime: mime.into(),
            bytes: final_bytes,
            width,
            height,
            duration_seconds: duration,
            path: path.clone(),
        };
        std::fs::write(
            dir.join(format!("{id}.json")),
            serde_json::to_vec(&asset).map_err(|_| "Media metadata unavailable")?,
        )
        .map_err(|_| "Media metadata cannot be saved")?;
        Ok(asset)
    })();
    if result.is_err() {
        let _ = std::fs::remove_file(&path);
    }
    result
}
#[derive(Serialize, Deserialize)]
struct Capability {
    customer: String,
    id: String,
    expires: i64,
}
pub fn provider_url(vault: &Vault, customer: &str, id: &str) -> Result<String, String> {
    load(customer, id)?;
    let base = std::env::var("SOCIAL_PUBLIC_MEDIA_BASE")
        .map_err(|_| "Public media delivery is not configured")?;
    let url = reqwest::Url::parse(&base).map_err(|_| "Public media URL is invalid")?;
    if url.scheme() != "https"
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
    {
        return Err("Public media URL must use HTTPS".into());
    }
    let cap = serde_json::to_string(&Capability {
        customer: customer.into(),
        id: id.into(),
        expires: crate::now_unix() + 21600,
    })
    .map_err(|_| "Media permission unavailable")?;
    use base64::Engine;
    let token = vault.seal(&cap, "provider-media-download")?;
    Ok(format!(
        "{}/{}",
        base.trim_end_matches('/'),
        base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(token)
    ))
}
pub fn download(vault: &Vault, token: &str) -> Result<Asset, String> {
    if token.len() > 2048 {
        return Err("Media permission invalid".into());
    }
    use base64::Engine;
    let token = base64::engine::general_purpose::URL_SAFE_NO_PAD
        .decode(token)
        .map_err(|_| "Media permission invalid")?;
    let sealed = String::from_utf8(token).map_err(|_| "Media permission invalid")?;
    let text = vault.open(&sealed, "provider-media-download")?;
    let cap: Capability = serde_json::from_str(&text).map_err(|_| "Media permission invalid")?;
    if cap.expires < crate::now_unix() {
        return Err("Media permission expired".into());
    }
    load(&cap.customer, &cap.id)
}

/// A Google Business update uses an approved still image when the brief contains video.
pub fn poster(customer: &str, id: &str) -> Result<Asset, String> {
    let original = load(customer, id)?;
    if original.kind != "video" {
        return Ok(original);
    }
    let poster_id = format!("{id}-poster");
    if let Ok(asset) = load(customer, &poster_id) {
        return Ok(asset);
    }
    let path = root().join(customer).join(format!("{poster_id}.bin"));
    let result = bounded_command("ffmpeg")
        .args([
            "-nostdin",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            "mov",
            "-i",
        ])
        .arg(&original.path)
        .args([
            "-frames:v",
            "1",
            "-c:v",
            "mjpeg",
            "-f",
            "image2",
            "-threads",
            "1",
            "-y",
        ])
        .arg(&path)
        .status()
        .map_err(|_| "Video thumbnail unavailable")?;
    if !result.success() {
        let _ = std::fs::remove_file(path);
        return Err("Cannot prepare a still image from this video".into());
    }
    let asset = Asset {
        id: poster_id.clone(),
        kind: "image".into(),
        mime: "image/jpeg".into(),
        bytes: std::fs::metadata(&path)
            .map_err(|_| "Thumbnail unavailable")?
            .len(),
        width: original.width,
        height: original.height,
        duration_seconds: 0.0,
        path,
    };
    std::fs::write(
        root().join(customer).join(format!("{poster_id}.json")),
        serde_json::to_vec(&asset).map_err(|_| "Thumbnail metadata unavailable")?,
    )
    .map_err(|_| "Thumbnail cannot be saved")?;
    Ok(asset)
}

fn bounded_command(program: &str) -> std::process::Command {
    let timeout = if cfg!(target_os = "macos") {
        "gtimeout"
    } else {
        "timeout"
    };
    let mut command = std::process::Command::new(timeout);
    command.args(["--kill-after=5s", "120s", program]);
    command
}
