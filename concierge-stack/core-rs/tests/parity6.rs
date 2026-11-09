//! Batch 6: owner SMS shortening, recording validation, and the Google Calendar sync state machine (live `sync_one`).
use chrono::DateTime;
use concierge_core::calendar::{self, Api, Appt, Resp};
use concierge_core::{owner_notifications, voice_records};
use serde::Deserialize;
use serde_json::Value;

#[derive(Deserialize)]
struct V {
    sms: Vec<Sms>,
    digest: Vec<Dg>,
    audio: Vec<Audio>,
    calendar: Vec<Cal>,
}
#[derive(Deserialize)]
struct Sms {
    subject: String,
    body: String,
    base: String,
    out: String,
}
#[derive(Deserialize)]
struct Dg {
    #[serde(rename = "in")]
    input: String,
    out: String,
}
#[derive(Deserialize)]
struct Audio {
    name: String,
    ct: String,
    body_hex: String,
    out: Value,
}
#[derive(Deserialize)]
struct Cal {
    appt: AppJ,
    cal: Option<String>,
    log: Vec<Entry>,
    outcome: Option<Out>,
}
#[derive(Deserialize)]
struct AppJ {
    id: String,
    tenant_id: String,
    status: String,
    calendar_sync_requested: bool,
    calendar_state: String,
    email: String,
    consent_contact: bool,
    name: String,
    notes: String,
    business_name: String,
    timezone: String,
    starts_at: i64,
    ends_at: i64,
}
#[derive(Deserialize, Clone)]
struct Entry {
    method: String,
    path: String,
    params: Option<Value>,
    json: Option<Value>,
    resp: Spec,
}
#[derive(Deserialize, Clone)]
struct Spec {
    status: Option<u16>,
    body: Option<Value>,
    err: bool,
}
#[derive(Deserialize)]
struct Out {
    state: String,
    error: String,
    remote_id: Option<String>,
    invitation: Option<String>,
}

fn load() -> V {
    serde_json::from_str(
        &std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/parity/vectors6.json"))
            .unwrap(),
    )
    .unwrap()
}

fn unhex(s: &str) -> Vec<u8> {
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap())
        .collect()
}

#[test]
fn owner_sms_body_matches_python() {
    for (i, c) in load().sms.iter().enumerate() {
        assert_eq!(
            owner_notifications::sms_body(&c.subject, &c.body, &c.base),
            c.out,
            "sms case {i} (body {} chars)",
            c.body.chars().count()
        );
    }
}

#[test]
fn digests_and_recording_validation_match_python() {
    let v = load();
    for c in &v.digest {
        assert_eq!(voice_records::digest(&c.input), c.out);
    }
    for c in &v.audio {
        let got = match voice_records::audio_type(&c.ct, &unhex(&c.body_hex)) {
            Ok(m) => serde_json::json!({"ok": m}),
            Err((s, m)) => serde_json::json!({"err": [s, m]}),
        };
        assert_eq!(got, c.out, "audio {} ct {:?}", c.name, c.ct);
    }
}

/// Replays the provider's recorded answers and asserts that every request Rust makes is the one Python made.
struct Replay {
    log: Vec<Entry>,
    next: usize,
}
impl Api for Replay {
    fn request(
        &mut self,
        method: &str,
        path: &str,
        params: Option<Value>,
        json: Option<Value>,
    ) -> Result<Resp, ()> {
        let e = self
            .log
            .get(self.next)
            .unwrap_or_else(|| panic!("Rust made an extra request: {method} {path}"))
            .clone();
        self.next += 1;
        assert_eq!(
            (method, path),
            (e.method.as_str(), e.path.as_str()),
            "request #{} differs",
            self.next
        );
        assert_eq!(params, e.params, "params of {method} {path}");
        assert_eq!(json, e.json, "json body of {method} {path}");
        if e.resp.err {
            return Err(());
        }
        Ok(Resp {
            status: e.resp.status.unwrap(),
            body: match e.resp.body {
                Some(Value::String(ref s)) if s == "INVALID" => None,
                other => Some(other.unwrap_or(Value::Null)),
            },
        })
    }
}

#[test]
fn calendar_sync_matches_python_requests_and_outcome() {
    for (i, c) in load().calendar.iter().enumerate() {
        let a = Appt {
            id: &c.appt.id,
            tenant_id: &c.appt.tenant_id,
            status: &c.appt.status,
            calendar_sync_requested: c.appt.calendar_sync_requested,
            calendar_state: &c.appt.calendar_state,
            email: &c.appt.email,
            consent_contact: c.appt.consent_contact,
            name: &c.appt.name,
            notes: &c.appt.notes,
            business_name: &c.appt.business_name,
            timezone: &c.appt.timezone,
            starts_at: c.appt.starts_at,
            ends_at: c.appt.ends_at,
        };
        let mut api = Replay {
            log: c.log.clone(),
            next: 0,
        };
        let got = calendar::sync_one(&a, c.cal.as_deref(), &mut api);
        assert_eq!(
            api.next,
            c.log.len(),
            "case {i}: Python made {} requests, Rust {}",
            c.log.len(),
            api.next
        );
        match (&got, &c.outcome) {
            (None, None) => {}
            (Some(g), Some(w)) => assert_eq!(
                (g.state, g.error, g.remote_id.as_deref(), g.invitation_state),
                (
                    w.state.as_str(),
                    w.error.as_str(),
                    w.remote_id.as_deref(),
                    w.invitation.as_deref()
                ),
                "case {i} outcome"
            ),
            _ => panic!(
                "case {i}: rust {got:?} python {:?}",
                c.outcome.as_ref().map(|o| &o.state)
            ),
        }
    }
    let _ = DateTime::from_timestamp(0, 0);
}

#[test]
fn event_ids_and_quoting() {
    // sha256("t-1:appt-1"), checked against Python in the calendar vectors; quote() mirrors urllib's safe=''.
    assert_eq!(calendar::quote("a b/c@é.co"), "a%20b%2Fc%40%C3%A9.co");
    assert_eq!(calendar::quote("AZaz09_.-~"), "AZaz09_.-~");
    assert_eq!(calendar::event_id("t-1", "appt-1").len(), 64);
}
