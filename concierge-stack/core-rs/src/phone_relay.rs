//! Port of the decision flows in `phone_relay.py`: inbound call registration, call setup, the consented recording start, the
//! recording callback, call finish and the bounded WebSocket relay session. The database, the telephony provider, the chat
//! engine and the socket are `Env` calls so the exact order and content of every effect can be compared with Python. Nothing here
//! places a call, buys a number or starts a recording without an explicit spoken consent, a business authorization and a
//! provider-confirmed receipt.
use crate::pyval::str_or_empty;
use crate::telephony::{is_call_sid, is_e164, is_recording_consent, is_recording_sid};
use crate::{py_strip, telephony};
use serde_json::{json, Value};

pub const MAX_TURNS: usize = 20;
pub const DECLINE: &str = "not_granted";

#[derive(Clone)]
pub struct Cfg {
    pub provider_legacy: bool,
    pub receptionist_enabled: bool,
    pub twilio_auth_token: String,
    pub public_base_url: String,
    pub recording_enabled: bool,
    pub twilio_account_sid: String,
}

impl Cfg {
    /// `configured()`.
    pub fn configured(&self) -> bool {
        self.provider_legacy
            && self.receptionist_enabled
            && !self.twilio_auth_token.is_empty()
            && self.public_base_url.starts_with("https://")
    }
}

/// The chat engine failed (any exception): the caller speaks a fixed apology.
#[derive(Debug)]
pub struct TurnFailed;

pub enum Provider {
    /// `httpx.HTTPError`.
    Error,
    /// Status and the parsed body (`Err(())` when the body is not JSON).
    Status(u16, Result<Value, ()>),
}

pub trait Env {
    // registration
    fn tenant_lookup(&mut self, to: &str) -> Option<Value>;
    fn authorized(&mut self, tenant_id: &str, channel: &str) -> bool;
    fn advisory_lock(&mut self, key: &str);
    fn previous_call(&mut self, sid: &str) -> Option<Value>;
    fn lock_tenant(&mut self, tenant_id: &str);
    fn calls_last_day(&mut self, tenant_id: &str) -> i64;
    fn insert_call(&mut self, tenant_id: &str, sid: &str, from: &str, to: &str);
    fn get_or_create(&mut self, tenant: &Value, session: &str) -> String;
    fn capture(
        &mut self,
        tenant: &Value,
        source: &str,
        message: &str,
        conversation_id: &str,
        phone: &str,
    );
    // setup
    fn setup_row(&mut self, sid: &str) -> Option<Value>;
    fn tenant_by_id(&mut self, tenant_id: &Value) -> Option<Value>;
    fn mark_in_progress(&mut self, sid: &str, session: &str);
    // recording
    fn claim_recording(&mut self, sid: &str, tenant_id: &str) -> bool;
    /// The provider client is opened before the request is built (and so before any URL error).
    fn provider_open(&mut self);
    fn provider_post(&mut self, url: &str, account: &str, token: &str, data: Value) -> Provider;
    fn store_receipt(&mut self, sid: &str, tenant_id: &str, recording_sid: &str);
    fn mark_recording_failed(&mut self, sid: &str, tenant_id: &str);
    fn update_recording(&mut self, sid: &str, recording_sid: &str, status: &str);
    fn finish_update(&mut self, sid: &str, status: &str);
    // relay session
    fn accept(&mut self);
    fn close(&mut self, code: u16);
    fn send(&mut self, message: Value);
    fn decline_recording(&mut self, sid: &str);
    fn run_turn(
        &mut self,
        tenant: &Value,
        session: &str,
        prompt: &str,
    ) -> Result<Option<String>, TurnFailed>;
    /// The setup check used by a live session (production: `record_setup(self, cfg, data)`).
    fn session_setup(&mut self, data: &Value) -> Option<Value>;
    /// The consented recording start used by a live session (production: `begin_recording(self, cfg, sid, tenant)`).
    fn session_begin_recording(&mut self, sid: &str, tenant: &Value) -> bool;
}

fn s(v: &Value, k: &str) -> String {
    v.get(k).and_then(Value::as_str).unwrap_or("").to_string()
}

