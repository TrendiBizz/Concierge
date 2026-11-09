//! Batch 9: SMS signatures and sender rules, RAG URL tagging and the system prompt, against the live Python.
use chrono::DateTime;
use concierge_core::{rag, sms};
use serde::Deserialize;
use serde_json::Value;

#[derive(Deserialize)]
struct V {
    twilio: Vec<Tw>,
    payload: Vec<Pl>,
    gate: Vec<Gt>,
    ready: Vec<Rd>,
    tag: Vec<Tg>,
    prompt: Vec<Pr>,
}
#[derive(Deserialize)]
struct Tw {
    token: String,
    url: String,
    params: Vec<(String, String)>,
    sig: Option<String>,
    out: bool,
}
#[derive(Deserialize)]
struct Pl {
    to: String,
    body: String,
    sim: i64,
    out: Value,
}
#[derive(Deserialize)]
struct Gt {
    key: String,
    body_hex: String,
    ts: String,
    sig: String,
    now: f64,
    tol: i64,
    out: bool,
}
#[derive(Deserialize)]
struct Rd {
    provider: Option<String>,
    sid: String,
    tok: String,
    msid: String,
    tfrom: String,
    tenant: Option<Value>,
    gate: Option<[String; 3]>,
    out: bool,
}
#[derive(Deserialize)]
struct Tg {
    url: String,
    ch: String,
    out: Option<String>,
}
#[derive(Deserialize)]
struct Pr {
    tenant: Value,
    hits: Option<Vec<Value>>,
    ch: String,
    now: i64,
    out: String,
}

fn load() -> V {
    serde_json::from_str(
        &std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/parity/vectors9.json"))
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
fn twilio_and_gateway_signatures_match_python() {
    let v = load();
    for (i, c) in v.twilio.iter().enumerate() {
        assert_eq!(
            sms::validate_signature(&c.token, &c.url, &c.params, c.sig.as_deref().unwrap_or("")),
            c.out,
            "twilio case {i}"
        );
    }
    for (i, c) in v.gate.iter().enumerate() {
        assert_eq!(
            sms::validate_smsgate_signature(
                &c.key,
                &unhex(&c.body_hex),
                &c.ts,
                &c.sig,
                c.now,
                c.tol
            ),
            c.out,
            "gateway case {i}: ts {:?} sig {:?}",
            c.ts,
            c.sig
        );
    }
    for c in &v.payload {
        assert_eq!(sms::smsgate_payload(&c.to, &c.body, c.sim), c.out);
    }
}

#[test]
fn sender_readiness_matches_python() {
    for (i, c) in load().ready.iter().enumerate() {
        let (base, user, pw) = match &c.gate {
            Some(g) => (g[0].as_str(), g[1].as_str(), g[2].as_str()),
            None => ("http://gw", "u", "p"),
        };
        let s = sms::Settings {
            provider: c.provider.as_deref().unwrap_or(""),
            twilio_account_sid: &c.sid,
            twilio_auth_token: &c.tok,
            twilio_messaging_service_sid: &c.msid,
            twilio_from_number: &c.tfrom,
            smsgate_base_url: base,
            smsgate_username: user,
            smsgate_password: pw,
        };
        let tenant = c.tenant.as_ref().map(|t| sms::TenantSms {
            transport: t.get("sms_transport").and_then(Value::as_str).unwrap_or(""),
            enabled: t
                .get("sms_enabled")
                .and_then(Value::as_bool)
                .unwrap_or(false),
            from: t.get("sms_from").and_then(Value::as_str).unwrap_or(""),
        });
        assert_eq!(
            sms::sender_ready(&s, tenant.as_ref()),
            c.out,
            "ready case {i}: {:?}",
            c.tenant
        );
    }
}

#[test]
fn utm_tagging_matches_python() {
    for c in load().tag {
        assert_eq!(
            rag::tag_url(&c.url, &c.ch),
            c.out,
            "url {:?} channel {:?}",
            c.url,
            c.ch
        );
    }
}

#[test]
fn system_prompt_matches_python_character_for_character() {
    for (i, c) in load().prompt.iter().enumerate() {
        let got = rag::build_system_prompt(
            &c.tenant,
            c.hits.as_deref(),
            &c.ch,
            DateTime::from_timestamp(c.now, 0).unwrap(),
        );
        assert_eq!(
            got,
            c.out,
            "prompt case {i} (channel {}, native_booking {:?})",
            c.ch,
            c.tenant.get("native_booking")
        );
    }
}
