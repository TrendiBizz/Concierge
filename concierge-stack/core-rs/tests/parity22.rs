//! Batch 22: `calendar_connection` outside the event state machine, against the live module with a temporary secret directory, a fake
//! `httpx` and a fake database.
use concierge_core::calendar_connection::{self as cc, Env, Failure, Notices, TokenReply, Worker};
use concierge_core::requests;
use serde_json::{json, Value};

fn vectors() -> Value {
    serde_json::from_str(include_str!("../parity/vectors22.json")).unwrap()
}

fn out(r: Result<Value, Failure>) -> Value {
    match r {
        Ok(v) => json!({"ok": v}),
        Err(Failure::Unavailable(m)) => json!({"unavailable": m}),
        Err(Failure::Http(s, d)) => json!({"http": [s, d]}),
        Err(Failure::Raises(t)) => json!({"raises": t}),
    }
}

struct Fake {
    configured: bool,
    app: Option<String>,
    token: Option<String>,
    saved: Option<Value>,
    provider: Value,
    state_found: bool,
    state: String,
    log: Vec<Value>,
    fx: Vec<Value>,
}

impl Env for Fake {
    fn credentials_dir_configured(&mut self) -> bool {
        self.configured
    }
    fn read_app_file(&mut self) -> Option<String> {
        self.app.clone()
    }
    fn read_token_file(&mut self, _t: &str) -> Option<String> {
        self.token.clone()
    }
    fn save_token(&mut self, _t: &str, v: &Value) {
        self.saved = Some(v.clone());
    }
    fn now(&mut self) -> f64 {
        1_800_000_000.0
    }
    fn post_token(&mut self, timeout: u32, data: Value) -> Option<TokenReply> {
        let url = "https://oauth2.googleapis.com/token";
        self.log.push(json!(["client", timeout]));
        self.log.push(json!(["post", url, data]));
        if self.provider == "error" {
            return None;
        }
        Some(TokenReply {
            status: self.provider[0].as_u64().unwrap() as u16,
            body: if self.provider[1] == "INVALID" {
                Err(())
            } else {
                Ok(self.provider[1].clone())
            },
        })
    }
    fn random_state(&mut self) -> String {
        self.state.clone()
    }
    fn store_state(&mut self, h: &str, t: &str, u: &str) {
        self.fx.push(json!([h, t, u]));
    }
    fn take_state(&mut self, h: &str, t: &str, u: &str) -> bool {
        self.fx.push(json!(["delete_state", [h, t, u]]));
        self.state_found
    }
    fn mark_connected(&mut self, t: &str) {
        self.fx.push(json!(["connect", [t]]));
    }
}

fn fake() -> Fake {
    Fake {
        configured: true,
        app: None,
        token: None,
        saved: None,
        provider: Value::Null,
        state_found: true,
        state: String::new(),
        log: vec![],
        fx: vec![],
    }
}

const TID: &str = "3f2504e0-4f89-41d3-9a0c-0305e82c3301";

#[test]
fn application_and_paths_match_python() {
    let v = vectors();
    for c in v["application"].as_array().unwrap() {
        let mut env = Fake {
            configured: c["configured"].as_bool().unwrap(),
            app: c["text"].as_str().map(String::from),
            ..fake()
        };
        assert_eq!(out(cc::application(&mut env)), c["out"], "{c}");
    }
    for c in v["token_path"].as_array().unwrap() {
        let got = match c["in"].as_str() {
            Some(t) => cc::canonical_tenant(t).map(|u| json!(format!("/secrets/{u}.json"))),
            None => Err(Failure::Raises("AttributeError")),
        };
        match (&got, c["out"].get("ok")) {
            (Ok(g), Some(w)) => assert_eq!(g, w, "{c}"),
            (Err(_), None) => {}
            // a non-string tenant id: Python's str() accepts it, so the port declines by never being given one
            _ => assert!(c["in"].as_str().is_none(), "{c} {got:?}"),
        }
    }
}

#[test]
fn access_token_matches_python() {
    let (mut fresh, mut refreshed) = (0, 0);
    for c in vectors()["access_token"].as_array().unwrap() {
        let mut env = fake();
        env.app = c["app_ok"].as_bool().unwrap().then(|| {
            json!({"client_id": "a", "client_secret": "b", "redirect_uri": "c"}).to_string()
        });
        env.token = match c["token_state"].as_str().unwrap() {
            "missing" => None,
            "invalid" => Some("not json".into()),
            _ => Some(c["token"].to_string()),
        };
        env.provider = c["provider"].clone();
        let got = out(cc::access_token(&mut env, TID).map(Value::from));
        assert_eq!(got, c["out"], "{c}");
        assert_eq!(Value::Array(env.log.clone()), c["log"], "{c}");
        let want_saved = if c["saved"].is_null() || c["saved"] == "UNPARSEABLE" {
            Value::Null
        } else {
            c["saved"].clone()
        };
        match (&env.saved, c["token_state"].as_str().unwrap()) {
            (Some(s), _) => assert_eq!(s, &want_saved, "{c}"),
            (None, "missing") | (None, "invalid") => {}
            (None, _) => assert!(
                c["saved"] == c["token"]
                    || c["saved"].is_null()
                    || c["saved"] == "UNPARSEABLE"
                    || c["saved"] == c["token"],
                "{c}"
            ),
        }
        fresh += (got.get("ok").is_some() && env.saved.is_none()) as i32;
        refreshed += env.saved.is_some() as i32;
    }
    assert!(fresh > 15 && refreshed > 20, "{fresh} {refreshed}");
}

