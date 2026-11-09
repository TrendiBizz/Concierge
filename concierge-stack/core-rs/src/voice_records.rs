//! Voice-recording helpers (port of `voice_records.digest` and `audio_type`).
use sha2::{Digest, Sha256};

pub fn digest(token: &str) -> String {
    Sha256::digest(token.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn magic(mime: &str) -> Option<Option<&'static [u8]>> {
    Some(match mime {
        "audio/webm" => Some(&[0x1a, 0x45, 0xdf, 0xa3][..]),
        "audio/ogg" => Some(&b"OggS"[..]),
        "audio/mp4" => None,
        "audio/wav" => Some(&b"RIFF"[..]),
        _ => return None,
    })
}

/// What Python's `wave` module reads from a WAV file: channels, sample width, rate, frame count, bytes of frame data present.
struct Wav {
    channels: u16,
    width: u16,
    rate: u32,
    frames: u64,
    data_len: u64,
}

fn le16(b: &[u8], o: usize) -> Option<u16> {
    Some(u16::from_le_bytes(b.get(o..o + 2)?.try_into().ok()?))
}
fn le32(b: &[u8], o: usize) -> Option<u32> {
    Some(u32::from_le_bytes(b.get(o..o + 4)?.try_into().ok()?))
}

/// Mirrors `wave.open(..., 'rb')`: RIFF/WAVE header, a PCM `fmt ` chunk before `data`. `None` is `wave.Error`/`EOFError`.
fn read_wav(b: &[u8]) -> Option<Wav> {
    if b.get(0..4)? != b"RIFF" || b.get(8..12)? != b"WAVE" {
        return None;
    }
    let (mut pos, mut fmt) = (12usize, None);
    loop {
        let id = b.get(pos..pos + 4)?;
        let size = le32(b, pos + 4)? as usize;
        let body = pos + 8;
        if id == b"fmt " {
            if le16(b, body)? != 1 {
                return None; // not PCM: wave.Error("unknown format")
            }
            let channels = le16(b, body + 2)?;
            let rate = le32(b, body + 4)?;
            let bits = le16(b, body + 14)?;
            let width = bits.div_ceil(8);
            if channels == 0 || width == 0 {
                return None;
            }
            fmt = Some((channels, width, rate));
        } else if id == b"data" {
            let (channels, width, rate) = fmt?;
            let available = b.len().saturating_sub(body).min(size) as u64;
            let frame_bytes = channels as u64 * width as u64;
            let frames = size as u64 / frame_bytes;
            return Some(Wav {
                channels,
                width,
                rate,
                frames,
                data_len: available.min(frames * frame_bytes),
            });
        }
        pos = body + size + (size & 1);
    }
}

/// Validate an uploaded recording; `Err` is the `(status, message)` the API returns.
pub fn audio_type(content_type: &str, body: &[u8]) -> Result<&'static str, (u16, &'static str)> {
    let mime = content_type
        .split(';')
        .next()
        .unwrap_or("")
        .trim()
        .to_lowercase();
    let known = ["audio/webm", "audio/ogg", "audio/mp4", "audio/wav"];
    let Some(mime_static) = known.iter().find(|m| **m == mime) else {
        return Err((415, "Unsupported audio recording"));
    };
    if body.len() < 16 {
        return Err((415, "Unsupported audio recording"));
    }
    let valid = match magic(mime_static).flatten() {
        None => body.get(4..8) == Some(&b"ftyp"[..]),
        Some(m) => body.starts_with(m),
    };
    if !valid {
        return Err((415, "Audio container does not match its type"));
    }
    if *mime_static == "audio/wav" {
        let bad = (415, "Invalid telephone recording");
        let w = read_wav(body).ok_or(bad)?;
        if (w.channels, w.width, w.rate) != (1, 2, 8000) {
            return Err(bad);
        }
        if w.frames > 600 * 8000 || w.data_len != w.frames * 2 {
            return Err(bad);
        }
    }
    Ok(mime_static)
}
