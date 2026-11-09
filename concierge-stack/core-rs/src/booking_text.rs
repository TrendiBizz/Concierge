//! Visitor-facing booking wording (port of the pure parts of `booking.book` / `booking_result`).
use crate::schedule::fmt_local;
use chrono::{DateTime, Utc};
use chrono_tz::Tz;
use serde_json::{json, Value};

pub fn read_back(name: &str, tz: Tz, start: DateTime<Utc>, phone: &str, email: &str) -> String {
    let wher = if phone.is_empty() { email } else { phone };
    format!(
        "{name}, {}. We'll confirm with you at {wher}.",
        fmt_local(tz, start)
    )
}

pub struct Appointment<'a> {
    pub id: &'a str,
    pub starts_at: DateTime<Utc>,
    pub calendar_state: Option<&'a str>,
    pub invitation_state: Option<&'a str>,
}

pub fn booking_result(tz: Tz, appt: &Appointment, duplicate: bool) -> Value {
    let synced = appt.calendar_state == Some("synced");
    let when = fmt_local(tz, appt.starts_at);
    let confirmation = if synced {
        format!(
            "Booked for {when}. The calendar provider accepted the event and invitation request."
        )
    } else {
        format!("Appointment request saved for {when}. Calendar booking and invitation are pending; the team must confirm.")
    };
    json!({
        "ok": true, "confirmation": confirmation, "appointment_id": appt.id,
        "booking_status": if synced { "booked" } else { "pending_calendar" },
        "calendar_state": appt.calendar_state.unwrap_or("unconnected"),
        "invitation_state": appt.invitation_state.unwrap_or("pending"),
        "duplicate": duplicate,
    })
}
