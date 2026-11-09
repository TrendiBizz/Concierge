//! Batch 19: `phone_relay` decision flows against the live module with a fake database, provider and WebSocket.
use concierge_core::phone_relay::{self as pr, Cfg, Env, Provider, RecordingError};
use serde_json::{json, Value};

fn vectors() -> Value {
    serde_json::from_str(include_str!("../parity/vectors19.json")).unwrap()
}

fn cfg(v: &Value) -> Cfg {
    Cfg {
        provider_legacy: v["phone_voice_provider"] == "legacy_twilio_tts",
        receptionist_enabled: v["phone_receptionist_enabled"].as_bool().unwrap(),
        twilio_auth_token: v["twilio_auth_token"].as_str().unwrap().into(),
        public_base_url: v["public_base_url"].as_str().unwrap().into(),
        recording_enabled: v["phone_recording_enabled"].as_bool().unwrap(),
        twilio_account_sid: v["twilio_account_sid"].as_str().unwrap().into(),
    }
}

/// Recording environment: every call is logged in the same shape the Python fakes use.
struct Fake<'a> {
    c: &'a Value,
    fx: Vec<Value>,
    sent: Vec<Value>,
}

impl Env for Fake<'_> {
    fn tenant_lookup(&mut self, to: &str) -> Option<Value> {
        self.fx.push(json!(["tenant_lookup", [to]]));
        (!self.c["row"].is_null()).then(|| self.c["row"].clone())
    }
    fn authorized(&mut self, t: &str, ch: &str) -> bool {
        self.fx.push(json!(["authorized", [t, ch]]));
        match &self.c["auth"] {
            Value::Bool(b) => *b,
            m => m[ch].as_bool().unwrap_or(false),
        }
    }
    fn advisory_lock(&mut self, key: &str) {
        self.fx
            .push(json!(["execute", "SELECT pg_advisory_xact_lock", [key]]));
    }
    fn previous_call(&mut self, sid: &str) -> Option<Value> {
        self.fx
            .push(json!(["fetchrow", "SELECT tenant_id FROM phone_ca", [sid]]));
        (!self.c["previous"].is_null()).then(|| self.c["previous"].clone())
    }
    fn lock_tenant(&mut self, t: &str) {
        self.fx.push(json!([
            "execute",
            "SELECT id FROM tenants WHERE id=$1 FOR U",
            [t]
        ]));
    }
    fn calls_last_day(&mut self, t: &str) -> i64 {
        self.fx
            .push(json!(["fetchval", "SELECT count(*) FROM phone_cal", [t]]));
        self.c["used"].as_i64().unwrap()
    }
    fn insert_call(&mut self, t: &str, sid: &str, from: &str, to: &str) {
        self.fx.push(json!([
            "execute",
            "INSERT INTO phone_calls",
            [t, sid, from, to]
        ]));
    }
    fn get_or_create(&mut self, tenant: &Value, session: &str) -> String {
        if self.c.get("events").is_some() {
            self.fx.push(json!(["get_or_create", [session]]));
        } else {
            self.fx.push(json!([
                "get_or_create",
                [tenant["id"], session, "phone", null, null]
            ]));
        }
        "conv-1".into()
    }
    fn capture(&mut self, tenant: &Value, source: &str, message: &str, conv: &str, phone: &str) {
        if self.c.get("events").is_some() {
            self.fx.push(json!(["capture", [source, message]]));
        } else {
            self.fx.push(json!(["capture", [tenant["id"], "phone", source, message, {"conversation_id": conv, "phone": phone}]]));
        }
    }
    fn setup_row(&mut self, sid: &str) -> Option<Value> {
        self.fx.push(json!(["fetchrow", [sid]]));
        (!self.c["row"].is_null()).then(|| self.c["row"].clone())
    }
    fn tenant_by_id(&mut self, tid: &Value) -> Option<Value> {
        self.fx.push(json!(["get_by_id", [tid]]));
        (!self.c["tenant"].is_null()).then(|| self.c["tenant"].clone())
    }
    fn mark_in_progress(&mut self, sid: &str, session: &str) {
        self.fx.push(json!(["execute", [sid, session]]));
    }
    fn claim_recording(&mut self, sid: &str, t: &str) -> bool {
        self.fx.push(json!(["claim", [sid, t]]));
        !self.c["updated"].is_null()
    }
    fn provider_open(&mut self) {
        self.fx.push(json!(["client", [12.0, false]]));
    }
    fn provider_post(&mut self, url: &str, account: &str, token: &str, data: Value) -> Provider {
        self.fx.push(json!(["post", [url, [account, token], data]]));
        let p = &self.c["provider"];
        if p[0] == "error" {
            return Provider::Error;
        }
        Provider::Status(
            p[1].as_u64().unwrap() as u16,
            if p[2] == "INVALID" {
                Err(())
            } else {
                Ok(p[2].clone())
            },
        )
    }
    fn store_receipt(&mut self, sid: &str, t: &str, rec: &str) {
        self.fx.push(json!([
            "execute",
            "recording_sid=COALESCE(recording_sid,$3)",
            [sid, t, rec]
        ]));
    }
    fn mark_recording_failed(&mut self, sid: &str, t: &str) {
        self.fx
            .push(json!(["execute", "recording_status='failed'", [sid, t]]));
    }
    fn update_recording(&mut self, sid: &str, rec: &str, status: &str) {
        self.fx.push(json!([sid, rec, status]));
    }
    fn finish_update(&mut self, sid: &str, status: &str) {
        if self.c.get("events").is_some() {
            self.fx.push(json!(["finish", [sid, status]]));
        } else {
            self.fx.push(json!([sid, status]));
        }
    }
    fn accept(&mut self) {
        self.sent.push(json!(["accept"]));
    }
    fn close(&mut self, code: u16) {
        self.sent.push(json!(["close", code]));
    }
    fn send(&mut self, m: Value) {
        self.sent.push(json!(["send", m]));
    }
    fn decline_recording(&mut self, sid: &str) {
        self.fx.push(json!(["decline", [sid, pr::DECLINE]]));
    }
    fn session_setup(&mut self, data: &Value) -> Option<Value> {
        // the Python relay test replaces `_record_setup`: it logs the ids and answers from the scenario
        self.fx.push(json!([
            "record_setup",
            [data["callSid"], data["sessionId"]]
        ]));
        self.c["record_ok"]
            .as_bool()
            .unwrap()
            .then(|| json!({"id": "t-1", "name": "Acme", "_recording_offer": self.c["offer"]}))
    }
    fn session_begin_recording(&mut self, sid: &str, _t: &Value) -> bool {
        self.fx.push(json!(["begin_recording", [sid]]));
        self.c["begin_ok"].as_bool().unwrap()
    }
    fn run_turn(
        &mut self,
        _t: &Value,
        session: &str,
        prompt: &str,
    ) -> Result<Option<String>, pr::TurnFailed> {
        self.fx
            .push(json!(["run_turn", [session, "phone", prompt]]));
        match self.c["mode"].as_str().unwrap() {
            "raise" => Err(pr::TurnFailed),
            "none" => Ok(None),
            "empty" => Ok(Some("   ".into())),
            _ => Ok(Some(format!("Answer: {prompt}{}", "y".repeat(1300)))),
        }
    }
}