/// `register_inbound`: `Err` is the PhoneError text.
pub fn register_inbound(env: &mut dyn Env, cfg: &Cfg, params: &Value) -> Result<Value, String> {
    if !cfg.configured() {
        return Err("Telephone reception disabled".into());
    }
    let (sid, to, from) = (s(params, "CallSid"), s(params, "To"), s(params, "From"));
    if !is_call_sid(&sid) || !is_e164(&to) {
        return Err("Invalid call identifier or destination".into());
    }
    let Some(row) = env.tenant_lookup(&to) else {
        return Err("This number has no enabled receptionist".into());
    };
    let mut tenant = row;
    let tid = tenant["id"].as_str().unwrap_or("").to_string();
    if !env.authorized(&tid, "telephone") {
        return Err("Business has not authorized telephone reception".into());
    }
    let offer = cfg.recording_enabled
        && env.authorized(&tid, "call_recording")
        && !cfg.twilio_account_sid.is_empty()
        && !cfg.twilio_auth_token.is_empty();
    tenant["_recording_offer"] = json!(offer);
    env.advisory_lock(&format!("phone:{sid}"));
    let previous = env.previous_call(&sid);
    if let Some(p) = &previous {
        if p["tenant_id"].as_str() != Some(&tid) {
            return Err("Call already registered for another business".into());
        }
    }
    env.lock_tenant(&tid);
    let used = env.calls_last_day(&tid);
    if previous.is_none() && used >= tenant["phone_daily_limit"].as_i64().unwrap_or(0) {
        return Err("Daily telephone limit reached".into());
    }
    env.insert_call(&tid, &sid, &from.chars().take(40).collect::<String>(), &to);
    let conv = env.get_or_create(&tenant, &sid);
    env.capture(
        &tenant,
        &sid,
        "Inbound telephone enquiry",
        &conv,
        if is_e164(&from) { &from } else { "" },
    );
    Ok(tenant)
}

/// `finish`: ignores anything that is not a call id.
pub fn finish(env: &mut dyn Env, sid: &str, status: &str) {
    if is_call_sid(sid) {
        env.finish_update(sid, &status.chars().take(40).collect::<String>());
    }
}

/// `recording_callback`.
pub fn recording_callback(env: &mut dyn Env, params: &Value) -> Result<(), &'static str> {
    let (sid, rec, status) = (
        s(params, "CallSid"),
        s(params, "RecordingSid"),
        s(params, "RecordingStatus"),
    );
    if !is_call_sid(&sid) || !is_recording_sid(&rec) {
        return Err("Invalid recording identifiers");
    }
    if !["in-progress", "completed", "absent", "failed"].contains(&status.as_str()) {
        return Err("Invalid recording status");
    }
    env.update_recording(&sid, &rec, &status);
    Ok(())
}

/// `_record_setup`: the tenant for a verified setup message, or `None` (the socket is closed).
pub fn record_setup(env: &mut dyn Env, cfg: &Cfg, data: &Value) -> Option<Value> {
    let sid = s(data, "callSid");
    let row = env.setup_row(&sid);
    let session = data.get("sessionId").and_then(Value::as_str);
    let (row, session) = match (row, session) {
        (Some(r), Some(sess)) if !sess.is_empty() => (r, sess),
        _ => return None,
    };
    if row["to_number"] != data.get("to").cloned().unwrap_or(Value::Null) {
        return None;
    }
    if crate::pyval::truthy(row.get("from_number"))
        && row["from_number"] != data.get("from").cloned().unwrap_or(Value::Null)
    {
        return None;
    }
    let mut tenant = env.tenant_by_id(&row["tenant_id"])?;
    env.mark_in_progress(&sid, &session.chars().take(100).collect::<String>());
    let tid = tenant["id"].as_str().unwrap_or("").to_string();
    let offer = cfg.recording_enabled
        && !cfg.twilio_account_sid.is_empty()
        && !cfg.twilio_auth_token.is_empty()
        && env.authorized(&tid, "call_recording");
    tenant["_recording_offer"] = json!(offer);
    Some(tenant)
}

#[derive(Debug, PartialEq)]
pub enum RecordingError {
    /// Python raised something the function does not catch (`AttributeError` on a non-object receipt).
    Raises,
}

/// `begin_recording`: start provider recording only after explicit opt-in. `Ok(true)` means the provider confirmed.
pub fn begin_recording(
    env: &mut dyn Env,
    cfg: &Cfg,
    sid: &str,
    tenant: &Value,
) -> Result<bool, RecordingError> {
    let tid = tenant["id"].as_str().unwrap_or("").to_string();
    if !is_call_sid(sid)
        || !cfg.recording_enabled
        || !cfg.twilio_account_sid.starts_with("AC")
        || cfg.twilio_account_sid.chars().count() != 34
        || cfg.twilio_auth_token.is_empty()
        || !env.authorized(&tid, "call_recording")
    {
        return Ok(false);
    }
    if !env.claim_recording(sid, &tid) {
        return Ok(false);
    }
    let url = format!(
        "https://api.twilio.com/2010-04-01/Accounts/{}/Calls/{sid}/Recordings.json",
        cfg.twilio_account_sid
    );
    // external_url may raise PhoneError inside the try block, which is handled like any provider failure
    env.provider_open();
    let callback = telephony::external_url(
        &cfg.public_base_url,
        "/api/v1/phone/twilio/recording",
        false,
    )
    .ok();
    let outcome: Result<String, ()> = match callback {
        None => Err(()),
        Some(cb) => match env.provider_post(
            &url,
            &cfg.twilio_account_sid,
            &cfg.twilio_auth_token,
            json!({"RecordingStatusCallback": cb, "RecordingStatusCallbackEvent": "completed absent", "RecordingChannels": "dual"}),
        ) {
            Provider::Error => Err(()),
            Provider::Status(st, body) => {
                if st != 200 && st != 201 {
                    Err(())
                } else {
                    match body {
                        Err(()) => Err(()),
                        Ok(Value::Object(m)) => {
                            let rec = m.get("sid").and_then(Value::as_str).unwrap_or("").to_string();
                            if is_recording_sid(&rec) { Ok(rec) } else { Err(()) }
                        }
                        Ok(_) => return Err(RecordingError::Raises),
                    }
                }
            }
        },
    };
    match outcome {
        Ok(rec) => {
            env.store_receipt(sid, &tid, &rec);
            Ok(true)
        }
        Err(()) => {
            env.mark_recording_failed(sid, &tid);
            Ok(false)
        }
    }
}

