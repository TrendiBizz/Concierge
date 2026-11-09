//! Batch 5: automation plans and campaign rules, against the live Python (async functions run with a fixed clock).
use concierge_core::automation::{self as au, Enqueue};
use concierge_core::campaigns::{self as cp, FilterError, Render};
use serde::Deserialize;
use serde_json::Value;

#[derive(Deserialize)]
struct V {
    appt: Vec<ApptCase>,
    status: Vec<StatusCase>,
    lead: Vec<LeadCase>,
    templates: Vec<Tpl>,
    footers: Vec<Foot>,
    mask: Vec<Mask>,
    times: Vec<Times>,
    filters: Vec<Filt>,
    ready: Vec<Ready>,
    now: i64,
}
#[derive(Deserialize)]
struct TenantJ {
    name: String,
    timezone: String,
    sms_enabled: bool,
    review_url: Option<String>,
}
#[derive(Deserialize)]
struct ApptJ {
    id: String,
    name: String,
    phone: String,
    email: String,
    notes: String,
    consent_contact: bool,
    starts_at: i64,
}
#[derive(Deserialize, Debug, PartialEq)]
struct EnqJ {
    kind: String,
    channel: String,
    to: String,
    subject: String,
    body: String,
    send_at: i64,
    dedupe: String,
}
#[derive(Deserialize)]
struct Alert {
    subject: String,
    body: String,
    dedupe: String,
}
#[derive(Deserialize)]
struct ApptCase {
    tenant: TenantJ,
    appt: ApptJ,
    cc: String,
    alert: Alert,
    enqueues: Vec<EnqJ>,
}
#[derive(Deserialize)]
struct StatusCase {
    tenant: TenantJ,
    appt: ApptJ,
    cc: String,
    status: String,
    cancel: bool,
    enqueues: Vec<EnqJ>,
}
#[derive(Deserialize)]
struct LeadJ {
    id: String,
    name: Option<String>,
    email: Option<String>,
    phone: Option<String>,
    message: Option<String>,
    channel: Option<String>,
    page_url: Option<String>,
    score: Option<i64>,
    score_label: Option<String>,
    score_reasons: Vec<String>,
}
#[derive(Deserialize)]
struct LeadCase {
    business: String,
    lead: LeadJ,
    alert: Alert,
}
#[derive(Deserialize)]
struct Tpl {
    t: String,
    err: Option<String>,
    renders: Vec<Rn>,
}
#[derive(Deserialize)]
struct Rn {
    name: String,
    out: Option<String>,
    err: Option<String>,
}
#[derive(Deserialize)]
struct Foot {
    tenant: FootTenant,
    to: String,
    out: String,
}
#[derive(Deserialize)]
struct FootTenant {
    id: String,
    name: String,
    notify_email: Option<String>,
}
#[derive(Deserialize)]
struct Mask {
    #[serde(rename = "in")]
    input: String,
    out: String,
}
#[derive(Deserialize)]
struct Times {
    count: usize,
    per: i64,
    out: Vec<i64>,
}
#[derive(Deserialize)]
struct Filt {
    max: i64,
    raw: Value,
    out: Value,
}
#[derive(Deserialize)]
struct Ready {
    enabled: bool,
    ch: String,
    sms: bool,
    sender: bool,
    email_cfg: bool,
    unsub: bool,
    out: Vec<String>,
}

fn load() -> V {
    serde_json::from_str(
        &std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/parity/vectors5.json"))
            .unwrap(),
    )
    .unwrap()
}
fn tenant(t: &TenantJ) -> au::Tenant<'_> {
    au::Tenant {
        name: &t.name,
        timezone: t.timezone.parse().unwrap(),
        sms_enabled: t.sms_enabled,
        review_url: t.review_url.as_deref(),
    }
}
fn appt(a: &ApptJ) -> au::Appointment<'_> {
    au::Appointment {
        id: &a.id,
        name: &a.name,
        phone: &a.phone,
        email: &a.email,
        notes: &a.notes,
        consent_contact: a.consent_contact,
        starts_at: a.starts_at,
    }
}
fn eq(got: &[Enqueue], want: &[EnqJ], ctx: &str) {
    let got: Vec<EnqJ> = got
        .iter()
        .map(|e| EnqJ {
            kind: e.kind.clone(),
            channel: e.channel.to_string(),
            to: e.to_addr.clone(),
            subject: e.subject.clone(),
            body: e.body.clone(),
            send_at: e.send_at,
            dedupe: e.dedupe_key.clone(),
        })
        .collect();
    assert_eq!(got, want, "{ctx}");
}

