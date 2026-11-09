//! Concierge core logic in Rust. Each module is a port of the Python module of the same name in
//! `api/app` and is verified against golden vectors produced by that Python code (see `parity/`).

pub mod automation;
pub mod booking_text;
pub mod calendar;
pub mod campaigns;
pub mod chunking;
pub mod contact;
pub mod convo;
pub mod events;
pub mod guard;
pub mod ical;
pub mod owner_auth;
pub mod owner_notifications;
pub mod pyval;
pub mod quotation;
pub mod rate_limit;
pub mod sales;
pub mod schedule;
pub mod scoring;
pub mod sla;
pub mod tasks;
pub mod tools;
pub mod unsub;
pub mod voice_records;

/// Python `str` whitespace (`str.isspace`), which is slightly wider than `char::is_whitespace`.
pub(crate) fn is_py_space(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

/// Python `str.strip()`.
pub(crate) fn py_strip(s: &str) -> &str {
    s.trim_matches(is_py_space)
}
