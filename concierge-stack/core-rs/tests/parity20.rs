//! Batch 20: the outbox worker against the live `outbox.process_once` with a fixed clock and recording collaborators.
use chrono::DateTime;
use concierge_core::outbox::{self, Env, Settings, SmsSend};
use serde_json::{json, Value};

struct Fake<'a> {
    c: &'a Value,
    fx: Vec<Value>,
    t: i64,
}

fn trunc(s: &str) -> String {
    s.chars().take(500).collect()
}

impl Env for Fake<'_> {
    fn recover_stale(&mut self) {
        self.fx.push(json!(["execute", "status = 'pending'", []]));
    }
    fn claim(&mut self) -> Vec<Value> {
        self.fx.push(json!(["claim", []]));
        self.c["rows"].as_array().unwrap().clone()
    }
    fn tenant(&mut self, tid: &str) -> Result<Option<Value>, String> {
        self.fx.push(json!(["tenant", [tid]]));
        Ok((!self.c["tenant"].is_null()).then(|| self.c["tenant"].clone()))
    }
    fn authorized(&mut self, tid: &str, p: &str) -> bool {
        self.fx.push(json!(["authorized", [tid, p]]));
        self.c["script"]["auth"][p].as_bool().unwrap()
    }
    fn opted_out(&mut self, tid: &str, contact: &str) -> bool {
        self.fx.push(json!(["opted_out", [tid, contact]]));
        self.c["script"]["opted_out"].as_bool().unwrap()
    }
    fn sender_ready(&mut self, _t: &Value) -> bool {
        self.fx.push(json!(["sender_ready", []]));
        self.c["script"]["ready"].as_bool().unwrap()
    }
    fn now(&mut self) -> chrono::DateTime<chrono::Utc> {
        DateTime::from_timestamp(self.t, 0).unwrap()
    }
    fn requeue_quiet(&mut self, id: i64, at: chrono::DateTime<chrono::Utc>) {
        self.fx.push(json!([
            "execute",
            "status = 'pending', attempts = attempts - 1, send_at = $2",
            [id, at.format("%Y-%m-%dT%H:%M:%S+00:00").to_string()]
        ]));
    }
    fn send_sms(
        &mut self,
        to: &str,
        body: &str,
        from: Option<&str>,
        key: &str,
        id: i64,
    ) -> SmsSend {
        self.fx.push(json!(["send_sms", [to, body, from, key, id]]));
        match self.c["script"]["sms"].as_str().unwrap() {
            "awaiting" => SmsSend::AwaitingReceipt,
            "recon" => SmsSend::ReconciliationRequired,
            "boom" => SmsSend::Failed("sms provider down".into()),
            _ => SmsSend::Sent,
        }
    }
    fn mark_awaiting_receipt(&mut self, id: i64) {
        self.fx
            .push(json!(["execute", "status='awaiting_receipt'", [id]]));
    }
    fn unsubscribe_url(&mut self, tid: &str, to: &str) -> String {
        self.fx.push(json!(["unsub_url", [tid, to]]));
        format!("https://u.example/{to}")
    }
    fn send_email(
        &mut self,
        to: &str,
        subject: &str,
        body: &str,
        headers: Option<Value>,
    ) -> Result<(), String> {
        self.fx
            .push(json!(["send_email", [to, subject, body, headers]]));
        match self.c["script"]["email"].as_str().unwrap() {
            "boom" => Err("smtp refused".into()),
            "long" => Err("e".repeat(700)),
            _ => Ok(()),
        }
    }
    fn finish(&mut self, id: i64, status: &str, error: &str) {
        self.fx.push(json!([
            "execute",
            "status = $2, last_error = $3, sent_at = CASE WHEN $2 = 'sent",
            [id, status, trunc(error)]
        ]));
    }
    fn retry_later(&mut self, id: i64, error: &str, minutes: i64) {
        self.fx.push(json!([
            "execute",
            "status = 'pending', last_error = $2, send_at = now() + $3 * ",
            [id, trunc(error), minutes]
        ]));
    }
}

#[test]
fn worker_matches_python() {
    let all: Vec<Value> = serde_json::from_str(include_str!("../parity/vectors20.json")).unwrap();
    let (mut sent, mut skipped, mut quiet, mut retried, mut failed) = (0, 0, 0, 0, 0);
    for c in &all {
        let mut env = Fake {
            c,
            fx: vec![],
            t: c["now"].as_i64().unwrap(),
        };
        let cfg = Settings {
            quiet_start_hour: c["cfg"]["sms_quiet_start_hour"].as_u64().unwrap() as u32,
            quiet_end_hour: c["cfg"]["sms_quiet_end_hour"].as_u64().unwrap() as u32,
            email_configured: c["cfg"]["email_configured"].as_bool().unwrap(),
        };
        let n = outbox::process_once(&mut env, &cfg);
        assert_eq!(n as u64, c["out"].as_u64().unwrap());
        assert_eq!(Value::Array(env.fx.clone()), c["effects"], "{c}");
        for e in &env.fx {
            let s = e.to_string();
            sent += (e[0] == "send_sms" || e[0] == "send_email") as i32;
            skipped += s.contains("\"skipped\"") as i32;
            quiet += s.contains("attempts = attempts - 1") as i32;
            retried += s.contains("send_at = now()") as i32;
            failed += s.contains("\"failed\"") as i32;
        }
    }
    assert!(
        sent > 100 && skipped > 100 && quiet > 20 && retried > 20 && failed > 5,
        "{sent} {skipped} {quiet} {retried} {failed}"
    );
}
