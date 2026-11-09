//! Port of the parts of Starlette's `FileResponse` that `main.py` relies on for `/widget.js`, `/admin-ui`, `/owner-ui`
//! and `/owner/social/oauth/callback`: the `ETag` / `Last-Modified` / `Content-Length` headers derived from the file's
//! `stat`, `Accept-Ranges`, and HTTP `Range` / `If-Range` handling (single and multiple ranges).
//!
//! Everything here is pure: the server crate does the file I/O. Expected values come from the live Starlette
//! (`parity/gen_vectors28.py`), including `os.stat` on real files with chosen nanosecond mtimes.
//!
//! Approximations (all fail closed with `RangeError::Unsupported`, which the server answers as a 500):
//! non-ASCII characters inside a range part (Python's `int()` accepts Unicode digits; this port does not), and
//! Unicode whitespace beyond ASCII and `\x1c`-`\x1f` around the units. Integers wider than 128 bits saturate, which
//! changes no outcome because they are only ever compared with the file size.
use chrono::{TimeZone, Utc};

/// Starlette's `FileResponse.max_ranges`: more ranges than this are ignored and the whole file is sent.
pub const MAX_RANGES: usize = 100;

/// What `os.stat` gives the response: size and the modification time with nanosecond resolution.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Stat {
    pub size: u64,
    pub mtime_secs: i64,
    pub mtime_nanos: u32,
}

impl Stat {
    /// `stat_result.st_mtime`: CPython computes the float as `sec + nsec * 1e-9`. At today's epoch a float holds about
    /// 0.2 microseconds, so `...000.999999999` really is `...001.0` (and `Last-Modified` follows the float).
    fn mtime_float(&self) -> f64 {
        self.mtime_secs as f64 + f64::from(self.mtime_nanos) * 1e-9
    }

    /// `str(stat_result.st_mtime)`: the float's shortest repr.
    pub fn mtime_repr(&self) -> String {
        let f = self.mtime_float();
        let text = format!("{f:?}");
        // Rust prints `1e-9` / `1e16` where Python's repr prints `1e-09` / `1e+16`.
        match text.split_once('e') {
            Some((mantissa, exp)) => {
                let n: i32 = exp.parse().unwrap_or(0);
                format!("{mantissa}e{}{:02}", if n < 0 { '-' } else { '+' }, n.abs())
            }
            None => text,
        }
    }

    /// `hashlib.md5(f"{st_mtime}-{st_size}")`, quoted.
    pub fn etag(&self) -> String {
        use md5::{Digest, Md5};
        let base = format!("{}-{}", self.mtime_repr(), self.size);
        let digest = Md5::digest(base.as_bytes());
        let hex: String = digest.iter().map(|b| format!("{b:02x}")).collect();
        format!("\"{hex}\"")
    }

    /// `email.utils.formatdate(st_mtime, usegmt=True)`.
    pub fn last_modified(&self) -> String {
        // `formatdate` -> `time.gmtime(float)`, which floors.
        Utc.timestamp_opt(self.mtime_float().floor() as i64, 0)
            .single()
            .map_or_else(String::new, |t| {
                t.format("%a, %d %b %Y %H:%M:%S GMT").to_string()
            })
    }
}

#[derive(Debug, PartialEq)]
pub enum RangeError {
    /// `MalformedRangeHeader(content)`: a 400 with this plain-text body.
    Malformed(String),
    /// `RangeNotSatisfiable(max_size)`: a 416 with `Content-Range: bytes */size`.
    NotSatisfiable(i128),
    /// An input this port declines instead of guessing.
    Unsupported,
}

fn is_py_space(c: char) -> bool {
    c.is_whitespace() || ('\x1c'..='\x1f').contains(&c)
}

fn py_strip(s: &str) -> &str {
    s.trim_matches(is_py_space)
}

/// Python's `int(text)` for an already-stripped string: an optional sign, then digits with single underscores
/// between them. `Err(false)` is a `ValueError`; `Err(true)` is an input this port declines (non-ASCII text).
fn py_int(text: &str) -> Result<i128, bool> {
    if !text.is_ascii() {
        return Err(true);
    }
    let t = py_strip(text);
    let (neg, digits) = match t.strip_prefix('-') {
        Some(rest) => (true, rest),
        None => (false, t.strip_prefix('+').unwrap_or(t)),
    };
    let bytes = digits.as_bytes();
    if bytes.is_empty() || bytes[0] == b'_' || bytes[bytes.len() - 1] == b'_' {
        return Err(false);
    }
    let mut value: i128 = 0;
    let mut previous_underscore = false;
    for &b in bytes {
        match b {
            b'_' if previous_underscore => return Err(false),
            b'_' => previous_underscore = true,
            b'0'..=b'9' => {
                previous_underscore = false;
                value = value
                    .saturating_mul(10)
                    .saturating_add(i128::from(b - b'0'));
            }
            _ => return Err(false),
        }
    }
    Ok(if neg { -value } else { value })
}

