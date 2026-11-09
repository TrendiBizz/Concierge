//! Google Calendar event sync decisions (port of `calendar_connection.sync_one`'s control flow). The HTTP calls are
//! behind [`Api`], so the exact request sequence and the resulting appointment state can be checked against Python.
use chrono::DateTime;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

pub fn event_id(tenant_id: &str, appointment_id: &str) -> String {
    Sha256::digest(format!("{tenant_id}:{appointment_id}").as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// Python `urllib.parse.quote(s, safe='')`.
pub fn quote(s: &str) -> String {
    s.bytes()
        .map(|b| {
            if b.is_ascii_alphanumeric() || b"_.-~".contains(&b) {
                (b as char).to_string()
            } else {
                format!("%{b:02X}")
            }
        })
        .collect()
}

pub struct Resp {
    pub status: u16,
    /// `None` when the body is not JSON (Python's `.json()` raises `ValueError`).
    pub body: Option<Value>,
}

/// One call to the provider. `Err` is an `httpx.HTTPError` (timeout, connection failure).
pub trait Api {
    fn request(
        &mut self,
        method: &str,
        path: &str,
        params: Option<Value>,
        json: Option<Value>,
    ) -> Result<Resp, ()>;
}

pub struct Appt<'a> {
    pub id: &'a str,
    pub tenant_id: &'a str,
    pub status: &'a str,
    pub calendar_sync_requested: bool,
    pub calendar_state: &'a str,
    pub email: &'a str,
    pub consent_contact: bool,
    pub name: &'a str,
    pub notes: &'a str,
    pub business_name: &'a str,
    pub timezone: &'a str,
    /// Unix seconds, UTC (whole seconds).
    pub starts_at: i64,
    pub ends_at: i64,
}

#[derive(Debug, PartialEq, Eq)]
pub struct Outcome {
    pub state: &'static str,
    pub error: &'static str,
    pub remote_id: Option<String>,
    pub invitation_state: Option<&'static str>,
}

fn out(state: &'static str, error: &'static str) -> Option<Outcome> {
    Some(Outcome {
        state,
        error,
        remote_id: None,
        invitation_state: None,
    })
}
fn retry() -> Option<Outcome> {
    out("retry", "Calendar synchronization pending; retry scheduled")
}

/// Everything that makes the Python `except (CalendarUnavailable, HTTPError, ValueError, KeyError)` fire.
struct Retry;

fn parse_time(v: &Value) -> Result<i64, Retry> {
    let s = v.as_str().ok_or(Retry)?;
    DateTime::parse_from_rfc3339(s)
        .map(|d| d.timestamp())
        .map_err(|_| Retry)
}

fn iso(secs: i64) -> String {
    crate::events::iso_utc(secs, 0)
}

/// `busy()`: the events already on the owner's calendar in the window (`Err` = unavailable / unparseable).
fn busy(
    api: &mut dyn Api,
    calendar_id: &str,
    start: i64,
    end: i64,
) -> Result<Vec<(i64, i64)>, Retry> {
    let r = api
        .request(
            "POST",
            "/freeBusy",
            None,
            Some(
                json!({"timeMin": iso(start), "timeMax": iso(end), "items": [{"id": calendar_id}]}),
            ),
        )
        .map_err(|_| Retry)?;
    if r.status != 200 {
        return Err(Retry);
    }
    let body = r.body.ok_or(Retry)?;
    let cal = body.get("calendars").and_then(|c| c.get(calendar_id));
    let Some(cal) = cal.filter(|c| !c.is_null()) else {
        return Err(Retry);
    };
    if crate::pyval::truthy(cal.get("errors")) {
        return Err(Retry);
    }
    let mut out = Vec::new();
    for x in cal
        .get("busy")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
    {
        out.push((
            parse_time(x.get("start").ok_or(Retry)?)?,
            parse_time(x.get("end").ok_or(Retry)?)?,
        ));
    }
    Ok(out)
}

/// `sync_one` for one appointment. `None` means Python returned without writing anything.
pub fn sync_one(a: &Appt, calendar_id: Option<&str>, api: &mut dyn Api) -> Option<Outcome> {
    if !a.calendar_sync_requested || (a.calendar_state == "synced" && a.status == "booked") {
        return None;
    }
    let Some(calendar_id) = calendar_id else {
        return out("unconnected", "Connect the owner calendar");
    };
    if a.status == "booked" && (a.email.is_empty() || !a.consent_contact) {
        return out("needs_contact", "Confirm invitation email and permission");
    }
    let remote_id = event_id(a.tenant_id, a.id);
    let path = format!("/calendars/{}/events", quote(calendar_id));
    match run(a, calendar_id, &remote_id, &path, api) {
        Ok(o) => o,
        Err(Retry) => retry(),
    }
}

fn run(
    a: &Appt,
    calendar_id: &str,
    remote_id: &str,
    path: &str,
    api: &mut dyn Api,
) -> Result<Option<Outcome>, Retry> {
    let item = format!("{path}/{remote_id}");
    if a.status == "cancelled" || a.status == "no_show" {
        let r = api
            .request("DELETE", &item, Some(json!({"sendUpdates": "all"})), None)
            .map_err(|_| Retry)?;
        if ![200, 204, 404, 410].contains(&r.status) {
            return Err(Retry);
        }
        return Ok(out("cancelled", ""));
    }
    let mut existing = api.request("GET", &item, None, None).map_err(|_| Retry)?;
    if existing.status == 404 {
        if !busy(api, calendar_id, a.starts_at, a.ends_at)?.is_empty() {
            return Ok(out("conflict", "Owner calendar has a conflicting event"));
        }
        let payload = json!({
            "id": remote_id, "summary": format!("{} — {}", a.business_name, a.name), "description": a.notes,
            "start": {"dateTime": iso(a.starts_at), "timeZone": a.timezone}, "end": {"dateTime": iso(a.ends_at), "timeZone": a.timezone},
            "attendees": [{"email": a.email}],
            "extendedProperties": {"private": {"concierge_appointment": a.id, "concierge_tenant": a.tenant_id}},
        });
        existing = api
            .request(
                "POST",
                path,
                Some(json!({"sendUpdates": "all"})),
                Some(payload),
            )
            .map_err(|_| Retry)?;
        if existing.status == 409 {
            existing = api.request("GET", &item, None, None).map_err(|_| Retry)?;
        }
    }
    if ![200, 201].contains(&existing.status) {
        return Err(Retry);
    }
    let result = existing.body.ok_or(Retry)?;
    let attendees = result
        .get("attendees")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let emails: Vec<String> = attendees
        .iter()
        .map(|x| {
            x.get("email")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_lowercase()
        })
        .collect();
    let private = result
        .get("extendedProperties")
        .and_then(|e| e.get("private"));
    let prop = |k: &str| private.and_then(|p| p.get(k)).and_then(Value::as_str);
    if result.get("status").and_then(Value::as_str) == Some("cancelled")
        || !emails.contains(&a.email.to_lowercase())
        || prop("concierge_appointment") != Some(a.id)
        || prop("concierge_tenant") != Some(a.tenant_id)
    {
        return Err(Retry);
    }
    for (key, expected) in [("start", a.starts_at), ("end", a.ends_at)] {
        let actual = parse_time(
            result
                .get(key)
                .and_then(|k| k.get("dateTime"))
                .ok_or(Retry)?,
        )?;
        if actual != expected {
            return Err(Retry);
        }
    }
    Ok(Some(Outcome {
        state: "synced",
        error: "",
        remote_id: Some(remote_id.to_string()),
        invitation_state: Some("provider_requested"),
    }))
}
