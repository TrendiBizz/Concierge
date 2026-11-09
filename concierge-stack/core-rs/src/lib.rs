//! Concierge core logic in Rust. Each module is a port of the Python module of the same name in
//! `api/app` and is verified against golden vectors produced by that Python code (see `parity/`).

pub mod acknowledgements;
pub mod automation;
pub mod booking_text;
pub mod calendar;
pub mod campaigns;
pub mod channel_auth;
pub mod chat;
pub mod chunking;
pub mod contact;
pub mod convo;
pub mod crawler;
pub mod drafts;
pub mod evals;
pub mod events;
pub mod guard;
pub mod ical;
pub mod inbound;
pub mod ingest;
pub mod knowledge;
pub mod maintenance;
pub mod owner_auth;
pub mod owner_notifications;
pub mod owner_profile;
pub mod phone_setup;
pub mod public_fetch;
pub mod pydantic;
pub mod pyjson;
pub mod pyurl;
pub mod pyval;
pub mod quotation;
pub mod rag;
pub mod rate_limit;
pub mod requests;
pub mod robots;
pub mod sales;
pub mod schedule;
pub mod scoring;
pub mod settings;
pub mod sla;
pub mod sms;
pub mod social;
pub mod tasks;
pub mod telephony;
pub mod tenants;
pub mod tools;
pub mod unsub;
pub mod voice_records;
pub mod voice_session;

/// Python `str` whitespace (`str.isspace`), which is slightly wider than `char::is_whitespace`.
pub(crate) fn is_py_space(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

/// Python `str.strip()`.
pub(crate) fn py_strip(s: &str) -> &str {
    s.trim_matches(is_py_space)
}

pub mod device_sms;
pub mod pbx;
pub mod phone_relay;

/// Python `str.splitlines()`: splits on `\n`, `\r\n`, `\r`, `\v`, `\f`, FS/GS/RS, NEL, LS and PS; no empty tail.
pub(crate) fn py_splitlines(s: &str) -> Vec<&str> {
    let mut out = Vec::new();
    let mut start = 0;
    let mut chars = s.char_indices().peekable();
    while let Some((i, c)) = chars.next() {
        let is_break = matches!(
            c,
            '\n' | '\r'
                | '\u{b}'
                | '\u{c}'
                | '\u{1c}'
                | '\u{1d}'
                | '\u{1e}'
                | '\u{85}'
                | '\u{2028}'
                | '\u{2029}'
        );
        if is_break {
            out.push(&s[start..i]);
            let mut end = i + c.len_utf8();
            if c == '\r' {
                if let Some(&(j, '\n')) = chars.peek() {
                    chars.next();
                    end = j + 1;
                }
            }
            start = end;
        }
    }
    if start < s.len() {
        out.push(&s[start..]);
    }
    out
}
