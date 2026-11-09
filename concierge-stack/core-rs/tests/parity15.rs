//! Batch 15: settings rules, the owner business profile, email drafts and tenant records, against vectors from the live Python.
use concierge_core::drafts::{self, Approval, DraftRow};
use concierge_core::owner_profile::{self, Outcome};
use concierge_core::pydantic::errors_json;
use concierge_core::pyurl::Fail;
use concierge_core::settings::{self, Settings};
use concierge_core::{telephony, tenants};
use serde_json::{json, Map, Value};

fn vectors() -> Value {
    serde_json::from_str(include_str!("../parity/vectors15.json")).unwrap()
}

#[test]
fn settings_match_python() {
    let v = vectors();
    let mut declined = 0;
    for c in v["settings"]["portal"].as_array().unwrap() {
        match settings::owner_portal(&c["url"]) {
            Ok(()) => assert_eq!(c["out"], json!({"ok": true}), "{c}"),
            Err(Ok(t)) => assert_eq!(c["out"], json!({"errors": [t]}), "{c}"),
            Err(Err(Fail::Unsupported(_))) => declined += 1,
            Err(Err(Fail::Value)) => panic!("{c}"),
        }
    }
    assert!(declined <= 2, "{declined}");
    for c in v["settings"]["props"].as_array().unwrap() {
        let k = &c["kw"];
        let g = |n: &str| k[n].as_str().unwrap();
        let s = Settings {
            xai_api_key: g("xai_api_key"),
            llm_api_key: g("llm_api_key"),
            voice_model: g("voice_model"),
            xai_realtime_url: g("xai_realtime_url"),
            sms_provider: g("sms_provider"),
            twilio_account_sid: g("twilio_account_sid"),
            twilio_auth_token: g("twilio_auth_token"),
            twilio_from_number: g("twilio_from_number"),
            twilio_messaging_service_sid: g("twilio_messaging_service_sid"),
            smsgate_base_url: g("smsgate_base_url"),
            smsgate_username: g("smsgate_username"),
            smsgate_password: g("smsgate_password"),
            smtp_host: g("smtp_host"),
            smtp_from: g("smtp_from"),
        };
        assert_eq!(
            s.effective_llm_key(),
            c["effective_llm_key"].as_str().unwrap()
        );
        assert_eq!(s.voice_ws_url(), c["voice_ws_url"].as_str().unwrap());
        assert_eq!(
            s.sms_configured(),
            c["sms_configured"].as_bool().unwrap(),
            "{c}"
        );
        assert_eq!(
            s.email_configured(),
            c["email_configured"].as_bool().unwrap()
        );
    }
}

#[test]
fn owner_profile_matches_python() {
    let v = vectors();
    let (mut ok, mut declined) = (0, 0);
    for c in v["profile"]["validate"].as_array().unwrap() {
        if c["out"].get("crash").is_some() {
            continue;
        }
        match owner_profile::validate(&c["in"]) {
            Ok(m) => {
                ok += 1;
                assert_eq!(json!({"ok": m}), c["out"], "{}", c["in"]);
            }
            Err(Outcome::Errors(e)) => {
                assert_eq!(json!({"errors": errors_json(&e)}), c["out"], "{}", c["in"])
            }
            Err(Outcome::Unsupported(_)) => declined += 1,
        }
    }
    assert!(ok > 150 && declined < 5, "{ok} {declined}");
    for z in v["profile"]["zones"].as_array().unwrap() {
        let r = owner_profile::validate(&json!({"timezone": z}));
        assert!(r.is_ok(), "Python accepts {z} but Rust refused it: {r:?}");
    }
    for c in v["profile"]["status"].as_array().unwrap() {
        let t = &c["tenant"];
        let got = owner_profile::website_channel_status(
            t["slug"].as_str(),
            t["site_url"].as_str(),
            t["voice_enabled"].as_bool().unwrap_or(false),
            c["verified"].as_str().unwrap(),
            if c["llm"].as_str().unwrap().is_empty() {
                c["xai"].as_str().unwrap()
            } else {
                c["llm"].as_str().unwrap()
            },
            c["xai"].as_str().unwrap(),
        );
        assert_eq!(got, c["out"], "{c}");
    }
}

