//! Owner-portal reads that decide something rather than just select rows: the Bearer header rule of
//! `owner_auth.current_user`, the onboarding `overview` and the channel `readiness` report of `main.owner_channel_readiness`.
//! Inputs are plain values (the tenant row, phone numbers, the paired SMS phone, settings) so the rules can be held to the
//! live Python functions by `tests/parity41.rs`.
use crate::{channel_auth, owner_profile, py_strip, pyval};
use serde_json::{json, Map, Value};

/// The settings the onboarding overview and readiness report read (`config.Settings` field names).
#[derive(Default, Clone)]
pub struct PortalSettings {
    pub llm_api_key: String,
    pub xai_api_key: String,
    pub website_verified_tenants: String,
    pub phone_verified_tenants: String,
    pub phone_receptionist_enabled: bool,
    pub phone_voice_provider: String,
    pub xai_sip_connections: String,
    pub twilio_auth_token: String,
    pub twilio_account_sid: String,
    pub twilio_from_number: String,
    pub twilio_messaging_service_sid: String,
    pub public_base_url: String,
    pub sms_provider: String,
    pub smsgate_base_url: String,
    pub smsgate_username: String,
    pub smsgate_password: String,
    pub smtp_host: String,
    pub smtp_from: String,
    pub social_service_enabled: bool,
    pub voice_recording_enabled: bool,
    pub phone_recording_enabled: bool,
    pub inbound_cloudflare_enabled: bool,
}

impl PortalSettings {
    fn core(&self) -> crate::settings::Settings<'_> {
        crate::settings::Settings {
            xai_api_key: &self.xai_api_key,
            llm_api_key: &self.llm_api_key,
            voice_model: "",
            xai_realtime_url: "",
            sms_provider: &self.sms_provider,
            twilio_account_sid: &self.twilio_account_sid,
            twilio_auth_token: &self.twilio_auth_token,
            twilio_from_number: &self.twilio_from_number,
            twilio_messaging_service_sid: &self.twilio_messaging_service_sid,
            smsgate_base_url: &self.smsgate_base_url,
            smsgate_username: &self.smsgate_username,
            smsgate_password: &self.smsgate_password,
            smtp_host: &self.smtp_host,
            smtp_from: &self.smtp_from,
        }
    }
}

/// The paired SMS phone row: `last_seen` as microseconds since the epoch.
pub struct Device {
    pub last_seen: Option<i64>,
    pub verified: bool,
    pub inbound_verified: bool,
}

/// `current_user`'s header rule. `Ok(token)` is what gets hashed and looked up; `Err` is the 401 detail. Starlette hands the
/// header over as text, `partition(" ")` splits at the FIRST space only (so `Bearer  x` has the token ` x`), the scheme is
/// compared case-insensitively and the limit of 256 counts characters.
pub fn bearer_token(authorization: &str) -> Result<&str, &'static str> {
    let (scheme, token) = authorization.split_once(' ').unwrap_or((authorization, ""));
    if scheme.to_lowercase() != "bearer" || token.is_empty() || token.chars().count() > 256 {
        return Err("Bearer authentication required");
    }
    Ok(token)
}

/// A lower-case hyphenated UUID, the only spelling `str(uuid.UUID(key))` maps back onto itself.
fn canonical_uuid(s: &str) -> bool {
    s.len() == 36
        && s.bytes().enumerate().all(|(i, b)| {
            if [8, 13, 18, 23].contains(&i) {
                b == b'-'
            } else {
                b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
            }
        })
}

/// `phone_sip.configured_for_tenant` for a tenant slug and its numbers `(e164, enabled)`. Every failure Python swallows
/// (bad JSON, a non-object, an item that is not an object, an invalid id) means "not configured".
pub fn sip_configured(s: &PortalSettings, slug: Option<&str>, numbers: &[(String, bool)]) -> bool {
    if !s.phone_receptionist_enabled || s.xai_api_key.is_empty() || s.phone_voice_provider != "grok"
    {
        return false;
    }
    let text = if s.xai_sip_connections.is_empty() {
        "{}"
    } else {
        &s.xai_sip_connections
    };
    let Ok(Value::Object(configs)) = serde_json::from_str::<Value>(text) else {
        return false;
    };
    configs.iter().any(|(ident, item)| {
        // `str(uuid.UUID(ident))` is looked up again as a key, so only a canonical lower-case id is ever found
        if !canonical_uuid(ident) {
            return false;
        }
        let Some(item) = item.as_object() else {
            return false;
        };
        if !["enabled", "tenant", "number", "signing_secret"]
            .iter()
            .all(|k| pyval::truthy(item.get(*k)))
        {
            return false;
        }
        item["tenant"].as_str().is_some()
            && item["tenant"].as_str() == slug
            && numbers
                .iter()
                .any(|(e164, enabled)| *enabled && item["number"].as_str() == Some(e164.as_str()))
    })
}

