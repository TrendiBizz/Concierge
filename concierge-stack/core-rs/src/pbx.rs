//! Asterisk AudioSocket rules and the call-recording mixer (port of `asterisk_bridge.routes_from_json`, `packet` framing and
//! `telephone_recording.TelephoneRecording`).
use regex::Regex;
use serde_json::Value;
use std::collections::HashSet;
use std::sync::OnceLock;

#[derive(Debug, PartialEq, Eq)]
pub struct Route {
    pub tenant: String,
    pub number: String,
    pub port: i64,
}

#[derive(Debug, PartialEq, Eq)]
pub enum RouteError {
    /// `json.loads` failed.
    Json,
    /// Python raises `TypeError` (wrong shape or type); the exact text is not reproduced.
    Type,
    /// Python raises `ValueError` with this message.
    Value(&'static str),
}

fn re(cell: &'static OnceLock<Regex>, p: &str) -> &'static Regex {
    cell.get_or_init(|| Regex::new(p).unwrap())
}

/// `routes_from_json`: explicit, unique routes only. Numbers whose digits are non-ASCII Unicode digits (Python's `\d` accepts
/// them) are refused.
pub fn routes_from_json(text: &str) -> Result<Vec<Route>, RouteError> {
    let v: Value = serde_json::from_str(text).map_err(|_| RouteError::Json)?;
    let rows = match v.as_array() {
        Some(r) if !r.is_empty() => r,
        _ => {
            return Err(RouteError::Value(
                "At least one explicit business route is required",
            ))
        }
    };
    let mut routes = Vec::new();
    for r in rows {
        let o = r.as_object().ok_or(RouteError::Type)?;
        if o.len() != 3
            || !["tenant", "number", "port"]
                .iter()
                .all(|k| o.contains_key(*k))
        {
            return Err(RouteError::Type);
        }
        // Later checks compare/regex these, which raises for the wrong type in Python.
        routes.push(Route {
            tenant: o["tenant"].as_str().ok_or(RouteError::Type)?.to_string(),
            number: o["number"].as_str().ok_or(RouteError::Type)?.to_string(),
            port: o["port"].as_i64().ok_or(RouteError::Type)?,
        });
    }
    if routes.iter().map(|r| r.port).collect::<HashSet<_>>().len() != routes.len() {
        return Err(RouteError::Value(
            "Each business route needs a unique private port",
        ));
    }
    if routes
        .iter()
        .map(|r| r.number.as_str())
        .collect::<HashSet<_>>()
        .len()
        != routes.len()
    {
        return Err(RouteError::Value(
            "Ambiguous forwarding destinations are forbidden",
        ));
    }
    static SLUG: OnceLock<Regex> = OnceLock::new();
    static NUM: OnceLock<Regex> = OnceLock::new();
    for r in &routes {
        if !re(&SLUG, r"^[a-z0-9][a-z0-9-]{0,79}$").is_match(&r.tenant) {
            return Err(RouteError::Value("Invalid business slug"));
        }
        if !re(&NUM, r"^\+[1-9][0-9]{6,14}$").is_match(&r.number)
            || !(1024..=65535).contains(&r.port)
        {
            return Err(RouteError::Value("Invalid destination or listener port"));
        }
    }
    Ok(routes)
}

/// AudioSocket header: kind (u8) and big-endian length (u16); more than 8192 bytes is refused.
pub fn parse_header(h: [u8; 3]) -> Result<(u8, usize), &'static str> {
    let len = u16::from_be_bytes([h[1], h[2]]) as usize;
    if len > 8192 {
        Err("Oversized AudioSocket packet")
    } else {
        Ok((h[0], len))
    }
}

pub fn encode_packet(kind: u8, body: &[u8]) -> Result<Vec<u8>, &'static str> {
    let length = u16::try_from(body.len()).map_err(|_| "AudioSocket body exceeds u16 length")?;
    let mut out = vec![kind];
    out.extend(length.to_be_bytes());
    out.extend(body);
    Ok(out)
}

// ---- recording mixer ------------------------------------------------------------------------------------------------
pub const RATE: usize = 8000;
pub const LIMIT: usize = 600 * RATE;

#[derive(Default)]
pub struct Recording {
    started: Option<f64>,
    samples: Vec<i16>,
}

impl Recording {
    pub fn start(&mut self, now: f64) {
        if self.started.is_none() {
            self.started = Some(now);
        }
    }

    pub fn discard(&mut self) {
        self.started = None;
        self.samples.clear();
    }

    /// Mix `pcm` (16-bit little-endian) in at the position the clock says it was heard. `Err` when Python's `frombytes` raises.
    pub fn append(&mut self, now: f64, pcm: &[u8]) -> Result<(), &'static str> {
        let Some(started) = self.started else {
            return Ok(());
        };
        if !pcm.len().is_multiple_of(2) {
            return Err("bytes length not a multiple of item size");
        }
        let values: Vec<i16> = pcm
            .as_chunks::<2>()
            .0
            .iter()
            .map(|c| i16::from_le_bytes([c[0], c[1]]))
            .collect();
        let offset = (((now - started) * RATE as f64) as i64).clamp(0, LIMIT as i64) as usize;
        let take = LIMIT - offset;
        let values = &values[..values.len().min(take)];
        if values.is_empty() {
            return Ok(());
        }
        let end = offset + values.len();
        if end > self.samples.len() {
            self.samples.resize(end, 0);
        }
        for (i, v) in values.iter().enumerate() {
            let slot = &mut self.samples[offset + i];
            *slot = (*slot as i32 + *v as i32).clamp(-32768, 32767) as i16;
        }
        Ok(())
    }

    /// A 16-bit mono 8 kHz WAV, byte for byte what Python's `wave` module writes.
    pub fn wav(&self) -> Option<Vec<u8>> {
        if self.started.is_none() || self.samples.is_empty() {
            return None;
        }
        let data: Vec<u8> = self.samples.iter().flat_map(|s| s.to_le_bytes()).collect();
        let mut out = Vec::with_capacity(44 + data.len());
        out.extend(b"RIFF");
        out.extend((36 + data.len() as u32).to_le_bytes());
        out.extend(b"WAVEfmt ");
        out.extend(16u32.to_le_bytes());
        out.extend(1u16.to_le_bytes()); // PCM
        out.extend(1u16.to_le_bytes()); // mono
        out.extend((RATE as u32).to_le_bytes());
        out.extend((RATE as u32 * 2).to_le_bytes());
        out.extend(2u16.to_le_bytes());
        out.extend(16u16.to_le_bytes());
        out.extend(b"data");
        out.extend((data.len() as u32).to_le_bytes());
        out.extend(data);
        Some(out)
    }
}