#[test]
fn oauth_flows_match_python() {
    let v = vectors();
    let mut started = 0;
    for c in v["start"].as_array().unwrap() {
        let mut env = fake();
        env.app = c["app_ok"].as_bool().unwrap().then(|| json!({"client_id": "id & co", "client_secret": "b", "redirect_uri": "https://x.example/cb?a=b c"}).to_string());
        env.state = c["state"].as_str().unwrap().into();
        let got = out(cc::start(&mut env, TID, "u-1", c["role"].as_str().unwrap()));
        assert_eq!(got, c["out"], "{c}");
        if got.get("ok").is_some() {
            started += 1;
            assert_eq!(
                Value::Array(env.fx.clone()),
                json!([c["effects"][0]]),
                "{c}"
            );
        }
    }
    assert!(started >= 4, "{started}");
    let mut connected = 0;
    for c in v["finish"].as_array().unwrap() {
        let mut env = fake();
        env.app = c["app_ok"].as_bool().unwrap().then(|| {
            json!({"client_id": "a", "client_secret": "b", "redirect_uri": "c"}).to_string()
        });
        env.provider = c["provider"].clone();
        env.state_found = c["state_found"].as_bool().unwrap();
        let got = out(cc::finish(
            &mut env,
            TID,
            "u-1",
            c["role"].as_str().unwrap(),
            c["state"].as_str().unwrap(),
            "CODE",
        ));
        assert_eq!(got, c["out"], "{c}");
        assert_eq!(Value::Array(env.log.clone()), c["log"], "{c}");
        let want = if c["saved"].is_null() {
            Value::Null
        } else {
            c["saved"].clone()
        };
        assert_eq!(env.saved.clone().unwrap_or(Value::Null), want, "{c}");
        let fx: Vec<Value> = env.fx.iter().map(|e| json!([e[0], e[1]])).collect();
        if got.get("ok").is_some() {
            connected += 1;
            assert_eq!(fx.last().unwrap()[0], "connect");
        }
        assert_eq!(fx.len(), c["effects"].as_array().unwrap().len(), "{c}");
    }
    assert!(connected > 20, "{connected}");
    for c in v["finish_model"].as_array().unwrap() {
        let got = match requests::validate("OAuthFinish", &c["in"]) {
            Ok(m) => json!({"ok": m}),
            Err(requests::Outcome::Errors(e)) => {
                json!({"errors": concierge_core::pydantic::errors_json(&e)})
            }
            Err(_) => panic!("{c}"),
        };
        assert_eq!(got, c["out"], "{c}");
    }
}

struct W<'a> {
    c: &'a Value,
    fx: Vec<Value>,
}

impl Worker for W<'_> {
    fn due_appointments(&mut self) -> Vec<String> {
        self.fx.push(json!(["fetch", "sync"]));
        self.c["due"]
            .as_array()
            .unwrap()
            .iter()
            .map(|r| r["id"].as_str().unwrap().into())
            .collect()
    }
    fn unnotified(&mut self) -> Vec<String> {
        self.fx.push(json!(["fetch", "notices"]));
        self.c["pending"]
            .as_array()
            .unwrap()
            .iter()
            .map(|r| r["id"].as_str().unwrap().into())
            .collect()
    }
    fn sync_one(&mut self, id: &str) {
        self.fx.push(json!(["sync_one", [id]]));
    }
    fn notify_synced(&mut self, id: &str) {
        self.fx.push(json!(["notify_synced", [id]]));
    }
}

struct N<'a> {
    c: &'a Value,
    fx: Vec<Value>,
}

impl Notices for N<'_> {
    fn unnotified_appointment(&mut self, id: &str) -> Option<Value> {
        self.fx.push(json!(["appointment", [id]]));
        (!self.c["row"].is_null()).then(|| self.c["row"].clone())
    }
    fn tenant(&mut self, tid: &Value) -> Value {
        self.fx.push(json!(["tenant", [tid]]));
        json!({"id": tid})
    }
    fn lead(&mut self, tid: &Value, lid: &Value) -> Option<Value> {
        self.fx.push(json!(["lead", [tid, lid]]));
        (!self.c["lead"].is_null()).then(|| self.c["lead"].clone())
    }
    fn on_appointment_booked(&mut self, t: &Value, a: &Value, l: Option<&Value>) {
        self.fx.push(json!(["on_booked", [t, a, l]]));
    }
    fn mark_notice_done(&mut self, id: &str) {
        self.fx.push(json!(["done", [id]]));
    }
}

#[test]
fn worker_and_notices_match_python() {
    let v = vectors();
    for c in v["process"].as_array().unwrap() {
        let mut w = W { c, fx: vec![] };
        cc::process_once(&mut w);
        assert_eq!(Value::Array(w.fx), c["effects"], "{c}");
    }
    let mut sent = 0;
    for c in v["notify"].as_array().unwrap() {
        let mut n = N { c, fx: vec![] };
        cc::notify_synced(&mut n, "ap-1");
        assert_eq!(Value::Array(n.fx.clone()), c["effects"], "{c}");
        sent += n.fx.iter().any(|e| e[0] == "on_booked") as i32;
    }
    assert!(sent > 10);
}