fn text(tenant: &Value, key: &str) -> Value {
    match tenant.get(key) {
        Some(v) if pyval::truthy(Some(v)) => v.clone(),
        _ => json!(""),
    }
}

/// `owner_onboarding.overview`. `Err` is the exception Python raises for a tenant dict without a `name` (a `KeyError`).
pub fn overview(
    tenant: &Value,
    numbers: &[(String, bool)],
    device: Option<&Device>,
    now_micros: i64,
    s: &PortalSettings,
) -> Result<Value, &'static str> {
    let name = tenant.get("name").ok_or("KeyError")?;
    let slug = tenant.get("slug").and_then(Value::as_str);
    let core = s.core();
    let device_online = device
        .and_then(|d| d.last_seen)
        .is_some_and(|seen| now_micros - seen < 300_000_000);
    let device_sms = tenant.get("sms_transport").and_then(Value::as_str) == Some("device");
    let relay_configured = s.phone_voice_provider == "legacy_twilio_tts"
        && s.phone_receptionist_enabled
        && !s.twilio_auth_token.is_empty()
        && s.public_base_url.starts_with("https://");
    let telephone_ready = pyval::truthy(tenant.get("phone_enabled"))
        && numbers.iter().any(|(_, enabled)| *enabled)
        && (relay_configured || sip_configured(s, slug, numbers));
    let phone_verified = slug.is_some_and(|sl| {
        s.phone_verified_tenants
            .split(',')
            .map(py_strip)
            .any(|v| !v.is_empty() && v == sl)
    });
    let mut channels = owner_profile::website_channel_status(
        slug,
        tenant.get("site_url").and_then(Value::as_str),
        pyval::truthy(tenant.get("voice_enabled")),
        &s.website_verified_tenants,
        core.effective_llm_key(),
        &s.xai_api_key,
    )
    .as_object()
    .cloned()
    .unwrap_or_default();
    channels.insert(
        "telephone".into(),
        json!({"configured": telephone_ready, "registered_numbers": numbers.len(),
               "verified": telephone_ready && phone_verified}),
    );
    channels.insert(
        "email".into(),
        json!({"configured": pyval::truthy(tenant.get("notify_email")) && core.email_configured(),
               "verified": false}),
    );
    channels.insert(
        "sms".into(),
        json!({"configured": pyval::truthy(tenant.get("sms_enabled"))
                  && (if device_sms { device_online } else { core.sms_configured() }),
               "verified": device_sms && device_online
                  && device.is_some_and(|d| d.verified && d.inbound_verified),
               "connection": if device_sms { "paired phone" } else { "carrier gateway" }}),
    );
    channels.insert(
        "social".into(),
        json!({"configured": s.social_service_enabled, "verified": false}),
    );
    channels.insert(
        "crm".into(),
        json!({"configured": true, "verified": true, "built_in": true}),
    );
    Ok(json!({
        "business": {
            "name": name,
            "site_url": text(tenant, "site_url"),
            "greeting": text(tenant, "greeting"),
            "voice_enabled": pyval::truthy(tenant.get("voice_enabled")),
            "native_booking": pyval::truthy(tenant.get("native_booking")),
            "slot_minutes": tenant.get("slot_minutes").cloned().unwrap_or(json!(30)),
            "business_hours": tenant.get("business_hours").cloned().unwrap_or(json!({})),
            "email_auto_reply": pyval::truthy(tenant.get("email_auto_reply")),
            "notify_phone": text(tenant, "notify_phone"),
            "notify_email": text(tenant, "notify_email"),
            "timezone": match tenant.get("timezone") {
                Some(v) if pyval::truthy(Some(v)) => v.clone(),
                _ => json!("Pacific/Auckland"),
            },
        },
        "channels": channels,
        "customer_activation_enabled": false,
    }))
}

/// `owner_channel_readiness`, from the overview and the stored declarations (`channel_authorization.authorizations`).
pub fn readiness(overview: &Value, declarations: &Map<String, Value>, s: &PortalSettings) -> Value {
    let configured = |channel: &str| pyval::truthy(overview["channels"][channel].get("configured"));
    let mut checks = Map::new();
    checks.insert("telephone".into(), json!(configured("telephone")));
    checks.insert(
        "call_recording".into(),
        json!(
            (s.voice_recording_enabled && configured("website_voice"))
                || (s.phone_recording_enabled
                    && !s.twilio_account_sid.is_empty()
                    && !s.twilio_auth_token.is_empty())
        ),
    );
    checks.insert("email_read".into(), json!(s.inbound_cloudflare_enabled));
    checks.insert("email_send".into(), json!(configured("email")));
    checks.insert("sms_read".into(), json!(configured("sms")));
    checks.insert("sms_send".into(), json!(configured("sms")));
    checks.insert("social".into(), json!(configured("social")));
    json!({
        "business": overview["business"]["name"],
        "channels": channel_auth::readiness(declarations, &checks),
        "customer_activation_enabled": false,
    })
}
