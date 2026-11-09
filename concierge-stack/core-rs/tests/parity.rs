//! Every golden vector was produced by the live Python module; the Rust port must reproduce it exactly.
use concierge_core::{chunking, contact, guard, ical, unsub};
use serde::Deserialize;
use std::collections::BTreeSet;

#[derive(Deserialize)]
struct Vectors {
    chunk: Vec<Chunk>,
    guard: Vec<Guard>,
    contact: Vec<Contact>,
    unsub: Vec<Unsub>,
    unsub_tampered: Vec<Tampered>,
    ical: IcalCase,
    esc: Vec<Pair>,
    fold: Vec<Pair>,
    secret: String,
    base: String,
}
#[derive(Deserialize)]
struct Chunk { text: String, max: usize, overlap: usize, out: Vec<String> }
#[derive(Deserialize)]
struct Guard { reply: String, evidence: String, unknown: Vec<String> }
#[derive(Deserialize)]
struct Contact { v: String, cc: String, phone: Option<String>, key: String, email: bool }
#[derive(Deserialize)]
struct Unsub { tenant: String, contact: String, token: String, read: Option<Vec<String>>, url: String }
#[derive(Deserialize)]
struct Tampered { token: String, read: Option<Vec<String>> }
#[derive(Deserialize)]
struct Pair { #[serde(rename = "in")] input: String, out: String }
#[derive(Deserialize)]
struct IcalCase { tenant: String, now: i64, appointments: Vec<Appt>, out: String }
#[derive(Deserialize)]
struct Appt {
    id: serde_json::Value,
    name: Option<String>, phone: Option<String>, email: Option<String>, notes: Option<String>, status: Option<String>,
    starts_at: i64, ends_at: i64,
}

fn vectors() -> Vectors {
    let raw = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/parity/vectors.json")).expect("vectors.json");
    serde_json::from_str(&raw).expect("valid vectors")
}

#[test]
fn chunking_matches_python() {
    for (i, c) in vectors().chunk.iter().enumerate() {
        assert_eq!(chunking::chunk_text(&c.text, c.max, c.overlap), c.out, "chunk case {i} (max {}, overlap {})", c.max, c.overlap);
    }
}

#[test]
fn quote_guard_matches_python() {
    for (i, g) in vectors().guard.iter().enumerate() {
        let got: BTreeSet<String> = guard::unknown_amounts(&g.reply, &g.evidence).iter().map(|a| a.canonical()).collect();
        // Python printed amounts with Decimal 'f' formatting of the normalized value; compare numerically-canonical text.
        let want: BTreeSet<String> = g.unknown.iter().map(|s| canonical(s)).collect();
        assert_eq!(got, want, "guard case {i}: reply={:?} evidence={:?}", g.reply, g.evidence);
    }
}

fn canonical(s: &str) -> String {
    let (w, f) = s.split_once('.').unwrap_or((s, ""));
    let w = w.trim_start_matches('0');
    let w = if w.is_empty() { "0" } else { w };
    let f = f.trim_end_matches('0');
    if f.is_empty() { w.to_string() } else { format!("{w}.{f}") }
}

#[test]
fn contact_matches_python() {
    for c in vectors().contact {
        assert_eq!(contact::normalize_phone(&c.v, &c.cc), c.phone, "phone {:?} cc {}", c.v, c.cc);
        assert_eq!(contact::contact_key(&c.v, &c.cc), c.key, "key {:?} cc {}", c.v, c.cc);
        assert_eq!(contact::is_email(&c.v), c.email, "email {:?}", c.v);
    }
}

#[test]
fn unsubscribe_tokens_match_python() {
    let v = vectors();
    for u in &v.unsub {
        assert_eq!(unsub::make_token(&v.secret, &u.tenant, &u.contact).unwrap(), u.token);
        assert_eq!(unsub::url_for(&v.secret, &v.base, &u.tenant, &u.contact).unwrap(), u.url);
        let got = unsub::read_token(&v.secret, &u.token).map(|(a, b)| vec![a, b]);
        assert_eq!(got, u.read);
    }
    for t in &v.unsub_tampered {
        let got = unsub::read_token(&v.secret, &t.token).map(|(a, b)| vec![a, b]);
        assert_eq!(got, t.read, "token {:?}", t.token);
    }
    assert!(unsub::make_token("", "t", "c").is_err());
    assert!(unsub::read_token("", &v.unsub[0].token).is_none());
}

#[test]
fn ical_matches_python() {
    let v = vectors();
    for e in &v.esc { assert_eq!(ical::esc(&e.input), e.out); }
    for f in &v.fold { assert_eq!(ical::fold(&f.input), f.out); }
    let appts: Vec<ical::Appointment> = v.ical.appointments.iter().map(|a| ical::Appointment {
        id: match &a.id { serde_json::Value::String(s) => s.clone(), other => other.to_string() },
        name: a.name.clone(), phone: a.phone.clone(), email: a.email.clone(), notes: a.notes.clone(),
        status: a.status.clone(), starts_at: a.starts_at, ends_at: a.ends_at,
    }).collect();
    assert_eq!(ical::build(&v.ical.tenant, &appts, v.ical.now), v.ical.out);
}

#[test]
fn rate_limiter_sliding_window() {
    use std::time::{Duration, Instant};
    let mut r = concierge_core::rate_limit::RateLimiter::new(2, Duration::from_secs(10));
    let t0 = Instant::now();
    assert!(r.check("a", t0));
    assert!(r.check("a", t0 + Duration::from_secs(1)));
    assert!(!r.check("a", t0 + Duration::from_secs(2)));
    assert!(r.check("b", t0 + Duration::from_secs(2)));
    assert!(r.check("a", t0 + Duration::from_secs(10))); // first hit has aged out
}
