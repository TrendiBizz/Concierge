//! Transparent rule-based lead scoring (port of `scoring.py`). No randomness, no model call.
use crate::py_strip;
use regex::{Regex, RegexBuilder};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::sync::OnceLock;

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    Points,
    Count,
    Threshold,
}

impl Kind {
    pub fn name(self) -> &'static str {
        match self {
            Kind::Points => "points",
            Kind::Count => "count",
            Kind::Threshold => "threshold",
        }
    }
    fn range(self) -> (i64, i64) {
        match self {
            Kind::Points => (-50, 50),
            Kind::Count => (0, 5),
            Kind::Threshold => (1, 100),
        }
    }
}

/// key, default, dashboard label, kind. Order matters: it is the order of the dashboard editor.
pub const WEIGHTS: &[(&str, i64, &str, Kind)] = &[
    ("phone", 25, "Gave a phone number", Kind::Points),
    ("email", 10, "Gave an email address", Kind::Points),
    ("name", 5, "Gave a name", Kind::Points),
    ("consent", 10, "Agreed to be contacted", Kind::Points),
    ("booked", 30, "Booked an appointment", Kind::Points),
    (
        "intent_each",
        10,
        "Each price / booking / timing word (see cap)",
        Kind::Points,
    ),
    ("intent_cap", 2, "Most intent words that count", Kind::Count),
    (
        "long_message",
        5,
        "Described what they need (40+ characters)",
        Kind::Points,
    ),
    (
        "voice_or_sms",
        10,
        "Reached out by text or voice",
        Kind::Points,
    ),
    (
        "high_intent_page",
        10,
        "Was on a pricing, booking or contact page",
        Kind::Points,
    ),
    (
        "conversation",
        10,
        "Had a real conversation (3+ messages)",
        Kind::Points,
    ),
    (
        "spam_link",
        -25,
        "Message contains a link (possible spam)",
        Kind::Points,
    ),
    ("hot_at", 70, "Score needed to be HOT", Kind::Threshold),
    ("warm_at", 40, "Score needed to be WARM", Kind::Threshold),
];

pub const HOT_AT: i64 = 70;
pub const WARM_AT: i64 = 40;

pub type Weights = BTreeMap<String, i64>;

fn spec(key: &str) -> Option<&'static (&'static str, i64, &'static str, Kind)> {
    WEIGHTS.iter().find(|w| w.0 == key)
}

pub fn default_weights() -> Weights {
    WEIGHTS.iter().map(|w| (w.0.to_string(), w.1)).collect()
}

fn intent_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        RegexBuilder::new(
            r"\b(price|prices|pricing|cost|quote|quotation|how much|book|booking|appointment|available|availability|today|tomorrow|this week|urgent|asap|emergency|buy|order|hire|start)\b",
        )
        .case_insensitive(true)
        .build()
        .unwrap()
    })
}
fn page_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        RegexBuilder::new(r"(pricing|price|quote|book|contact|checkout|order)")
            .case_insensitive(true)
            .build()
            .unwrap()
    })
}
fn link_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        RegexBuilder::new(r"https?://|www\.")
            .case_insensitive(true)
            .build()
            .unwrap()
    })
}

/// Check a client's overrides. The error text is exactly the Python `ValueError` message.
/// Returns the cleaned overrides in the caller's key order.
pub fn validate_overrides(raw: &Value) -> Result<Vec<(String, i64)>, String> {
    let obj = raw
        .as_object()
        .ok_or("scoring must be an object of weight overrides")?;
    let mut clean: Vec<(String, i64)> = Vec::new();
    for (key, value) in obj {
        let (_, _, _, kind) = spec(key).ok_or_else(|| format!("unknown scoring key '{key}'"))?;
        let n = value
            .as_i64()
            .filter(|_| !value.is_boolean())
            .ok_or_else(|| format!("'{key}' must be a whole number"))?;
        let (low, high) = kind.range();
        if !(low..=high).contains(&n) {
            return Err(format!("'{key}' must be between {low} and {high}"));
        }
        clean.push((key.clone(), n));
    }
    let mut merged = default_weights();
    for (k, v) in &clean {
        merged.insert(k.clone(), *v);
    }
    if merged["warm_at"] >= merged["hot_at"] {
        return Err("warm_at must be lower than hot_at".into());
    }
    Ok(clean)
}

