//! Batch 13: channel authorization, owner knowledge, phone-setup validation, owner-auth retention limits, the enquirer
//! acknowledgement flow and the knowledge ingest rules, against vectors generated from the live Python.
use concierge_core::acknowledgements::{self as ack, Outbox, Store};
use concierge_core::ingest::{self, DemoRow, Op, Page};
use concierge_core::pydantic::errors_json;
use concierge_core::{channel_auth, knowledge, maintenance, phone_setup};
use serde_json::{json, Value};

fn vectors() -> Value {
    serde_json::from_str(include_str!("../parity/vectors13.json")).unwrap()
}

/// Expands the `{"$rep": [unit, count]}` placeholders the generator uses for very long strings.
fn expand(v: &Value) -> Value {
    match v {
        Value::Object(m) if m.len() == 1 && m.contains_key("$rep") => {
            let a = m["$rep"].as_array().unwrap();
            Value::String(
                a[0].as_str()
                    .unwrap()
                    .repeat(a[1].as_u64().unwrap() as usize),
            )
        }
        Value::Object(m) => Value::Object(m.iter().map(|(k, x)| (k.clone(), expand(x))).collect()),
        Value::Array(a) => Value::Array(a.iter().map(expand).collect()),
        other => other.clone(),
    }
}

#[test]
fn readiness_matches_python() {
    for c in vectors()["channel"]["readiness"].as_array().unwrap() {
        let got = channel_auth::readiness(
            c["channels"].as_object().unwrap(),
            c["checks"].as_object().unwrap(),
        );
        assert_eq!(got, c["out"], "{c}");
        // object key order is part of the report the owner sees
        assert_eq!(
            got.as_object().unwrap().keys().collect::<Vec<_>>(),
            c["out"].as_object().unwrap().keys().collect::<Vec<_>>()
        );
    }
}

#[test]
fn authorization_request_validation_matches_python() {
    let mut ok = 0;
    for c in vectors()["channel"]["request"].as_array().unwrap() {
        let got = match channel_auth::validate(&c["in"]) {
            Ok(a) => {
                ok += 1;
                json!({"ok": {"channel": a.channel, "authorized": a.authorized, "acknowledgement": a.acknowledgement}})
            }
            Err(e) => json!({"errors": errors_json(&e)}),
        };
        assert_eq!(got, c["out"], "{c}");
    }
    assert!(ok > 500, "{ok}");
}

#[test]
fn membership_and_record_guard_match_python() {
    for c in vectors()["channel"]["membership"].as_array().unwrap() {
        let stored = c["stored"].as_bool().unwrap_or_else(|| {
            // the fake pool returned 1/0/None: Python wraps it in bool(...)
            c["stored"].as_i64().unwrap_or(0) != 0
        });
        assert_eq!(
            channel_auth::is_authorized(c["channel"].as_str().unwrap(), stored),
            c["out"].as_bool().unwrap(),
            "{c}"
        );
    }
    for c in vectors()["record"].as_array().unwrap() {
        let a = channel_auth::Authorization {
            channel: "social",
            authorized: c["authorized"].as_bool().unwrap(),
            acknowledgement: c["ack"].as_bool().unwrap(),
        };
        let got = match channel_auth::check_record(&a) {
            Err(e) => json!({"error": e}),
            Ok(()) => {
                json!({"ok": channel_auth::record_response("social", a.authorized, json!("T"))})
            }
        };
        assert_eq!(got, c["out"], "{c}");
        // an authorization is only stored (and audited) when the guard passes
        assert_eq!(
            c["calls"].as_array().unwrap().len() == 2,
            got.get("ok").is_some()
        );
    }
}

#[test]
fn business_documents_match_python() {
    let mut ok = 0;
    for c in vectors()["knowledge"]["validate"].as_array().unwrap() {
        let input = expand(&c["in"]);
        let got = match knowledge::validate(&input) {
            Ok(d) => {
                ok += 1;
                json!({"ok": {"title": d.title, "text": d.text}})
            }
            Err(e) => json!({"errors": errors_json(&e)}),
        };
        assert_eq!(got, c["out"], "{}", c["in"]);
    }
    assert!(ok > 30, "{ok}");
}

