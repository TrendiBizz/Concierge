//! Port of the guard and table list in `owner_maintenance.py`. The bounded DELETE itself runs in Python/SQL.

/// The tables pruned, in order, with the constant predicate used for each (never user supplied).
pub const TABLES: [(&str, &str); 3] = [
    ("tenant_sessions", "expires_at <= now()"),
    (
        "tenant_invites",
        "expires_at <= now() OR used_at IS NOT NULL",
    ),
    ("owner_login_limits", "window_until <= now()"),
];

/// `1 <= batch_size <= 5000`, else the ValueError text.
pub fn check_batch_size(n: i64) -> Result<(), &'static str> {
    if (1..=5000).contains(&n) {
        Ok(())
    } else {
        Err("batch_size must be between 1 and 5000")
    }
}
