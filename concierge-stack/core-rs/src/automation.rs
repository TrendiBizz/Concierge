//! What follows a captured lead or a booked appointment (port of the decision logic in `automation.py`):
//! owner alert wording and the confirmation / reminder / review messages to queue.
use crate::campaigns::first_name;
use crate::contact::{is_email, normalize_phone};
use crate::schedule::fmt_local;
use chrono::DateTime;
use chrono_tz::Tz;

const HOUR: i64 = 3600;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Enqueue {
    pub kind: String,
    pub channel: &'static str,
    pub to_addr: String,
    pub subject: String,
    pub body: String,
    /// Unix seconds.
    pub send_at: i64,
    pub dedupe_key: String,
}

pub struct Tenant<'a> {
    pub name: &'a str,
    pub timezone: Tz,
    pub sms_enabled: bool,
    pub review_url: Option<&'a str>,
}

pub struct Appointment<'a> {
    pub id: &'a str,
    pub name: &'a str,
    pub phone: &'a str,
    pub email: &'a str,
    pub notes: &'a str,
    pub consent_contact: bool,
    pub starts_at: i64,
}

/// Python prints a missing value as `None`.
fn py(v: Option<&str>) -> &str {
    v.unwrap_or("None")
}

pub struct LeadAlertInput<'a> {
    pub id: &'a str,
    pub name: Option<&'a str>,
    pub phone: Option<&'a str>,
    pub email: Option<&'a str>,
    pub channel: Option<&'a str>,
    pub page_url: Option<&'a str>,
    pub message: Option<&'a str>,
    pub score: Option<i64>,
    pub score_label: Option<&'a str>,
    pub score_reasons: &'a [String],
}

fn truthy(v: Option<&str>) -> Option<&str> {
    v.filter(|s| !s.is_empty())
}

fn score_tag(label: Option<&str>) -> String {
    match label {
        Some(l @ ("hot" | "warm")) => format!("[{}] ", l.to_uppercase()),
        _ => String::new(),
    }
}

fn score_lines(l: &LeadAlertInput) -> String {
    let Some(score) = l.score else {
        return String::new();
    };
    let why = if l.score_reasons.is_empty() {
        "-".to_string()
    } else {
        l.score_reasons.join("; ")
    };
    format!("Score: {score}/100 ({})\nWhy: {why}\n\n", py(l.score_label))
}

/// `(subject, body, dedupe_key)` of the owner's new-lead alert.
pub fn lead_owner_alert(business: &str, l: &LeadAlertInput) -> (String, String, String) {
    let contact = truthy(l.phone).or(truthy(l.email)).unwrap_or("-");
    let subject = format!(
        "{}New lead for {business}: {}",
        score_tag(l.score_label),
        truthy(l.name).unwrap_or(contact)
    );
    let body = format!(
        "{}Name: {}\nPhone: {}\nEmail: {}\nChannel: {}\nPage: {}\n\n{}\n",
        score_lines(l),
        py(l.name),
        py(l.phone),
        py(l.email),
        py(l.channel),
        truthy(l.page_url).unwrap_or("-"),
        py(l.message)
    );
    (subject, body, format!("lead:{}:owner", l.id))
}

fn sms_target(t: &Tenant, phone: &str, consent: bool, cc: &str) -> Option<String> {
    if !(t.sms_enabled && consent && !phone.is_empty()) {
        return None;
    }
    normalize_phone(phone, cc)
}

pub struct BookedPlan {
    pub owner_subject: String,
    pub owner_body: String,
    pub owner_dedupe: String,
    pub enqueues: Vec<Enqueue>,
}

fn when(t: &Tenant, secs: i64) -> String {
    fmt_local(
        t.timezone,
        DateTime::from_timestamp(secs, 0).expect("in range"),
    )
}

/// `on_appointment_booked`: the owner alert plus the confirmation and two reminders.
pub fn appointment_booked(t: &Tenant, a: &Appointment, now: i64, cc: &str) -> BookedPlan {
    let when_text = when(t, a.starts_at);
    let owner_subject = format!("New appointment for {}: {} - {when_text}", t.name, a.name);
    let owner_body = format!(
        "{} booked {when_text}.\nPhone: {}\nEmail: {}\nNotes: {}\n",
        a.name, a.phone, a.email, a.notes
    );
    let sms_to = sms_target(t, a.phone, a.consent_contact, cc);
    let email_to = (a.consent_contact && is_email(a.email)).then(|| a.email.to_string());
    let first = first_name(a.name);
    let plan = [
        (
            "confirm",
            now,
            format!("Hi {first}, you're booked with {} for {when_text}.", t.name),
        ),
        (
            "rem24",
            a.starts_at - 24 * HOUR,
            format!(
                "Reminder: your appointment with {} is tomorrow, {when_text}.",
                t.name
            ),
        ),
        (
            "rem2",
            a.starts_at - 2 * HOUR,
            format!(
                "Reminder: your appointment with {} is today, {when_text}.",
                t.name
            ),
        ),
    ];
    let mut enqueues = Vec::new();
    for (tag, send_at, text) in plan {
        if tag != "confirm" && send_at <= now {
            continue;
        }
        if let Some(to) = &sms_to {
            enqueues.push(Enqueue {
                kind: format!("appt_{tag}"),
                channel: "sms",
                to_addr: to.clone(),
                subject: String::new(),
                body: format!("{text} Reply STOP to opt out."),
                send_at,
                dedupe_key: format!("appt:{}:{tag}:sms", a.id),
            });
        }
        if let Some(to) = &email_to {
            enqueues.push(Enqueue {
                kind: format!("appt_{tag}"),
                channel: "email",
                to_addr: to.clone(),
                subject: format!("Your appointment with {}", t.name),
                body: text.clone(),
                send_at,
                dedupe_key: format!("appt:{}:{tag}:email", a.id),
            });
        }
    }
    BookedPlan {
        owner_subject,
        owner_body,
        owner_dedupe: format!("appt:{}:owner", a.id),
        enqueues,
    }
}

pub struct StatusPlan {
    pub cancel_pending: bool,
    pub enqueues: Vec<Enqueue>,
}

/// `on_appointment_status`: cancel queued messages, or ask for a review an hour after completion.
pub fn appointment_status(
    t: &Tenant,
    a: &Appointment,
    status: &str,
    now: i64,
    cc: &str,
) -> StatusPlan {
    if status == "cancelled" || status == "no_show" {
        return StatusPlan {
            cancel_pending: true,
            enqueues: Vec::new(),
        };
    }
    let mut enqueues = Vec::new();
    if let (true, Some(url)) = (status == "completed", truthy(t.review_url)) {
        let send_at = now + HOUR;
        let first = first_name(a.name);
        let text = format!("Thanks for visiting {}, {first}! If we did a good job, would you leave a quick review? {url}", t.name);
        if let Some(to) = sms_target(t, a.phone, a.consent_contact, cc) {
            enqueues.push(Enqueue {
                kind: "review_request".into(),
                channel: "sms",
                to_addr: to,
                subject: String::new(),
                body: format!("{text} Reply STOP to opt out."),
                send_at,
                dedupe_key: format!("appt:{}:review:sms", a.id),
            });
        }
        if is_email(a.email) {
            enqueues.push(Enqueue {
                kind: "review_request".into(),
                channel: "email",
                to_addr: a.email.to_string(),
                subject: format!("How was your visit to {}?", t.name),
                body: text,
                send_at,
                dedupe_key: format!("appt:{}:review:email", a.id),
            });
        }
    }
    StatusPlan {
        cancel_pending: false,
        enqueues,
    }
}
