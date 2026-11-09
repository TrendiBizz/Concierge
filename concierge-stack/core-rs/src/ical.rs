//! Read-only iCalendar (RFC 5545) feed of a client's appointments.
use time::{format_description::FormatItem, macros::format_description, OffsetDateTime};

const PRODID: &str = "-//Concierge//Appointments//EN";
const STAMP: &[FormatItem<'static>] = format_description!("[year][month][day]T[hour][minute][second]Z");

#[derive(Debug, Clone, Default)]
pub struct Appointment {
    pub id: String,
    pub name: Option<String>,
    pub phone: Option<String>,
    pub email: Option<String>,
    pub notes: Option<String>,
    pub status: Option<String>,
    /// Unix seconds, UTC.
    pub starts_at: i64,
    pub ends_at: i64,
}

/// Escape a TEXT value: backslash, semicolon, comma and line breaks.
pub fn esc(text: &str) -> String {
    text.replace('\\', "\\\\")
        .replace(';', "\\;")
        .replace(',', "\\,")
        .replace("\r\n", "\n")
        .replace('\r', "\n")
        .replace('\n', "\\n")
}

/// Fold a content line at 75 octets, never splitting a multi-byte character.
pub fn fold(line: &str) -> String {
    if line.len() <= 75 {
        return line.to_string();
    }
    let mut parts: Vec<String> = Vec::new();
    let mut current = String::new();
    let mut limit = 75;
    for ch in line.chars() {
        if current.len() + ch.len_utf8() > limit {
            parts.push(std::mem::take(&mut current));
            limit = 74; // continuation lines start with a space
        }
        current.push(ch);
    }
    parts.push(current);
    parts.join("\r\n ")
}

fn stamp(epoch: i64) -> String {
    OffsetDateTime::from_unix_timestamp(epoch)
        .expect("timestamp in range")
        .format(STAMP)
        .expect("valid format")
}

fn some(o: &Option<String>) -> Option<&str> {
    o.as_deref().filter(|s| !s.is_empty())
}

pub fn build(tenant_name: &str, appointments: &[Appointment], now_epoch: i64) -> String {
    let mut lines: Vec<String> = vec![
        "BEGIN:VCALENDAR".into(),
        "VERSION:2.0".into(),
        format!("PRODID:{PRODID}"),
        "CALSCALE:GREGORIAN".into(),
        "METHOD:PUBLISH".into(),
        format!("X-WR-CALNAME:{}", esc(&format!("{tenant_name} appointments"))),
        "REFRESH-INTERVAL;VALUE=DURATION:PT15M".into(),
        "X-PUBLISHED-TTL:PT15M".into(),
    ];
    for a in appointments {
        let description = [
            some(&a.phone).map(|p| format!("Phone: {p}")),
            some(&a.email).map(|e| format!("Email: {e}")),
            some(&a.notes).map(str::to_string),
        ]
        .into_iter()
        .flatten()
        .collect::<Vec<_>>()
        .join("\n");
        lines.push("BEGIN:VEVENT".into());
        lines.push(format!("UID:appt-{}@concierge", a.id));
        lines.push(format!("DTSTAMP:{}", stamp(now_epoch)));
        lines.push(format!("DTSTART:{}", stamp(a.starts_at)));
        lines.push(format!("DTEND:{}", stamp(a.ends_at)));
        lines.push(format!("SUMMARY:{}", esc(&format!("{} - {tenant_name}", some(&a.name).unwrap_or("Appointment")))));
        if !description.is_empty() {
            lines.push(format!("DESCRIPTION:{}", esc(&description)));
        }
        lines.push(format!("STATUS:{}", if a.status.as_deref() == Some("cancelled") { "CANCELLED" } else { "CONFIRMED" }));
        lines.push("END:VEVENT".into());
    }
    lines.push("END:VCALENDAR".into());
    let mut out = lines.iter().filter(|l| !l.is_empty()).map(|l| fold(l)).collect::<Vec<_>>().join("\r\n");
    out.push_str("\r\n");
    out
}
