//! Batch 17: the request models and pure helpers of `main.py` against the live Python classes and functions.
use concierge_core::pydantic::errors_json;
use concierge_core::requests::{self, Outcome};
use serde_json::{json, Value};

fn vectors() -> Value {
    serde_json::from_str(include_str!("../parity/vectors17.json")).unwrap()
}

#[test]
fn request_models_match_python() {
    let v = vectors();
    let (mut total, mut ok, mut declined) = (0, 0, 0);
    let mut declined_why = std::collections::BTreeMap::new();
    for (name, cases) in v["models"].as_object().unwrap() {
        for c in cases.as_array().unwrap() {
            total += 1;
            match requests::validate(name, &c["in"]) {
                Ok(m) => {
                    ok += 1;
                    assert_eq!(json!({"ok": m}), c["out"], "{name} {}", c["in"]);
                }
                Err(Outcome::Errors(e)) => assert_eq!(
                    json!({"errors": errors_json(&e)}),
                    c["out"],
                    "{name} {}",
                    c["in"]
                ),
                Err(Outcome::Unsupported(why)) => {
                    declined += 1;
                    *declined_why.entry(why).or_insert(0) += 1;
                }
            }
        }
    }
    assert!(total > 5000 && ok > 1800, "{total} {ok}");
    assert!(
        declined * 40 < total,
        "declined {declined} of {total}: {declined_why:?}"
    );
}

#[test]
fn helpers_match_python() {
    let v = vectors();
    let h = &v["helpers"];
    for c in h["origin"].as_array().unwrap() {
        assert_eq!(
            requests::origin_of(c["in"].as_str().unwrap()).unwrap(),
            c["out"].as_str().unwrap()
        );
    }
    for c in h["money"].as_array().unwrap() {
        assert_eq!(
            requests::money(c["in"].as_i64().unwrap()),
            c["out"].as_str().unwrap(),
            "{c}"
        );
    }
    for c in h["twiml"].as_array().unwrap() {
        assert_eq!(
            requests::twiml(c["in"].as_str().unwrap()),
            c["out"].as_str().unwrap(),
            "{c}"
        );
    }
    for c in h["snippet"].as_array().unwrap() {
        assert_eq!(
            requests::with_snippet(c["base"].as_str().unwrap(), &c["tenant"]),
            c["out"],
            "{c}"
        );
    }
    for c in h["campaign_view"].as_array().unwrap() {
        assert_eq!(requests::campaign_view(&c["in"]).unwrap(), c["out"], "{c}");
    }
    for c in h["audio"].as_array().unwrap() {
        let got = requests::private_audio_headers("f.x", c["mime"].as_str().unwrap());
        for (k, val) in got {
            if k == "content-disposition" {
                continue; // the filename differs per vector; the other headers are fixed
            }
            assert_eq!(c["headers"][&k].as_str().unwrap(), val, "{k}");
        }
    }
    let mut refused = 0;
    for c in h["origin_gate"].as_array().unwrap() {
        let allowed: Vec<&str> = c["allowed"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| x.as_str().unwrap())
            .collect();
        let got = match requests::origin_gate(
            &allowed,
            c["origin"].as_str(),
            c["base"].as_str().unwrap(),
        ) {
            Ok(()) => json!({"ok": true}),
            Err((s, d)) => {
                refused += 1;
                json!({"status": s, "detail": d})
            }
        };
        assert_eq!(got, c["out"], "{c}");
    }
    assert!(refused > 10);
    for c in h["rate"].as_array().unwrap() {
        let mut calls: Vec<Value> = vec![];
        let (ip_ok, sess_ok) = (
            c["ip_ok"].as_bool().unwrap(),
            c["sess_ok"].as_bool().unwrap(),
        );
        let log = std::cell::RefCell::new(&mut calls);
        let got = requests::rate_limit(
            c["client"].as_bool().unwrap().then_some("1.2.3.4"),
            c["session"].as_str(),
            &mut |k| {
                log.borrow_mut().push(json!(["ip", k]));
                ip_ok
            },
            &mut |k| {
                log.borrow_mut().push(json!(["session", k]));
                sess_ok
            },
        );
        let got = match got {
            Ok(()) => json!({"ok": true}),
            Err((s, d)) => json!({"status": s, "detail": d}),
        };
        assert_eq!(got, c["out"], "{c}");
        assert_eq!(Value::Array(calls), c["calls"], "{c}");
    }
}
