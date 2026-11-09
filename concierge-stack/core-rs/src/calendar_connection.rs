//! Port of `calendar_connection.py` outside the event state machine (which lives in `calendar.rs`): the operator-provided Google
//! application file, per-business token files, access-token refresh, the owner OAuth start/finish/disconnect flows, the booking
//! notice and the worker loop. Files, the Google token endpoint and the database are `Env` calls. Secrets stay in the private
//! secret directory: nothing here returns a token to a caller other than the access token used for one provider request.
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

pub const SCOPES: [&str; 2] = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.freebusy",
];

#[derive(Debug, PartialEq)]
pub enum Failure {
    /// `CalendarUnavailable(message)`.
    Unavailable(&'static str),
    Http(u16, String),
    /// Python raises an exception nothing catches (`KeyError`, `ValueError`, `HTTPError`, ...).
    Raises(&'static str),
}

pub struct TokenReply {
    pub status: u16,
    /// `Err(())` when the body is not JSON.
    pub body: Result<Value, ()>,
}

pub trait Env {
    fn credentials_dir_configured(&mut self) -> bool;
    fn read_app_file(&mut self) -> Option<String>;
    fn read_token_file(&mut self, tenant_id: &str) -> Option<String>;
    fn save_token(&mut self, tenant_id: &str, token: &Value);
    fn now(&mut self) -> f64;
    /// POST to the Google token endpoint; `None` is an `httpx.HTTPError`.
    fn post_token(&mut self, timeout: u32, data: Value) -> Option<TokenReply>;
    fn random_state(&mut self) -> String;
    fn store_state(&mut self, hash: &str, tenant_id: &str, user_id: &str);
    fn take_state(&mut self, hash: &str, tenant_id: &str, user_id: &str) -> bool;
    fn mark_connected(&mut self, tenant_id: &str);
}

/// `application()`.
pub fn application(env: &mut dyn Env) -> Result<Value, Failure> {
    const MSG: &str = "Calendar connection is not configured";
    if !env.credentials_dir_configured() {
        return Err(Failure::Unavailable(MSG));
    }
    let Some(text) = env.read_app_file() else {
        return Err(Failure::Unavailable(MSG));
    };
    let Ok(data) = serde_json::from_str::<Value>(&text) else {
        return Err(Failure::Unavailable(MSG));
    };
    let Some(map) = data.as_object() else {
        return Err(Failure::Raises("AttributeError"));
    };
    if ["client_id", "client_secret", "redirect_uri"]
        .iter()
        .all(|k| crate::pyval::truthy(map.get(*k)))
    {
        Ok(data)
    } else {
        Err(Failure::Unavailable(MSG))
    }
}

/// `str(UUID(str(tenant_id)))`: Python strips braces, `urn:uuid:` and every hyphen, then needs 32 hex digits.
pub fn canonical_tenant(tenant_id: &str) -> Result<String, Failure> {
    let t = tenant_id.strip_prefix("urn:").unwrap_or(tenant_id);
    let t = t.strip_prefix("uuid:").unwrap_or(t);
    let t = t.trim_matches(|c| c == '{' || c == '}');
    let hex: String = t.chars().filter(|c| *c != '-').collect();
    if hex.len() != 32 || !hex.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err(Failure::Raises("ValueError"));
    }
    let h = hex.to_lowercase();
    Ok(format!(
        "{}-{}-{}-{}-{}",
        &h[0..8],
        &h[8..12],
        &h[12..16],
        &h[16..20],
        &h[20..32]
    ))
}

/// `access_token(tenant_id)`.
pub fn access_token(env: &mut dyn Env, tenant_id: &str) -> Result<String, Failure> {
    let tid = canonical_tenant(tenant_id)?;
    if !env.credentials_dir_configured() {
        return Err(Failure::Unavailable(
            "Calendar connection is not configured",
        ));
    }
    let reconnect = Failure::Unavailable("Reconnect the business calendar");
    let mut token: Value = match env
        .read_token_file(&tid)
        .and_then(|t| serde_json::from_str(&t).ok())
    {
        Some(v) => v,
        None => return Err(reconnect),
    };
    let Some(map) = token.as_object_mut() else {
        return Err(Failure::Raises("AttributeError"));
    };
    let expires = map.get("expires_at").and_then(Value::as_f64).unwrap_or(0.0);
    if expires > env.now() + 60.0 {
        return map
            .get("access_token")
            .and_then(Value::as_str)
            .map(String::from)
            .ok_or(Failure::Raises("KeyError"));
    }
    let app = application(env)?;
    let reply = env
        .post_token(
            15,
            json!({"client_id": app["client_id"], "client_secret": app["client_secret"],
                   "refresh_token": map.get("refresh_token").cloned().filter(|v| crate::pyval::truthy(Some(v))).unwrap_or(json!("")), "grant_type": "refresh_token"}),
        )
        .ok_or(Failure::Raises("HTTPError"))?;
    if reply.status != 200 {
        return Err(Failure::Unavailable(
            "Calendar authorization needs reconnection",
        ));
    }
    let fresh = reply.body.map_err(|_| Failure::Raises("ValueError"))?;
    let Some(fresh_map) = fresh.as_object() else {
        return Err(Failure::Raises("TypeError"));
    };
    for (k, v) in fresh_map {
        map.insert(k.clone(), v.clone());
    }
    let expires_in = fresh_map
        .get("expires_in")
        .and_then(Value::as_f64)
        .unwrap_or(3600.0);
    map.insert("expires_at".into(), json!(env.now() + expires_in));
    let saved = Value::Object(map.clone());
    env.save_token(&tid, &saved);
    saved["access_token"]
        .as_str()
        .map(String::from)
        .ok_or(Failure::Raises("KeyError"))
}

fn rank(role: &str) -> i32 {
    match role {
        "viewer" => 0,
        "editor" => 1,
        _ => 2,
    }
}

fn require_owner(role: &str) -> Result<(), Failure> {
    if rank(role) < 2 {
        return Err(Failure::Http(403, "Insufficient permissions".into()));
    }
    Ok(())
}

fn sha256_hex(s: &str) -> String {
    Sha256::digest(s.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// `urllib.parse.quote_plus`.
fn quote_plus(s: &str) -> String {
    let mut out = String::new();
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'_' | b'.' | b'-' | b'~' => {
                out.push(b as char)
            }
            b' ' => out.push('+'),
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

/// `start`: begin the owner's Google authorization.
pub fn start(
    env: &mut dyn Env,
    tenant_id: &str,
    user_id: &str,
    role: &str,
) -> Result<Value, Failure> {
    require_owner(role)?;
    let app = match application(env) {
        Ok(a) => a,
        Err(Failure::Unavailable(m)) => return Err(Failure::Http(503, m.into())),
        Err(e) => return Err(e),
    };
    let state = env.random_state();
    env.store_state(&sha256_hex(&state), tenant_id, user_id);
    let mut scopes = SCOPES.to_vec();
    scopes.sort();
    let pairs = [
        (
            "client_id",
            app["client_id"].as_str().unwrap_or("").to_string(),
        ),
        (
            "redirect_uri",
            app["redirect_uri"].as_str().unwrap_or("").to_string(),
        ),
        ("response_type", "code".to_string()),
        ("scope", scopes.join(" ")),
        ("state", state.clone()),
        ("access_type", "offline".to_string()),
        ("prompt", "consent".to_string()),
    ];
    let query: Vec<String> = pairs
        .iter()
        .map(|(k, v)| format!("{k}={}", quote_plus(v)))
        .collect();
    Ok(
        json!({"state": state, "authorization_url": format!("https://accounts.google.com/o/oauth2/v2/auth?{}", query.join("&"))}),
    )
}

/// `finish`: exchange the code. `state`/`code` already passed `OAuthFinish` validation.
pub fn finish(
    env: &mut dyn Env,
    tenant_id: &str,
    user_id: &str,
    role: &str,
    state: &str,
    code: &str,
) -> Result<Value, Failure> {
    require_owner(role)?;
    if !env.take_state(&sha256_hex(state), tenant_id, user_id) {
        return Err(Failure::Http(
            409,
            "Calendar authorization expired or belongs to another session".into(),
        ));
    }
    let app = application(env)?;
    let reply = env
        .post_token(
            20,
            json!({"client_id": app["client_id"], "client_secret": app["client_secret"], "redirect_uri": app["redirect_uri"], "code": code, "grant_type": "authorization_code"}),
        )
        .ok_or(Failure::Raises("HTTPError"))?;
    if reply.status != 200 {
        return Err(Failure::Http(
            400,
            "Google rejected calendar authorization; reconnect".into(),
        ));
    }
    let token = reply.body.map_err(|_| Failure::Raises("ValueError"))?;
    let Some(map) = token.as_object() else {
        return Err(Failure::Raises("AttributeError"));
    };
    let granted: Vec<&str> = map
        .get("scope")
        .and_then(Value::as_str)
        .unwrap_or("")
        .split_whitespace()
        .collect();
    if !SCOPES.iter().all(|s| granted.contains(s))
        || !crate::pyval::truthy(map.get("refresh_token"))
    {
        return Err(Failure::Http(
            400,
            "Authorize calendar events and availability with offline access".into(),
        ));
    }
    let mut saved: Map<String, Value> = map.clone();
    let expires_in = map
        .get("expires_in")
        .and_then(Value::as_f64)
        .unwrap_or(3600.0);
    saved.insert("expires_at".into(), json!(env.now() + expires_in));
    let tid = canonical_tenant(tenant_id)?;
    env.save_token(&tid, &Value::Object(saved));
    env.mark_connected(tenant_id);
    Ok(json!({"connected": true, "provider": "google", "calendar_id": "primary"}))
}

pub trait Worker {
    fn due_appointments(&mut self) -> Vec<String>;
    fn unnotified(&mut self) -> Vec<String>;
    fn sync_one(&mut self, id: &str);
    fn notify_synced(&mut self, id: &str);
}

/// `process_once`.
pub fn process_once(w: &mut dyn Worker) {
    for id in w.due_appointments() {
        w.sync_one(&id);
        w.notify_synced(&id);
    }
    for id in w.unnotified() {
        w.notify_synced(&id);
    }
}

pub trait Notices {
    fn unnotified_appointment(&mut self, id: &str) -> Option<Value>;
    fn tenant(&mut self, tenant_id: &Value) -> Value;
    fn lead(&mut self, tenant_id: &Value, lead_id: &Value) -> Option<Value>;
    fn on_appointment_booked(&mut self, tenant: &Value, appointment: &Value, lead: Option<&Value>);
    fn mark_notice_done(&mut self, id: &str);
}

/// `notify_synced`: tell the owner and visitor once a provider-accepted booking exists.
pub fn notify_synced(n: &mut dyn Notices, id: &str) {
    let Some(row) = n.unnotified_appointment(id) else {
        return;
    };
    let tenant = n.tenant(&row["tenant_id"]);
    let lead = n.lead(&row["tenant_id"], &row["lead_id"]);
    n.on_appointment_booked(&tenant, &row, lead.as_ref());
    n.mark_notice_done(id);
}
