//! Batch 11: telephony rules, the Grok session builder, slugs and the eval checks, against the live Python.
use chrono::DateTime;
use concierge_core::evals::{self, ToolCall, Turn};
use concierge_core::{telephony as t, voice_session};
use serde::Deserialize;
use serde_json::Value;

#[derive(Deserialize)]
struct V {
    sip: Vec<Sip>,
    header: Vec<Hd>,
    twiml: Vec<Tw>,
    ws: Vec<Ws>,
    patterns: Vec<Pat>,
    sip_twiml: Vec<ST>,
    forward: Vec<Fw>,
    slugs: Vec<Slug>,
    sessions: Vec<Sess>,
    tokens: Vec<Tok>,
    evals: Vec<Ev>,
}
#[derive(Deserialize)]
struct Sip {
    label: String,
    secret: String,
    body_hex: String,
    id: String,
    ts: String,
    sigs: String,
    now: f64,
    out: bool,
}
#[derive(Deserialize)]
struct Hd {
    headers: Value,
    name: String,
    out: String,
}
#[derive(Deserialize)]
struct Tw {
    base: String,
    name: String,
    offer: bool,
    out: Value,
}
#[derive(Deserialize)]
struct Ws {
    base: String,
    token: String,
    sig: String,
    out: Value,
}
#[derive(Deserialize)]
struct Pat {
    #[serde(rename = "in")]
    input: String,
    call: bool,
    rec: bool,
    e164: bool,
    consent: bool,
}
#[derive(Deserialize)]
struct ST {
    cfg: Value,
    out: String,
}
#[derive(Deserialize)]
struct Fw {
    dest: String,
    carrier: String,
    mode: String,
    out: Vec<Value>,
}
#[derive(Deserialize)]
struct Slug {
    #[serde(rename = "in")]
    input: String,
    out: String,
}
#[derive(Deserialize)]
struct Sess {
    tenant: Value,
    website: bool,
    now: i64,
    out: Value,
}
#[derive(Deserialize)]
struct Tok {
    data: Value,
    out: Option<String>,
}
#[derive(Deserialize)]
struct Ev {
    reply: String,
    tc: Vec<Value>,
    evidence: String,
    price: (bool, String),
    ai: (bool, String),
    private: (bool, String),
    nolead: (bool, String),
    lead: (bool, String),
    book: (bool, String),
}

fn load() -> V {
    serde_json::from_str(
        &std::fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/parity/vectors11.json"
        ))
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
fn sip_webhook_signatures_match_python() {
    let (mut compared, mut declined) = (0, 0);
    for c in &load().sip {
        let got =
            t::sip_signature_valid(&c.secret, &unhex(&c.body_hex), &c.id, &c.ts, &c.sigs, c.now);
        if got == c.out {
            compared += 1;
        } else {
            // The only allowed difference is refusing a timestamp written with underscores (Python's int() accepts it).
            assert!(
                c.out && !got && c.ts.contains('_'),
                "{}: python {} rust {got}",
                c.label,
                c.out
            );
            declined += 1;
        }
    }
    assert!(compared > 85, "{compared} compared, {declined} declined");
}

#[test]
fn caller_number_header_parsing_matches_python() {
    for c in &load().header {
        let got = t::header_number(&c.headers, &c.name);
        if got != c.out {
            // Python's \d also matches non-ASCII digits; Rust refuses those (no number is the safe answer).
            assert!(
                got.is_empty() && !c.out.is_ascii(),
                "{:?}: python {:?} rust {:?}",
                c.headers,
                c.out,
                got
            );
        }
    }
}

#[test]
fn twiml_and_relay_signatures_match_python() {
    let v = load();
    for c in &v.twiml {
        let got = t::twiml(&c.name, c.offer, &c.base);
        match (&got, c.out.get("ok")) {
            (Ok(g), Some(w)) => {
                assert_eq!(g, w.as_str().unwrap(), "twiml {:?} {:?}", c.base, c.name)
            }
            (Err(_), None) => {}
            other => panic!("twiml {:?} {:?}: {other:?} vs {:?}", c.base, c.name, c.out),
        }
    }
    for c in &v.ws {
        let got = t::valid_websocket_signature(&c.token, &c.base, &c.sig);
        match c.out.as_bool() {
            Some(want) => assert_eq!(got, want, "ws {:?} {:?}", c.base, c.sig),
            None => assert!(
                !got,
                "Python raised for {:?}; Rust must say invalid",
                c.base
            ),
        }
    }
}