#[test]
fn drafts_match_python() {
    let v = vectors();
    let d = &v["drafts"];
    for c in d["address"].as_array().unwrap() {
        let got = match drafts::address(c["in"].as_str().unwrap()) {
            Ok(a) => json!({"ok": a}),
            Err(e) => json!({"err": e}),
        };
        assert_eq!(got, c["out"], "{c}");
    }
    for c in d["subject"].as_array().unwrap() {
        assert_eq!(
            drafts::subject(c["in"].as_str().unwrap()),
            c["out"].as_str().unwrap(),
            "{c}"
        );
    }
    let mut with_call = 0;
    for c in d["propose"].as_array().unwrap() {
        let (sender, subj, body) = (
            c["sender"].as_str().unwrap(),
            c["subject"].as_str().unwrap(),
            c["body"].as_str().unwrap(),
        );
        assert_eq!(
            drafts::retrieval_query(subj, body),
            c["query"].as_str().unwrap()
        );
        let contents: Vec<&str> = c["contents"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| x.as_str().unwrap())
            .collect();
        let t = &c["tenant"];
        match drafts::propose_messages(
            t["name"].as_str().unwrap(),
            t["persona"].as_str(),
            &contents,
            sender,
            subj,
            body,
        ) {
            Err(e) => {
                assert_eq!(c["out"], json!({"err": e}));
                assert!(
                    c["call"].is_null(),
                    "no model call may happen for a bad sender"
                );
            }
            Ok(m) => {
                with_call += 1;
                assert_eq!(m, c["call"][0], "{c}");
                assert_eq!(
                    (&c["call"][1], &c["call"][2], &c["call"][3]),
                    (&Value::Null, &json!(0.2), &json!(450))
                );
                let got = match drafts::finish_reply(c["reply"].as_str()) {
                    Ok(r) => json!({"ok": r}),
                    Err(e) => json!({"err": e}),
                };
                assert_eq!(got, c["out"], "{c}");
            }
        }
    }
    assert!(with_call > 30);
    let mut created = 0;
    for c in d["create"].as_array().unwrap() {
        let i: Vec<&str> = c["in"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| x.as_str().unwrap())
            .collect();
        match drafts::create_args(i[0], i[1], i[2], i[3], i[4]) {
            Err(e) => assert_eq!(c["out"], json!({"err": e}), "{c}"),
            Ok(a) => {
                created += 1;
                assert_eq!(
                    c["out"]["args"],
                    json!(["t1", a[0], a[1], a[2], a[3], a[4]]),
                    "{c}"
                );
            }
        }
    }
    assert!(created > 10);
    let mut queued = 0;
    for c in d["approve"].as_array().unwrap() {
        let got = match drafts::approval_allowed(
            c["outbox"].as_bool().unwrap(),
            c["email"].as_bool().unwrap(),
        ) {
            Err(e) => {
                assert_eq!(c["out"], json!({"err": e}));
                assert!(
                    c["effects"].as_array().unwrap().is_empty(),
                    "nothing is read when email is off"
                );
                continue;
            }
            Ok(()) => {
                let row = (!c["row"].is_null()).then(|| DraftRow {
                    status: c["row"]["status"].as_str().unwrap(),
                    reply_body: c["row"]["reply_body"].as_str().unwrap(),
                    sender: c["row"]["sender"].as_str().unwrap(),
                    subject: c["row"]["subject"].as_str().unwrap(),
                });
                drafts::approve(9, row.as_ref())
            }
        };
        let eff = c["effects"].as_array().unwrap();
        assert_eq!(eff[0], json!(["fetchrow", "SELECT", [9, "t1"]]));
        match got {
            Err(e) => {
                assert_eq!(c["out"], json!({"err": e}));
                assert_eq!(eff.len(), 1);
            }
            Ok(Approval::Nothing) => {
                assert_eq!(c["out"], json!({"ok": null}));
                assert_eq!(eff.len(), 1);
            }
            Ok(Approval::Queue(a)) => {
                queued += 1;
                assert_eq!(eff.len(), 3);
                assert_eq!(
                    eff[1],
                    json!(["execute", "INSERT", ["t1", a[0], a[1], a[2], a[3]]]),
                    "{c}"
                );
                assert_eq!(eff[2], json!(["fetchrow", "UPDATE", [9, "t1"]]));
            }
        }
    }
    assert!(queued >= 3, "{queued}");
}

#[test]
fn tenants_match_python() {
    let v = vectors();
    let t = &v["tenants"];
    let mut updated = 0;
    for c in t["update"].as_array().unwrap() {
        let fields = c["fields"].as_object().unwrap();
        let (sql, args) = match tenants::update_plan("slug-1", fields).unwrap() {
            Some((s, a)) => (s, a),
            None => (
                "SELECT * FROM tenants WHERE slug = $1".to_string(),
                vec![json!("slug-1")],
            ),
        };
        assert_eq!(c["call"], json!([sql, args]), "{c}");
        if sql.starts_with("UPDATE") {
            updated += 1;
        }
        let out = if c["row"].is_null() {
            Value::Null
        } else {
            tenants::load(&c["row"]).unwrap()
        };
        assert_eq!(out, c["out"], "{c}");
    }
    assert!(updated > 100);
    for c in t["create"].as_array().unwrap() {
        let name = c["name"].as_str().unwrap();
        let base = telephony::slugify(match c["slug"].as_str() {
            Some(s) if !s.is_empty() => s,
            _ => name,
        });
        let calls = c["calls"].as_array().unwrap();
        let conflicts = c["conflicts"].as_u64().unwrap() as usize;
        assert_eq!(calls.len(), conflicts + 2);
        let site = calls[0][1][4].as_str();
        let mut fields = Map::new();
        fields.insert("allowed_origins".into(), json!(["https://o"]));
        fields.insert("persona".into(), json!("p"));
        for (i, call) in calls[..=conflicts].iter().enumerate() {
            let want = tenants::create_args(
                &tenants::slug_attempt(&base, i),
                name,
                "pk_fixed",
                "rt_fixed",
                site,
                &fields,
            );
            assert_eq!(call[1], Value::Array(want), "{c}");
        }
        assert_eq!(calls[conflicts + 1], json!(["UPDATE", ["i-1", "rt_fixed"]]));
    }
    for c in t["clone"].as_array().unwrap() {
        let copied = tenants::clone_fields(c["source"].as_object().unwrap());
        let ops = c["ops"].as_array().unwrap();
        assert_eq!(Value::Object(copied.clone()), ops[1][2], "{c}");
        assert_eq!(
            copied.keys().collect::<Vec<_>>(),
            ops[1][2].as_object().unwrap().keys().collect::<Vec<_>>(),
            "field order is the column order"
        );
        let want = if ops[1][3].is_null() {
            json!({"slug": "new-slug"})
        } else {
            ops[1][3].clone()
        };
        assert_eq!(want, c["out"]);
    }
    for c in t["view"].as_array().unwrap() {
        assert_eq!(tenants::public_view(&c["tenant"]), c["out"], "{c}");
    }
}
