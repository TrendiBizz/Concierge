//! Port of the request-edge rules in `main.py` and `security.py`: the same-origin boundary for the owner portal and device
//! SMS, and the operator admin-token gate. No server runs here; these decide what a request is allowed to reach.
use crate::requests::origin_of;
use subtle::ConstantTimeEq;

#[derive(Debug, PartialEq, Eq)]
pub enum Boundary {
    /// Not a protected path: untouched.
    Passthrough,
    /// A protected path whose origin is acceptable: serve it with the three hardening headers.
    Protected,
    /// A protected path with a foreign Origin: answer 403 (with `Cache-Control: no-store`) and do not serve it.
    Refuse,
}

pub const PROTECTED_HEADERS: [(&str, &str); 3] = [
    ("cache-control", "no-store"),
    ("x-content-type-options", "nosniff"),
    ("referrer-policy", "no-referrer"),
];

fn protected(path: &str) -> bool {
    path == "/owner-ui" || path.starts_with("/owner/") || path.starts_with("/api/v1/device-sms/")
}

/// `owner_boundary`: `scheme`/`netloc` come from the request URL, `origin` from its `Origin` header (absent or empty is fine).
pub fn owner_boundary(
    path: &str,
    scheme: &str,
    netloc: &str,
    origin: Option<&str>,
    public_base_url: &str,
) -> Boundary {
    if !protected(path) {
        return Boundary::Passthrough;
    }
    if let Some(o) = origin.filter(|o| !o.is_empty()) {
        let own = format!("{scheme}://{netloc}").to_lowercase();
        let public = origin_of(public_base_url).unwrap_or_default();
        let o = o.trim_end_matches('/').to_lowercase();
        if o != own && o != public {
            return Boundary::Refuse;
        }
    }
    Boundary::Protected
}

/// `require_admin`: `Err((status, detail))`.
pub fn require_admin(expected: &str, given: &str) -> Result<(), (u16, &'static str)> {
    if expected.is_empty() {
        return Err((503, "ADMIN_TOKEN is not configured"));
    }
    if !bool::from(given.as_bytes().ct_eq(expected.as_bytes())) {
        return Err((401, "Invalid admin token"));
    }
    Ok(())
}
