//! Wording of the owner's response-time alert (port of `sla._alert_text`).
use std::fmt::Display;

pub struct Tenant<'a> {
    pub name: &'a str,
    pub sla_minutes: i64,
}

pub struct Lead<'a> {
    pub name: Option<&'a str>,
    pub phone: Option<&'a str>,
    pub email: Option<&'a str>,
    pub channel: Option<&'a str>,
    pub message: Option<&'a str>,
    pub score_label: &'a str,
    pub score: i64,
    pub minutes_waiting: i64,
}

/// Python formats a missing value as "None".
fn py(v: Option<&str>) -> &str {
    v.unwrap_or("None")
}
fn truthy<'a>(v: Option<&'a str>) -> Option<&'a str> {
    v.filter(|s| !s.is_empty())
}

pub fn alert_text(tenant: &Tenant, lead: &Lead) -> (String, String) {
    let who = truthy(lead.name)
        .or(truthy(lead.phone))
        .or(truthy(lead.email))
        .unwrap_or("a visitor");
    let subject = format!(
        "[ACTION] {} lead waiting {} min: {who}",
        lead.score_label.to_uppercase(),
        lead.minutes_waiting
    );
    let body = format!(
        "A {} lead (score {}/100) for {} has had no reply for {} minutes (your target is {}).\n\nName: {}\nPhone: {}\nEmail: {}\nVia: {}\n\n{}\n\nOpen the dashboard and mark the lead as contacted once you have replied, and this stops.\n",
        lead.score_label, lead.score, tenant.name, lead.minutes_waiting, tenant.sla_minutes,
        py(lead.name), py(lead.phone), py(lead.email), py(lead.channel), py(lead.message),
    );
    (subject, body)
}

#[allow(dead_code)]
fn _assert_display<T: Display>() {}