const FALLBACK_EMPTY: &str = "I could not find that answer. The team can follow up with you.";
const FALLBACK_ERROR: &str =
    "Sorry, I'm having trouble right now. Please contact the team through our website.";

/// `relay`: one bounded session over already-received events. `signature_ok` is the verified Twilio WSS signature and
/// `time_limit_reached` says the 600-second budget is spent at the top of the loop.
pub fn relay(
    env: &mut dyn Env,
    cfg: &Cfg,
    signature_ok: bool,
    events: &[Value],
    time_limit_reached: bool,
) {
    if !cfg.configured() || !signature_ok {
        env.close(1008);
        return;
    }
    env.accept();
    let mut tenant: Option<Value> = None;
    let mut session: Option<String> = None;
    let mut turns = 0usize;
    let mut awaiting = false;
    let mut it = events.iter();
    loop {
        if time_limit_reached {
            env.send(json!({"type": "end", "handoffData": "{\"reason\":\"time_limit\"}"}));
            break;
        }
        let Some(data) = it.next() else { break };
        let kind = data.get("type").and_then(Value::as_str);
        let Some(t) = tenant.clone() else {
            if kind != Some("setup") {
                env.close(1008);
                break;
            }
            match env.session_setup(data) {
                None => {
                    env.close(1008);
                    break;
                }
                Some(t) => {
                    awaiting = t
                        .get("_recording_offer")
                        .and_then(Value::as_bool)
                        .unwrap_or(false);
                    session = Some(match data.get("callSid") {
                        Some(Value::String(x)) => x.clone(),
                        Some(other) => other.to_string(),
                        None => String::new(),
                    });
                    tenant = Some(t);
                    continue;
                }
            }
        };
        let sess = session.clone().unwrap_or_default();
        if kind == Some("prompt") && data.get("last") == Some(&Value::Bool(true)) {
            let raw = str_or_empty(data.get("voicePrompt")).unwrap_or_default();
            let prompt: String = py_strip(&raw).chars().take(1000).collect();
            if prompt.is_empty() {
                continue;
            }
            if awaiting {
                awaiting = false;
                if is_recording_consent(&prompt) {
                    let ok = env.session_begin_recording(&sess, &t);
                    env.send(json!({"type": "text", "last": true, "token": if ok {
                        "Thank you. Recording has started. How can I help?"
                    } else {
                        "Recording could not be started, so this call will continue without recording. How can I help?"
                    }}));
                    continue;
                }
                env.decline_recording(&sess);
            }
            turns += 1;
            if turns > MAX_TURNS {
                env.send(json!({"type": "text", "token": "I have reached my call limit. Please contact the team directly.", "last": true}));
                env.send(json!({"type": "end", "handoffData": "{\"reason\":\"turn_limit\"}"}));
                break;
            }
            // respond(): record, ask the chat engine, never let a failure end the call
            let conv = env.get_or_create(&t, &sess);
            env.capture(&t, &sess, &prompt, &conv, "");
            let reply = match env.run_turn(&t, &sess, &prompt) {
                Ok(r) => {
                    let r = py_strip(r.as_deref().unwrap_or("")).to_string();
                    if r.is_empty() {
                        FALLBACK_EMPTY.to_string()
                    } else {
                        r
                    }
                }
                Err(TurnFailed) => {
                    env.send(json!({"type": "text", "token": FALLBACK_ERROR, "last": true}));
                    continue;
                }
            };
            env.send(json!({"type": "text", "token": reply.chars().take(1200).collect::<String>(), "last": true}));
        }
        // interrupt, error, info, dtmf and repeated setup events trigger nothing
    }
    if let Some(s) = session {
        finish(env, &s, "relay_ended");
    }
}
