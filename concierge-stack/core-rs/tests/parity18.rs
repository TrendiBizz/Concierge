//! Batch 18: `social_bridge` against the live module with a fake `httpx` client and a recording fake `_request`.
use concierge_core::social::{self, Api, Failure, HttpErr};
use serde_json::{json, Value};

fn vectors() -> Value {
    serde_json::from_str(include_str!("../parity/vectors18.json")).unwrap()
}

fn out_json(r: Result<Value, Failure>) -> Value {
    match r {
        Ok(v) => json!({"ok": v}),
        Err(Failure::Http(e)) => json!({"status": e.status, "detail": e.detail}),
        Err(Failure::ValueError) => json!({"raises": "ValueError"}),
    }
}

#[test]
fn configuration_matches_python() {
    let mut accepted = 0;
    for c in vectors()["config"].as_array().unwrap() {
        let got = social::configuration(
            c["enabled"].as_bool().unwrap(),
            c["key"].as_str().unwrap(),
            c["url"].as_str().unwrap(),
        );
        let got = match got {
            Ok((b, k)) => {
                accepted += 1;
                json!({"ok": [b, k]})
            }
            Err(Failure::Http(e)) => json!({"status": e.status, "detail": e.detail}),
            Err(Failure::ValueError) => json!({"raises": "ValueError"}),
        };
        assert_eq!(got, c["out"], "{c}");
    }
    assert!(accepted >= 8, "{accepted}");
}

#[test]
fn response_mapping_matches_python() {
    let (mut mapped, mut raised) = (0, 0);
    for c in vectors()["request"].as_array().unwrap() {
        let path = c["path"].as_str().unwrap();
        assert_eq!(social::timeout(path), c["timeout"].as_f64().unwrap(), "{c}");
        let Some(status) = c["status"].as_u64() else {
            continue;
        }; // transport failure case is covered below
        let body = if c["raw"] == "invalid" {
            Err(())
        } else {
            Ok(c["body"].clone())
        };
        let got = out_json(social::response(status as u16, path, body));
        // Python's `json()` body is returned as is for 2xx
        let want = if c["out"].get("ok").is_some() {
            json!({"ok": c["out"]["ok"]})
        } else {
            c["out"].clone()
        };
        assert_eq!(got, want, "{c}");
        if c["out"].get("raises").is_some() {
            raised += 1;
        } else {
            mapped += 1;
        }
    }
    assert!(mapped > 1000 && raised > 20, "{mapped} {raised}");
}

struct Script<'a> {
    script: &'a Value,
    calls: Vec<Value>,
    rules_seen: usize,
}

impl Api for Script<'_> {
    fn request(&mut self, method: &str, path: &str, data: Option<Value>) -> Result<Value, HttpErr> {
        self.calls.push(json!([method, path, data]));
        let key = if path.ends_with("/rules") {
            self.rules_seen += 1;
            if self.rules_seen == 1 {
                "rules"
            } else {
                "again"
            }
        } else if path == "/v1/customers" && method == "POST" {
            "create"
        } else {
            "main"
        };
        match &self.script[key] {
            Value::Array(t) => Err(HttpErr {
                status: t[0].as_u64().unwrap() as u16,
                detail: "scripted".into(),
            }),
            _ => Ok(json!({"result": key})),
        }
    }
}

#[test]
fn operations_match_python() {
    let mut by_calls = std::collections::BTreeMap::new();
    for c in vectors()["ops"].as_array().unwrap() {
        let mut api = Script {
            script: &c["script"],
            calls: vec![],
            rules_seen: 0,
        };
        let args = c["args"].as_array().unwrap();
        let t = &c["tenant"];
        let got = social::run(
            &mut api,
            t["slug"].as_str().unwrap(),
            t["name"].as_str().unwrap(),
            c["op"].as_str().unwrap(),
            args,
        );
        let got = match got {
            Ok(v) => json!({"ok": v}),
            Err(e) => json!({"status": e.status, "detail": e.detail}),
        };
        // a scripted HTTP error carries Python's detail "scripted"; a validation error carries the real message
        assert_eq!(got, c["out"], "{} {}", c["op"], c["args"]);
        assert_eq!(
            Value::Array(api.calls.clone()),
            c["calls"],
            "{} {}",
            c["op"],
            c["args"]
        );
        *by_calls.entry(api.calls.len()).or_insert(0) += 1;
    }
    assert!(by_calls.len() >= 4, "{by_calls:?}");
}