fn fake(c: &Value) -> Fake<'_> {
    Fake {
        c,
        fx: vec![],
        sent: vec![],
    }
}

#[test]
fn registration_matches_python() {
    let mut ok = 0;
    for c in vectors()["register"].as_array().unwrap() {
        let mut env = fake(c);
        let got = match pr::register_inbound(&mut env, &cfg(&c["cfg"]), &c["params"]) {
            Ok(t) => {
                ok += 1;
                json!({"ok": t})
            }
            Err(e) => json!({"err": e}),
        };
        assert_eq!(got, c["out"], "{c}");
        assert_eq!(Value::Array(env.fx), c["effects"], "{c}");
    }
    assert!(ok >= 15, "{ok}");
}

#[test]
fn finish_and_callback_match_python() {
    let v = vectors();
    for c in v["finish"].as_array().unwrap() {
        let mut env = fake(c);
        pr::finish(
            &mut env,
            c["sid"].as_str().unwrap(),
            c["status"].as_str().unwrap(),
        );
        let want: Vec<Value> = c["effects"].as_array().unwrap().clone();
        assert_eq!(env.fx, want, "{c}");
    }
    let mut accepted = 0;
    for c in v["callback"].as_array().unwrap() {
        let mut env = fake(c);
        let got = match pr::recording_callback(&mut env, &c["params"]) {
            Ok(()) => {
                accepted += 1;
                json!({"ok": true})
            }
            Err(e) => json!({"err": e}),
        };
        assert_eq!(got, c["out"], "{c}");
        assert_eq!(Value::Array(env.fx), c["effects"], "{c}");
    }
    assert!(accepted >= 6, "{accepted}");
}

#[test]
fn setup_matches_python() {
    let mut ok = 0;
    for c in vectors()["setup"].as_array().unwrap() {
        let mut env = fake(c);
        let got = pr::record_setup(&mut env, &cfg(&c["cfg"]), &c["data"]);
        if got.is_some() {
            ok += 1;
        }
        assert_eq!(got.unwrap_or(Value::Null), c["out"], "{c}");
        assert_eq!(Value::Array(env.fx), c["effects"], "{c}");
    }
    assert!(ok > 50, "{ok}");
}

#[test]
fn consented_recording_matches_python() {
    let (mut started, mut raised) = (0, 0);
    for c in vectors()["recording"].as_array().unwrap() {
        let mut env = fake(c);
        let got = match pr::begin_recording(
            &mut env,
            &cfg(&c["cfg"]),
            c["sid"].as_str().unwrap(),
            &json!({"id": "t-1"}),
        ) {
            Ok(b) => {
                started += b as i32;
                json!({"ok": b})
            }
            Err(RecordingError::Raises) => {
                raised += 1;
                json!({"raises": "AttributeError"})
            }
        };
        assert_eq!(got, c["out"], "{c}");
        assert_eq!(Value::Array(env.fx), c["effects"], "{c}");
    }
    assert!(started >= 20 && raised >= 1, "{started} {raised}");
}

#[test]
fn relay_sessions_match_python() {
    let (mut long, mut limited, mut closed) = (0, 0, 0);
    for c in vectors()["relay"].as_array().unwrap() {
        let mut env = fake(c);
        let events = c["events"].as_array().unwrap();
        pr::relay(
            &mut env,
            &cfg(&c["cfg"]),
            c["sig_ok"].as_bool().unwrap(),
            events,
            c["max_seconds"] == 0,
        );
        assert_eq!(Value::Array(env.sent.clone()), c["sent"], "{c}");
        assert_eq!(Value::Array(env.fx.clone()), c["effects"], "{c}");
        long += (env.sent.len() > 5) as i32;
        limited += env
            .sent
            .iter()
            .any(|m| m.to_string().contains("turn_limit")) as i32;
        closed += env.sent.iter().any(|m| m[0] == "close") as i32;
    }
    assert!(
        long > 20 && limited >= 3 && closed > 10,
        "{long} {limited} {closed}"
    );
}