/// `FileResponse._parse_ranges`.
fn parse_ranges(range: &str, file_size: i128) -> Result<Vec<(i128, i128)>, RangeError> {
    let mut ranges = Vec::new();
    for part in range.split(',') {
        let part = py_strip(part);
        if part.is_empty() || part == "-" {
            continue;
        }
        let Some((start_raw, end_raw)) = part.split_once('-') else {
            continue;
        };
        let (start_str, end_str) = (py_strip(start_raw), py_strip(end_raw));
        let number = |s: &str| match py_int(s) {
            Ok(n) => Ok(Some(n)),
            Err(true) => Err(RangeError::Unsupported),
            Err(false) => Ok(None),
        };
        // `start` is evaluated first, then `end`; a ValueError in either skips the whole part.
        let start = if start_str.is_empty() {
            match number(end_str)? {
                Some(n) => (file_size - n).max(0),
                None => continue,
            }
        } else {
            match number(start_str)? {
                Some(n) => n,
                None => continue,
            }
        };
        let end = if !start_str.is_empty() && !end_str.is_empty() {
            match number(end_str)? {
                Some(n) if n < file_size => n + 1,
                Some(_) => file_size,
                None => continue,
            }
        } else {
            file_size
        };
        ranges.push((start, end));
    }
    Ok(ranges)
}

/// `FileResponse._parse_range_header`. `Ok(vec![])` means "ignore the header and send the whole file".
pub fn parse_range_header(
    http_range: &str,
    file_size: i128,
) -> Result<Vec<(i128, i128)>, RangeError> {
    let Some((units, range)) = http_range.split_once('=') else {
        return Err(RangeError::Malformed("Malformed range header.".into()));
    };
    if py_strip(units).to_lowercase() != "bytes" {
        return Err(RangeError::Malformed("Only support bytes range".into()));
    }
    if range.matches(',').count() + 1 > MAX_RANGES {
        return Ok(Vec::new());
    }
    let mut ranges = parse_ranges(range, file_size)?;
    if ranges.is_empty() {
        return Err(RangeError::Malformed(
            "Range header: range must be requested".into(),
        ));
    }
    if ranges.iter().any(|&(s, _)| !(0 <= s && s < file_size)) {
        return Err(RangeError::NotSatisfiable(file_size));
    }
    if ranges.iter().any(|&(s, e)| s >= e) {
        return Err(RangeError::Malformed(
            "Range header: start must be less than end".into(),
        ));
    }
    if ranges.len() == 1 {
        return Ok(ranges);
    }
    ranges.sort();
    let mut merged = vec![ranges[0]];
    for &(start, end) in &ranges[1..] {
        let (last_start, last_end) = *merged.last().unwrap();
        if start <= last_end {
            *merged.last_mut().unwrap() = (last_start, last_end.max(end));
        } else {
            merged.push((start, end));
        }
    }
    Ok(merged)
}

/// `FileResponse._should_use_range`: an `If-Range` that is a weak validator, or matches neither `Last-Modified` nor
/// the `ETag`, makes the server ignore `Range` and send the whole file.
pub fn should_use_range(if_range: &str, last_modified: &str, etag: &str) -> bool {
    if if_range.starts_with("W/") {
        return false;
    }
    if_range == last_modified || if_range == etag
}

/// The per-part header block `generate_multipart` emits before each range's bytes.
pub fn multipart_part_header(
    boundary: &str,
    content_type: &str,
    start: i128,
    end: i128,
    max_size: i128,
) -> String {
    format!(
        "--{boundary}\r\nContent-Type: {content_type}\r\nContent-Range: bytes {start}-{}/{max_size}\r\n\r\n",
        end - 1
    )
}

/// `generate_multipart`'s precomputed `Content-Length` (what Python sends in the header).
pub fn multipart_content_length(
    ranges: &[(i128, i128)],
    boundary: &str,
    max_size: i128,
    content_type: &str,
) -> i128 {
    let static_part = 49 + boundary.len() + content_type.len() + max_size.to_string().len();
    let parts: i128 = ranges
        .iter()
        .map(|&(start, end)| {
            (start.to_string().len() + (end - 1).to_string().len() + static_part) as i128
                + (end - start)
        })
        .sum();
    parts + 4 + boundary.len() as i128
}