#[test]
fn document_identity_and_ids_match_python() {
    for c in vectors()["knowledge"]["identity"].as_array().unwrap() {
        let title = c["title"].as_str().unwrap();
        if let Some(id) = c.get("id") {
            assert_eq!(knowledge::identity(title), id.as_str().unwrap(), "{title}");
        }
        if let Some(save) = c.get("save") {
            let d = knowledge::Document {
                title: title.into(),
                text: c["args"][1].as_str().unwrap().into(),
            };
            let (label, text, t) = knowledge::ingest_args(&d);
            assert_eq!(json!([label, text, t]), c["args"], "{title}");
            assert_eq!(
                save["document_id"].as_str().unwrap(),
                knowledge::identity(title)
            );
        }
    }
    for c in vectors()["knowledge"]["ids"].as_array().unwrap() {
        assert_eq!(
            knowledge::is_document_id(c["id"].as_str().unwrap()),
            c["out"].as_bool().unwrap(),
            "{c}"
        );
    }
}

#[test]
fn phone_models_match_python() {
    let v = vectors();
    for (key, f) in [
        ("setup", phone_setup::validate_setup as fn(&Value) -> _),
        ("mobile", phone_setup::validate_mobile),
    ] {
        let mut ok = 0;
        for c in v["phone"][key].as_array().unwrap() {
            let got = match f(&c["in"]) {
                Ok(m) => {
                    ok += 1;
                    json!({"ok": m})
                }
                Err(e) => json!({"errors": errors_json(&e)}),
            };
            assert_eq!(got, c["out"], "{c}");
        }
        assert!(ok > 5, "{key} {ok}");
    }
}

#[test]
fn retention_batch_size_matches_python() {
    for c in vectors()["maintenance"].as_array().unwrap() {
        let size = c["size"].as_i64().unwrap();
        match maintenance::check_batch_size(size) {
            Err(e) => assert_eq!(json!({"error": e}), c["out"], "{c}"),
            Ok(()) => {
                let counts: serde_json::Map<String, Value> = maintenance::TABLES
                    .iter()
                    .map(|(t, _)| {
                        (
                            t.to_string(),
                            json!(if c["dry"].as_bool().unwrap() { 7 } else { 2 }),
                        )
                    })
                    .collect();
                assert_eq!(json!({"ok": counts}), c["out"], "{c}");
            }
        }
    }
}

struct Rec {
    effects: Vec<Value>,
    row: Option<Value>,
    authorized: bool,
    lead: Option<String>,
}

impl Store for Rec {
    fn decline(&mut self, t: &str, c: &str) {
        self.effects.push(json!(["decline", [t, c]]));
    }
    fn lock_pending(&mut self, t: &str, c: &str) -> Option<Value> {
        self.effects.push(json!(["select_pending", [t, c]]));
        self.row.as_ref().map(|r| r["pending"].clone())
    }
    fn set_pending(&mut self, t: &str, c: &str, key_json: &str) {
        self.effects.push(json!(["pending", [t, c, key_json]]));
    }
    fn is_authorized(&mut self, t: &str, ch: &str) -> bool {
        self.effects.push(json!(["authorized", [t, ch]]));
        self.authorized
    }
    fn first_lead(&mut self, t: &str, c: &str) -> Option<String> {
        self.effects.push(json!(["select_lead", [t, c]]));
        self.lead.clone()
    }
    fn queue(&mut self, o: &Outbox) {
        self.effects.push(json!([
            "outbox",
            [
                o.tenant_id,
                o.channel,
                o.recipient,
                o.subject,
                o.body,
                o.dedupe_key,
                o.lead_id
            ]
        ]));
    }
}

#[test]
fn acknowledgement_flow_matches_python() {
    let mut statuses = std::collections::BTreeSet::new();
    let cases = vectors()["ack"].as_array().unwrap().clone();
    assert!(cases.len() > 2000);
    for c in &cases {
        let mut store = Rec {
            effects: vec![],
            row: (!c["row"].is_null()).then(|| c["row"].clone()),
            authorized: c["authorized"].as_bool().unwrap(),
            lead: c["lead"].as_str().map(String::from),
        };
        let got = ack::request(&mut store, "t-1", "Trendi", &c["args"], &c["ctx"]);
        if c.get("crash").is_some() {
            assert!(
                got.is_err(),
                "Python crashed, Rust must not claim a result: {c}"
            );
            continue;
        }
        let got = got.unwrap_or_else(|e| panic!("{e:?} for {c}"));
        assert_eq!(got, c["out"], "{c}");
        assert_eq!(Value::Array(store.effects), c["effects"], "{c}");
        statuses.insert(
            got["status"]
                .as_str()
                .or(got["error"].as_str())
                .unwrap_or("needs_confirmation")
                .to_string(),
        );
    }
    for needed in [
        "queued",
        "declined",
        "dry_run",
        "needs_confirmation",
        "Conversation unavailable",
    ] {
        assert!(statuses.contains(needed), "never exercised: {needed}");
    }
}

