//! Compatibility port of `api/app/revenue.py`. Reporting semantics are preserved,
//! including the created-at cohort and the existing zero-baseline convention.
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::collections::BTreeMap;

pub const CHANNELS: [&str; 4] = ["phone", "email", "sms", "chat"];
pub const NOTE: &str = "Value is what the customer accepted, not what you banked; confirmed money is reported separately. Enquiries are counted when they were first captured, by channel.";

#[derive(Default, Deserialize, Serialize)]
#[serde(default)]
pub struct Period {
    pub enquiries: i64,
    pub by_channel: BTreeMap<String, i64>,
    pub quotes_sent: i64,
    pub quotes_accepted: i64,
    pub accepted_cents: i128,
    pub paid_cents: i128,
    pub outstanding_cents: i128,
    pub currency: String,
}

pub fn clamp_days(days: i128) -> i64 {
    if days == 0 {
        30
    } else {
        days.clamp(1, 365) as i64
    }
}

pub fn percent_change(current: i64, previous: i64) -> Option<i64> {
    if previous <= 0 {
        return (current > 0).then_some(100);
    }
    Some(
        (((i128::from(current) - i128::from(previous)) as f64 / previous as f64) * 100.0)
            .round_ties_even() as i64,
    )
}

pub fn per_enquiry(cents: i64, enquiries: i64) -> i64 {
    if enquiries <= 0 {
        0
    } else {
        (cents as f64 / enquiries as f64).round_ties_even() as i64
    }
}

pub fn convert_rate(numerator: i64, denominator: i64) -> f64 {
    if denominator <= 0 {
        return 0.0;
    }
    // Fixed decimal formatting rounds the binary float itself, as Python's
    // round(x, 1) does; multiplying by ten first loses half-way information.
    format!("{:.1}", numerator as f64 / denominator as f64 * 100.0)
        .parse()
        .unwrap()
}

fn money(cents: i128) -> f64 {
    format!("{:.2}", cents as f64 / 100.0).parse().unwrap()
}

pub fn build(current: &Period, previous: &Period) -> Value {
    let mut channels = Map::new();
    for channel in CHANNELS {
        let count = current.by_channel.get(channel).copied().unwrap_or(0);
        let prev = previous.by_channel.get(channel).copied().unwrap_or(0);
        channels.insert(channel.into(), json!({"enquiries": count, "previous": prev, "change_percent": percent_change(count, prev)}));
    }
    json!({
        "enquiries": current.enquiries,
        "enquiries_previous": previous.enquiries,
        "enquiries_change_percent": percent_change(current.enquiries, previous.enquiries),
        "by_channel": channels,
        "quotes_sent": current.quotes_sent,
        "quotes_accepted": current.quotes_accepted,
        "quotes_sent_previous": previous.quotes_sent,
        "quotes_accepted_previous": previous.quotes_accepted,
        "accept_rate_percent": convert_rate(current.quotes_accepted, current.quotes_sent),
        "accepted_cents": current.accepted_cents,
        "accepted_value": money(current.accepted_cents),
        "accepted_previous_value": money(previous.accepted_cents),
        "accepted_change_percent": wide_percent_change(current.accepted_cents, previous.accepted_cents),
        "paid_cents": current.paid_cents,
        "paid_value": money(current.paid_cents),
        "outstanding_cents": current.outstanding_cents,
        "outstanding_value": money(current.outstanding_cents),
        "value_per_enquiry": money(wide_per_enquiry(current.accepted_cents, current.enquiries)),
        "currency": current.currency,
    })
}

fn wide_percent_change(current: i128, previous: i128) -> Option<i128> {
    if previous <= 0 {
        return (current > 0).then_some(100);
    }
    Some(((((current - previous) as f64) / previous as f64) * 100.0).round_ties_even() as i128)
}
fn wide_per_enquiry(cents: i128, enquiries: i64) -> i128 {
    if enquiries <= 0 {
        0
    } else {
        (cents as f64 / enquiries as f64).round_ties_even() as i128
    }
}