#[test]
fn appointment_booked_plan_matches_python() {
    let v = load();
    for (i, c) in v.appt.iter().enumerate() {
        let p = au::appointment_booked(&tenant(&c.tenant), &appt(&c.appt), v.now, &c.cc);
        assert_eq!(
            (
                p.owner_subject.as_str(),
                p.owner_body.as_str(),
                p.owner_dedupe.as_str()
            ),
            (
                c.alert.subject.as_str(),
                c.alert.body.as_str(),
                c.alert.dedupe.as_str()
            ),
            "alert {i}"
        );
        eq(&p.enqueues, &c.enqueues, &format!("booked case {i}"));
    }
}

#[test]
fn appointment_status_plan_matches_python() {
    let v = load();
    for (i, c) in v.status.iter().enumerate() {
        let p = au::appointment_status(&tenant(&c.tenant), &appt(&c.appt), &c.status, v.now, &c.cc);
        assert_eq!(p.cancel_pending, c.cancel, "status case {i} {}", c.status);
        eq(
            &p.enqueues,
            &c.enqueues,
            &format!("status case {i} {}", c.status),
        );
    }
}

#[test]
fn lead_owner_alert_matches_python() {
    for (i, c) in load().lead.iter().enumerate() {
        let l = &c.lead;
        let input = au::LeadAlertInput {
            id: &l.id,
            name: l.name.as_deref(),
            phone: l.phone.as_deref(),
            email: l.email.as_deref(),
            channel: l.channel.as_deref(),
            page_url: l.page_url.as_deref(),
            message: l.message.as_deref(),
            score: l.score,
            score_label: l.score_label.as_deref(),
            score_reasons: &l.score_reasons,
        };
        let (s, b, d) = au::lead_owner_alert(&c.business, &input);
        assert_eq!(
            (s, b, d),
            (
                c.alert.subject.clone(),
                c.alert.body.clone(),
                c.alert.dedupe.clone()
            ),
            "lead alert {i}"
        );
    }
}

#[test]
fn template_validation_and_render_match_python() {
    let (mut rendered, mut unsupported) = (0, 0);
    for c in load().templates {
        assert_eq!(
            cp::validate_template(&c.t).err(),
            c.err,
            "validate {:?}",
            c.t
        );
        for r in &c.renders {
            match (cp::render(&c.t, &r.name, "Trendi; Bizz"), &r.out) {
                (Render::Text(got), Some(want)) => {
                    assert_eq!(&got, want, "render {:?} / {:?}", c.t, r.name);
                    rendered += 1;
                }
                // "Unsupported" makes no claim about the outcome (callers refuse or defer to Python), so it is safe
                // against either a Python result or a Python error; it is counted so it cannot hide.
                (Render::Unsupported, _) => unsupported += 1,
                (Render::Error, None) => assert!(r.err.is_some()),
                (got, want) => panic!(
                    "render {:?}/{:?}: rust {got:?} python {want:?} {:?}",
                    c.t, r.name, r.err
                ),
            }
        }
    }
    assert!(
        rendered > 100,
        "rendered only {rendered} ({unsupported} unsupported)"
    );
    println!("rendered {rendered}, unsupported conversion/spec forms {unsupported}");
}

#[test]
fn footer_mask_and_send_times_match_python() {
    let v = load();
    for c in &v.footers {
        let got = cp::email_footer(
            &c.tenant.name,
            c.tenant.notify_email.as_deref(),
            &c.tenant.id,
            &c.to,
            "parity-secret-not-real",
            "https://example.test/",
        )
        .unwrap();
        assert_eq!(got, c.out);
    }
    for c in &v.mask {
        assert_eq!(cp::mask(&c.input), c.out, "mask {:?}", c.input);
    }
    for c in &v.times {
        assert_eq!(
            cp::send_times(v.now * 1_000_000, c.count, c.per),
            c.out,
            "times count {} per {}",
            c.count,
            c.per
        );
    }
}

#[test]
fn filters_and_readiness_match_python() {
    let v = load();
    for c in &v.filters {
        let got = match cp::clean_filters(&c.raw, c.max) {
            Ok(f) => {
                serde_json::json!({"ok": {"statuses": f.statuses, "older_than_days": f.older_than_days, "min_score": f.min_score, "max_recipients": f.max_recipients}})
            }
            Err(FilterError::Campaign(m)) => serde_json::json!({"err": "CampaignError", "msg": m}),
            Err(FilterError::ValueError) => serde_json::json!({"err": "ValueError"}),
            Err(FilterError::TypeError) => serde_json::json!({"err": "TypeError"}),
        };
        assert_eq!(got, c.out, "filters {:?} max {}", c.raw, c.max);
    }
    for c in &v.ready {
        let got: Vec<String> =
            cp::readiness(c.enabled, &c.ch, c.sms, c.sender, c.email_cfg, c.unsub)
                .into_iter()
                .map(String::from)
                .collect();
        assert_eq!(got, c.out);
    }
}