pub fn effective_weights(overrides: Option<&Weights>) -> Weights {
    let mut w = default_weights();
    if let Some(o) = overrides {
        for (k, v) in o {
            w.insert(k.clone(), *v);
        }
    }
    w
}

/// Weights in force for a tenant from its stored `scoring` value (a JSON object or a JSON string).
/// Non-integer or unknown entries are ignored (Python would carry them through untouched).
pub fn weights_for(scoring: Option<&Value>) -> Weights {
    let parsed;
    let raw = match scoring {
        Some(Value::String(s)) => {
            parsed = serde_json::from_str::<Value>(s).unwrap_or(Value::Null);
            &parsed
        }
        Some(v) => v,
        None => &Value::Null,
    };
    let mut o = Weights::new();
    if let Some(map) = raw.as_object() {
        for (k, v) in map {
            if let (Some(_), Some(n)) = (spec(k), v.as_i64()) {
                o.insert(k.clone(), n);
            }
        }
    }
    effective_weights(Some(&o))
}

pub fn label_for(score: i64, hot_at: i64, warm_at: i64) -> &'static str {
    if score >= hot_at {
        "hot"
    } else if score >= warm_at {
        "warm"
    } else {
        "cold"
    }
}

#[derive(Debug, Clone, Default)]
pub struct Lead {
    pub message: Option<String>,
    pub phone: Option<String>,
    pub email: Option<String>,
    pub name: Option<String>,
    pub consent_contact: bool,
    pub channel: Option<String>,
    pub page_url: Option<String>,
}

#[derive(Debug, PartialEq, Eq)]
pub struct Assessment {
    pub score: i64,
    pub label: &'static str,
    pub reasons: Vec<String>,
}

fn nonblank(o: &Option<String>) -> &str {
    py_strip(o.as_deref().unwrap_or(""))
}

fn add(points: &mut Vec<(i64, &str)>, w: &Weights, key: &str, applies: bool) {
    let value = w[key];
    if applies && value != 0 {
        points.push((value, spec(key).unwrap().2));
    }
}

pub fn assess(lead: &Lead, user_turns: i64, booked: bool, weights: Option<&Weights>) -> Assessment {
    let w = effective_weights(weights);
    let mut points: Vec<(i64, &str)> = Vec::new();
    let message = nonblank(&lead.message);
    add(&mut points, &w, "phone", !nonblank(&lead.phone).is_empty());
    add(&mut points, &w, "email", !nonblank(&lead.email).is_empty());
    add(
        &mut points,
        &w,
        "name",
        nonblank(&lead.name).chars().count() >= 2,
    );
    add(&mut points, &w, "consent", lead.consent_contact);

    if booked {
        add(&mut points, &w, "booked", true);
    } else {
        let found: BTreeSet<String> = intent_re()
            .find_iter(message)
            .map(|m| m.as_str().to_lowercase())
            .collect();
        let counted = (found.len() as i64).min(w["intent_cap"]);
        if counted != 0 && w["intent_each"] != 0 {
            points.push((
                counted * w["intent_each"],
                "Asked about price, booking or timing",
            ));
        }
        add(
            &mut points,
            &w,
            "long_message",
            message.chars().count() >= 40,
        );
    }

    let channel = lead.channel.as_deref().unwrap_or("");
    add(
        &mut points,
        &w,
        "voice_or_sms",
        channel == "sms" || channel == "voice",
    );
    add(
        &mut points,
        &w,
        "high_intent_page",
        page_re().is_match(lead.page_url.as_deref().unwrap_or("")),
    );
    add(&mut points, &w, "conversation", user_turns >= 3);
    add(&mut points, &w, "spam_link", link_re().is_match(message));

    let score = points.iter().map(|p| p.0).sum::<i64>().clamp(0, 100);
    Assessment {
        score,
        label: label_for(score, w["hot_at"], w["warm_at"]),
        reasons: points
            .iter()
            .map(|(p, why)| format!("{}{p} {why}", if *p > 0 { "+" } else { "" }))
            .collect(),
    }
}