#[test]
fn ingest_store_matches_python() {
    for c in vectors()["ingest"]["store"].as_array().unwrap() {
        let owned: Vec<(String, String, String)> = c["pages"]
            .as_array()
            .unwrap()
            .iter()
            .map(|p| {
                (
                    p[0].as_str().unwrap().into(),
                    p[1].as_str().unwrap().into(),
                    p[2].as_str().unwrap().into(),
                )
            })
            .collect();
        let pages: Vec<Page> = owned
            .iter()
            .map(|(u, t, x)| Page {
                url: u,
                title: t,
                text: x,
            })
            .collect();
        let records = ingest::records(&pages);
        let ops = c["ops"].as_array().unwrap();
        if records.is_empty() {
            assert_eq!(c["out"], json!({"n": 0}));
            assert!(ops.is_empty());
            continue;
        }
        // the first recorded operation is the embedding request, which must receive exactly these texts
        assert_eq!(ops[0][0], "embed");
        assert_eq!(ops[0][1].as_u64().unwrap() as usize, records.len());
        assert_eq!(
            ops[0][2],
            Value::Array(records.iter().map(|r| json!(r.text)).collect()),
            "{}",
            c["pages"]
        );
        let vectors: Vec<Vec<f64>> = c["vectors"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| {
                v.as_array()
                    .unwrap()
                    .iter()
                    .map(|x| x.as_f64().unwrap())
                    .collect()
            })
            .collect();
        let plan = ingest::store_plan(
            "t-1",
            &records,
            &vectors,
            c["replace_crawled"].as_bool().unwrap(),
            c["replace_url"].as_str(),
        );
        match plan {
            Err(e) => {
                assert_eq!(c["out"], json!({"error": e}));
                assert_eq!(
                    ops.len(),
                    1,
                    "nothing may be written when embeddings are short"
                );
            }
            Ok(plan) => {
                assert_eq!(c["out"], json!({"n": records.len()}));
                let got: Vec<Value> = plan
                    .into_iter()
                    .map(|op| match op {
                        Op::Execute { sql, args } => json!(["execute", sql, args]),
                        Op::ExecuteMany { sql, rows } => json!(["executemany", sql, rows]),
                    })
                    .collect();
                assert_eq!(
                    Value::Array(got),
                    Value::Array(ops[1..].to_vec()),
                    "{}",
                    c["pages"]
                );
            }
        }
    }
}

#[test]
fn demo_questions_match_python() {
    for c in vectors()["ingest"]["questions"].as_array().unwrap() {
        let rows: Vec<(String, String)> = c["rows"]
            .as_array()
            .unwrap()
            .iter()
            .map(|r| {
                (
                    r["title"].as_str().unwrap().into(),
                    r["content"].as_str().unwrap().into(),
                )
            })
            .collect();
        let calls = c["calls"].as_array().unwrap();
        let count = c["count"].as_u64().unwrap() as usize;
        if rows.is_empty() {
            assert_eq!(c["out"], json!([]));
            assert_eq!(calls.len(), 1, "no model call without knowledge");
            continue;
        }
        let demo: Vec<DemoRow> = rows
            .iter()
            .map(|(t, x)| DemoRow {
                title: t,
                content: x,
            })
            .collect();
        assert_eq!(calls[1][0], "llm");
        assert_eq!(
            ingest::demo_messages("Biz", &demo, count),
            calls[1][1],
            "{c}"
        );
        assert_eq!(calls[1][2], json!(0.7));
        assert_eq!(calls[1][3], json!(400));
        let questions = ingest::parse_questions(c["content"].as_str(), count);
        assert_eq!(json!(questions), c["out"], "{c}");
        assert_eq!(
            json!(["t-1", ingest::questions_json(&questions).unwrap()]),
            calls[2][1],
            "{c}"
        );
    }
}

#[test]
fn pgvector_text_matches_python() {
    let v = vectors();
    for c in v["ingest"]["pgvector"].as_array().unwrap() {
        let vec: Vec<f64> = c["vec"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| x.as_f64().unwrap())
            .collect();
        assert_eq!(ingest::to_pgvector(&vec), c["out"].as_str().unwrap(), "{c}");
    }
    let s = &v["ingest"]["pgvector_special"][0];
    assert_eq!(
        ingest::to_pgvector(&[f64::NAN, f64::INFINITY, f64::NEG_INFINITY]),
        s["out"].as_str().unwrap()
    );
}