#[test]
fn id_and_consent_patterns_match_python() {
    for c in &load().patterns {
        assert_eq!(t::is_call_sid(&c.input), c.call, "call sid {:?}", c.input);
        assert_eq!(
            t::is_recording_sid(&c.input),
            c.rec,
            "recording sid {:?}",
            c.input
        );
        assert_eq!(t::is_e164(&c.input), c.e164, "e164 {:?}", c.input);
        assert_eq!(
            t::is_recording_consent(&c.input),
            c.consent,
            "consent {:?}",
            c.input
        );
    }
}

#[test]
fn sip_twiml_forwarding_and_slugs_match_python() {
    let v = load();
    for c in &v.sip_twiml {
        let s = |k: &str| c.cfg[k].as_str().unwrap().to_string();
        assert_eq!(
            t::sip_twiml(&s("sip_username"), &s("sip_password"), &s("number")),
            c.out,
            "{:?}",
            c.cfg
        );
    }
    for c in &v.forward {
        assert_eq!(t::forwarding_steps(&c.dest, &c.carrier, &c.mode), c.out);
    }
    for c in &v.slugs {
        assert_eq!(t::slugify(&c.input), c.out, "slug {:?}", c.input);
    }
}

#[test]
fn grok_session_matches_python() {
    let v = load();
    for (i, c) in v.sessions.iter().enumerate() {
        let got = voice_session::build_session(
            &c.tenant,
            c.website,
            "eve",
            DateTime::from_timestamp(c.now, 0).unwrap(),
        );
        assert_eq!(got, c.out, "session case {i} (website {})", c.website);
    }
    for c in &v.tokens {
        assert_eq!(voice_session::extract_token(&c.data), c.out, "{:?}", c.data);
    }
}

#[test]
fn eval_checks_match_python() {
    for c in &load().evals {
        let calls: Vec<ToolCall> =
            c.tc.iter()
                .map(|x| ToolCall {
                    name: x["name"].as_str().unwrap().into(),
                    ok: x["ok"].as_bool().unwrap(),
                })
                .collect();
        let turns = vec![
            Turn {
                user: "u1".into(),
                reply: c.reply.clone(),
                tool_calls: calls.clone(),
            },
            Turn {
                user: "u2".into(),
                reply: c.reply.clone(),
                tool_calls: calls,
            },
        ];
        let ctx = format!(
            "reply {:?} calls {:?} evidence {:?}",
            c.reply, c.tc, c.evidence
        );
        // Messages that embed a Python repr() (prices, quoted replies) are compared by result and fixed prefix only.
        let price = evals::no_unknown_prices(&turns, &c.evidence);
        assert_eq!(price.0, c.price.0, "price: {ctx}");
        assert!(
            price.1.starts_with(c.price.1.split(" [").next().unwrap()) || price.0,
            "price message: {ctx}"
        );
        let ai = evals::says_it_is_ai(&turns);
        assert_eq!(ai.0, c.ai.0, "ai: {ctx}");
        assert_eq!(
            ai.1.split(':').next(),
            c.ai.1.split(':').next(),
            "ai message: {ctx}"
        );
        assert_eq!(
            evals::keeps_rules_private(&turns),
            c.private,
            "private: {ctx}"
        );
        assert_eq!(
            evals::no_lead_before_contact(&turns),
            c.nolead,
            "nolead: {ctx}"
        );
        assert_eq!(evals::lead_after_contact(&turns), c.lead, "lead: {ctx}");
        assert_eq!(
            evals::no_booking_without_readback(&turns),
            c.book,
            "book: {ctx}"
        );
    }
}
