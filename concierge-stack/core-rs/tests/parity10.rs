//! Batch 10: email ingress, against the real `cloudflare_inbound.handle()` run with a fake database and clock.
use concierge_core::inbound::{draft_address, draft_subject, enquiry_plan, ingest_plan, verify_request};
use serde::Deserialize;
use serde_json::Value;

#[derive(Deserialize)]
struct V { cases: Vec<Case>, address: Vec<Addr>, subject: Vec<Subj>, secret: String, tenant: String }
#[derive(Deserialize)]
struct Case { name: String, enabled: bool, secret: String, ts: String, sig: String, body_hex: String, now: i64, out: Value }
#[derive(Deserialize)]
struct Addr { #[serde(rename = "in")] input: String, out: Option<String> }
#[derive(Deserialize)]
struct Subj { #[serde(rename = "in")] input: String, out: String }

fn load() -> V {
    serde_json::from_str(&std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/parity/vectors10.json")).unwrap()).unwrap()
}
fn unhex(s: &str) -> Vec<u8> {
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap()).collect()
}
fn s(v: &Value) -> String { v.as_str().unwrap().to_string() }

#[test]
fn webhook_authentication_and_validation_match_python() {
    let v = load();
    assert_eq!(v.secret.len(), 40);
    let mut accepted = 0;
    for c in &v.cases {
        let body = unhex(&c.body_hex);
        let got = verify_request(c.enabled, &c.secret, &c.ts, &c.sig, &body, c.now);
        let ctx = format!("case {:?}", c.name);
        if let Some(status) = c.out.get("status").and_then(Value::as_u64) {
            let status = status as u16;
            match status {
                503 | 401 | 413 => {
                    let r = got.expect_err(&ctx);
                    if c.ts.is_ascii() {
                        assert_eq!((r.status, r.detail), (status, c.out["detail"].as_str().unwrap()), "{ctx}");
                    } else {
                        // Known, documented divergence: Python accepts non-ASCII decimal digits in the timestamp and fails later with a
                        // different message. Both refuse with the same status, so only the status is compared.
                        assert_eq!(r.status, status, "{ctx}");
                    }
                }
                // 400 is either a payload the webhook layer refuses, or one the ingestion layer refuses afterwards.
                400 => match got {
                    Err(r) => assert_eq!(r.status, 400, "{ctx}"),
                    Ok(p) => assert!(ingest_plan("cloudflare", &p.message_id, &p.sender, &p.recipient, &p.subject, &p.text).is_none(), "{ctx}: Python refused it, Rust accepted it"),
                },
                // 404 and 403 come from the database after the payload was accepted.
                404 | 403 => { got.expect(&ctx); }
                other => panic!("unexpected python status {other}"),
            }
            continue;
        }
        if c.out.get("exception").is_some() {
            assert!(got.is_err(), "{ctx}: Python crashed, Rust must refuse");
            continue;
        }
        // ---- accepted: every stored value must match ----
        let ok = &c.out["ok"];
        let p = got.expect(&ctx);
        let plan = ingest_plan("cloudflare", &p.message_id, &p.sender, &p.recipient, &p.subject, &p.text).expect(&ctx);
        let draft = ok["draft"].as_array().unwrap();
        assert_eq!(draft[0], v.tenant);
        assert_eq!(s(&draft[1]), plan.source_key, "{ctx}: source key");
        assert_eq!(s(&draft[2]), plan.draft_sender, "{ctx}: sender");
        assert_eq!(s(&draft[3]), plan.draft_subject, "{ctx}: subject");
        assert_eq!(s(&draft[4]), plan.draft_inbound_body, "{ctx}: body");
        assert_eq!(s(&ok["session"]), plan.session_id, "{ctx}: session");
        let e = enquiry_plan(&v.tenant, "Trendi", "email", &plan.source_key, &format!("{}\n\n{}", p.subject, p.text), &plan.draft_sender, "").expect(&ctx);
        let lead = ok["lead"].as_array().unwrap();
        assert_eq!((s(&lead[2]), s(&lead[3]), s(&lead[4])), (e.lead_email.clone(), e.lead_phone.clone(), e.lead_message.clone()), "{ctx}: lead");
        assert_eq!((s(&lead[6]), s(&ok["source"][2])), (e.lead_key.clone(), e.original_key.clone()), "{ctx}: keys");
        assert_eq!(s(&ok["source"][4]), e.original_text, "{ctx}: original text");
        let owner = ok["owner"].as_array().unwrap();
        assert_eq!((s(&owner[0]), s(&owner[1]), s(&owner[2])), (e.owner_subject, e.owner_body, e.owner_dedupe), "{ctx}: owner notice");
        accepted += 1;
    }
    assert!(accepted >= 10, "only {accepted} accepted cases compared");
}

#[test]
fn draft_helpers_match_python() {
    let v = load();
    for c in &v.address { assert_eq!(draft_address(&c.input), c.out, "address {:?}", c.input); }
    for c in &v.subject { assert_eq!(draft_subject(&c.input), c.out, "subject {:?}", c.input); }
}

#[test]
fn enquiry_rules() {
    assert!(enquiry_plan("t", "T", "fax", "src", "m", "", "").is_none(), "unknown channel");
    assert!(enquiry_plan("t", "T", "email", "", "m", "", "").is_none(), "an enquiry needs an authenticated source");
    let e = enquiry_plan("t", "Trendi", "sms", "src", "hello", "", "+6421").unwrap();
    assert_eq!(e.owner_subject, "Sms enquiry for Trendi");
    assert_ne!(e.lead_key, e.original_key, "a repeated source with new text is a new original, the same lead");
}
