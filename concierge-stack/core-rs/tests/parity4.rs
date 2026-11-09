//! Batch 4: tool specs, lead-capture rules, Twenty payload/URL/delivery id and views, against the live Python.
use concierge_core::{events, tools};
use serde::Deserialize;
use serde_json::{json, Value};

#[derive(Deserialize)]
struct V {
    tools: Vec<ToolCase>,
    capture: Vec<Cap>,
    search: Vec<Search>,
    twenty: Vec<Tw>,
    urls: Vec<UrlCase>,
    delivery: Vec<Del>,
    views: Vec<View>,
}
#[derive(Deserialize)]
struct ToolCase {
    tenant: Value,
    chat: Vec<Value>,
    voice: Vec<Value>,
    voice_web: Vec<Value>,
}
#[derive(Deserialize)]
struct Cap {
    args: Value,
    sender: Option<String>,
    sms: bool,
    cc: String,
    out: Value,
}
#[derive(Deserialize)]
struct Search {
    args: Value,
    out: Option<String>,
}
#[derive(Deserialize)]
struct Tw {
    tenant: Value,
    event: String,
    sections: Value,
    out: Option<Value>,
}
#[derive(Deserialize)]
struct UrlCase {
    url: String,
    ok: bool,
}
#[derive(Deserialize)]
struct Del {
    tenant: String,
    event: String,
    source: String,
    out: String,
}
#[derive(Deserialize)]
struct View {
    secs: i64,
    micros: u32,
    tz: String,
    lead: Value,
    lead_out: Option<Value>,
    appt: Value,
    appt_out: Value,
}

fn load() -> V {
    serde_json::from_str(
        &std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/parity/vectors4.json"))
            .unwrap(),
    )
    .unwrap()
}

#[test]
fn tool_lists_match_python() {
    for c in load().tools {
        assert_eq!(tools::chat_tools(&c.tenant), c.chat, "chat {:?}", c.tenant);
        assert_eq!(
            tools::voice_tools(&c.tenant, false),
            c.voice,
            "voice {:?}",
            c.tenant
        );
        assert_eq!(
            tools::voice_tools(&c.tenant, true),
            c.voice_web,
            "voice_web {:?}",
            c.tenant
        );
    }
}

#[test]
fn lead_capture_normalisation_matches_python() {
    for (i, c) in load().capture.iter().enumerate() {
        let got = match tools::normalise_capture(&c.args, c.sender.as_deref(), c.sms, &c.cc) {
            Ok(l) => {
                json!({"ok": {"name": l.name, "email": l.email, "phone": l.phone, "message": l.message, "consent": l.consent, "marketing": l.marketing}})
            }
            Err(e) => json!({"err": e}),
        };
        assert_eq!(
            got, c.out,
            "capture case {i}: {:?} sender {:?} sms {} cc {}",
            c.args, c.sender, c.sms, c.cc
        );
    }
}

#[test]
fn knowledge_query_clamp_matches_python() {
    for c in load().search {
        assert_eq!(tools::search_query(&c.args), c.out, "{:?}", c.args);
    }
}

#[test]
fn twenty_payload_matches_python() {
    for (i, c) in load().twenty.iter().enumerate() {
        assert_eq!(
            events::twenty_bridge_payload(&c.tenant, &c.event, &c.sections),
            c.out,
            "twenty case {i}: {} {:?}",
            c.event,
            c.sections
        );
    }
}

#[test]
fn bridge_url_rules_match_python() {
    for c in load().urls {
        assert_eq!(events::bridge_url_allowed(&c.url), c.ok, "url {:?}", c.url);
    }
}

#[test]
fn delivery_ids_match_python() {
    for c in load().delivery {
        assert_eq!(
            events::delivery_id(&c.tenant, &c.event, &c.source),
            c.out,
            "{:?} {:?} {:?}",
            c.tenant,
            c.event,
            c.source
        );
    }
}

#[test]
fn lead_and_appointment_views_match_python() {
    for (i, c) in load().views.iter().enumerate() {
        let at = (c.secs, c.micros);
        assert_eq!(
            events::lead_view(&c.lead, at).ok(),
            c.lead_out,
            "lead view {i}: {:?}",
            c.lead
        );
        assert_eq!(
            events::appointment_view(&c.appt, at, at, &c.tz),
            c.appt_out,
            "appt view {i}"
        );
    }
}
