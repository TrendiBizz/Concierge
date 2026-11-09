//! Batch 2: scoring, SLA alert text, sending window and booking slots, against vectors from the live Python.
use chrono::{DateTime, NaiveDate, Utc};
use chrono_tz::Tz;
use concierge_core::{schedule, scoring, sla};
use serde::Deserialize;
use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Deserialize)]
struct V {
    score: Vec<ScoreCase>,
    overrides: Vec<OverrideCase>,
    weights_for: Vec<WeightsForCase>,
    describe: Vec<Describe>,
    labels: Vec<LabelCase>,
    sla: Vec<SlaCase>,
    nas: Vec<NasCase>,
    slots: Vec<SlotCase>,
}
#[derive(Deserialize)]
struct ScoreCase {
    lead: LeadJ,
    turns: i64,
    booked: bool,
    weights: Option<BTreeMap<String, i64>>,
    out: Out,
}
#[derive(Deserialize)]
struct LeadJ {
    message: Option<String>,
    phone: Option<String>,
    email: Option<String>,
    name: Option<String>,
    consent_contact: Option<bool>,
    channel: Option<String>,
    page_url: Option<String>,
}
#[derive(Deserialize)]
struct Out {
    score: i64,
    label: String,
    reasons: Vec<String>,
}
#[derive(Deserialize)]
struct OverrideCase {
    raw: Value,
    out: Value,
}
#[derive(Deserialize)]
struct WeightsForCase {
    scoring: Value,
    out: BTreeMap<String, i64>,
}
#[derive(Deserialize)]
struct Describe {
    key: String,
    label: String,
    kind: String,
    default: i64,
    value: i64,
}
#[derive(Deserialize)]
struct LabelCase {
    score: i64,
    hot: i64,
    warm: i64,
    out: String,
}
#[derive(Deserialize)]
struct SlaCase {
    tenant: SlaTenant,
    lead: SlaLead,
    subject: String,
    body: String,
}
#[derive(Deserialize)]
struct SlaTenant {
    name: String,
    sla_minutes: i64,
}
#[derive(Deserialize)]
struct SlaLead {
    name: Option<String>,
    phone: Option<String>,
    email: Option<String>,
    channel: Option<String>,
    message: Option<String>,
    score_label: String,
    score: i64,
    minutes_waiting: i64,
}
#[derive(Deserialize)]
struct NasCase {
    tz: String,
    when: i64,
    start: u32,
    end: u32,
    out: i64,
}
#[derive(Deserialize)]
struct SlotCase {
    tenant: SlotTenant,
    day: String,
    now: i64,
    booked: Vec<[i64; 2]>,
    out: Vec<i64>,
}
#[derive(Deserialize)]
struct SlotTenant {
    timezone: String,
    slot_minutes: i64,
    min_notice_hours: i64,
    business_hours: BTreeMap<String, Vec<(String, String)>>,
}

fn load() -> V {
    let raw = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/parity/vectors2.json"))
        .expect("vectors2.json");
    serde_json::from_str(&raw).expect("valid vectors2")
}
fn ts(n: i64) -> DateTime<Utc> {
    DateTime::from_timestamp(n, 0).unwrap()
}

#[test]
fn scoring_matches_python() {
    for (i, c) in load().score.iter().enumerate() {
        let lead = scoring::Lead {
            message: c.lead.message.clone(),
            phone: c.lead.phone.clone(),
            email: c.lead.email.clone(),
            name: c.lead.name.clone(),
            consent_contact: c.lead.consent_contact.unwrap_or(false),
            channel: c.lead.channel.clone(),
            page_url: c.lead.page_url.clone(),
        };
        let got = scoring::assess(&lead, c.turns, c.booked, c.weights.as_ref());
        assert_eq!(
            (got.score, got.label, &got.reasons),
            (c.out.score, c.out.label.as_str(), &c.out.reasons),
            "score case {i}: {:?}",
            c.lead.message
        );
    }
}

#[test]
fn override_validation_matches_python() {
    for c in load().overrides {
        let got = match scoring::validate_overrides(&c.raw) {
            Ok(v) => {
                serde_json::json!({ "ok": v.into_iter().map(|(k, n)| (k, Value::from(n))).collect::<serde_json::Map<String, Value>>() })
            }
            Err(e) => serde_json::json!({ "err": e }),
        };
        assert_eq!(got, c.out, "overrides {:?}", c.raw);
    }
}

#[test]
fn weights_labels_and_describe_match_python() {
    let v = load();
    for c in &v.weights_for {
        assert_eq!(
            scoring::weights_for(Some(&c.scoring)),
            c.out,
            "weights_for {:?}",
            c.scoring
        );
    }
    for c in &v.labels {
        assert_eq!(scoring::label_for(c.score, c.hot, c.warm), c.out);
    }
    assert_eq!(v.describe.len(), scoring::WEIGHTS.len());
    for (d, w) in v.describe.iter().zip(scoring::WEIGHTS) {
        assert_eq!(
            (
                d.key.as_str(),
                d.default,
                d.label.as_str(),
                d.kind.as_str(),
                d.value
            ),
            (w.0, w.1, w.2, w.3.name(), w.1)
        );
    }
}

#[test]
fn sla_alert_text_matches_python() {
    for (i, c) in load().sla.iter().enumerate() {
        let l = &c.lead;
        let got = sla::alert_text(
            &sla::Tenant {
                name: &c.tenant.name,
                sla_minutes: c.tenant.sla_minutes,
            },
            &sla::Lead {
                name: l.name.as_deref(),
                phone: l.phone.as_deref(),
                email: l.email.as_deref(),
                channel: l.channel.as_deref(),
                message: l.message.as_deref(),
                score_label: &l.score_label,
                score: l.score,
                minutes_waiting: l.minutes_waiting,
            },
        );
        assert_eq!(got, (c.subject.clone(), c.body.clone()), "sla case {i}");
    }
}

#[test]
fn next_allowed_send_matches_python_including_dst() {
    for (i, c) in load().nas.iter().enumerate() {
        let tz: Tz = c.tz.parse().unwrap();
        assert_eq!(
            schedule::next_allowed_send(tz, ts(c.when), c.start, c.end),
            ts(c.out),
            "nas case {i}: {} when={} {}-{}",
            c.tz,
            c.when,
            c.start,
            c.end
        );
    }
}

#[test]
fn day_slots_match_python_including_dst() {
    for (i, c) in load().slots.iter().enumerate() {
        let tenant = schedule::BookingTenant {
            timezone: c.tenant.timezone.parse().unwrap(),
            slot_minutes: c.tenant.slot_minutes,
            min_notice_hours: c.tenant.min_notice_hours,
            business_hours: c.tenant.business_hours.clone(),
        };
        let day = NaiveDate::parse_from_str(&c.day, "%Y-%m-%d").unwrap();
        let booked: Vec<_> = c.booked.iter().map(|b| (ts(b[0]), ts(b[1]))).collect();
        let got: Vec<i64> = schedule::day_slots(&tenant, day, ts(c.now), &booked)
            .unwrap()
            .iter()
            .map(|d| d.timestamp())
            .collect();
        assert_eq!(
            got, c.out,
            "slot case {i}: {} {} step {}",
            c.tenant.timezone, c.day, c.tenant.slot_minutes
        );
    }
}
