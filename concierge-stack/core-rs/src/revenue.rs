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
        (integer_ratio(cents.into(), enquiries.into())).round_ties_even() as i64
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
    format!("{:.2}", integer_ratio(cents, 100)).parse().unwrap()
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
    Some((integer_ratio(current - previous, previous) * 100.0).round_ties_even() as i128)
}
fn wide_per_enquiry(cents: i128, enquiries: i64) -> i128 {
    if enquiries <= 0 {
        0
    } else {
        (integer_ratio(cents, enquiries.into())).round_ties_even() as i128
    }
}

// Python divides integer operands before rounding to binary64. Casting the
// operands first introduces a second rounding for aggregates above 2^53.
fn integer_ratio(n: i128, d: i128) -> f64 {
    if n == 0 {
        return 0.0;
    }
    let negative = (n < 0) != (d < 0);
    let n = n.unsigned_abs();
    let d = d.unsigned_abs();
    let q = n / d;
    let mut rem = n % d;
    let mut bits = 128 - q.leading_zeros() as i32;
    let (mut sig, exp) = if bits > 53 {
        let shift = bits - 53;
        let mut sig = q >> shift;
        let tail = q - (sig << shift);
        let half = 1u128 << (shift - 1);
        if tail > half || (tail == half && (rem > 0 || sig & 1 == 1)) {
            sig += 1
        }
        return (if negative { -1.0 } else { 1.0 }) * sig as f64 * 2f64.powi(shift);
    } else if bits > 0 {
        (q, bits - 1)
    } else {
        let mut exp = -1;
        loop {
            rem *= 2;
            if rem >= d {
                rem -= d;
                break;
            }
            exp -= 1
        }
        bits = 1;
        (1, exp)
    };
    while bits < 53 {
        rem *= 2;
        sig *= 2;
        if rem >= d {
            rem -= d;
            sig += 1
        }
        bits += 1
    }
    rem *= 2;
    if rem > d || (rem == d && sig & 1 == 1) {
        sig += 1
    }
    (if negative { -1.0 } else { 1.0 }) * sig as f64 * 2f64.powi(exp - 52)
}
