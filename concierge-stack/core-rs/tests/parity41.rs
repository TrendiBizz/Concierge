//! Batch 41: owner-portal reads. Expected values are the output of the live `owner_auth.current_user`,
//! `owner_onboarding.overview` and `main.owner_channel_readiness` (`parity/gen_vectors41.py` -> `parity/vectors41.json`).
use concierge_core::owner_portal::{self as op, Device, PortalSettings};
use serde_json::{json, Map, Value};

fn vectors() -> Value {
    serde_json::from_str(include_str!("../parity/vectors41.json")).unwrap()
}

#[test]
fn bearer_header_rule_matches_python() {
    for c in vectors()["headers"].as_array().unwrap() {
        let h = c["header"].as_str().unwrap();
        match op::bearer_token(h) {
            Ok(token) => {
                assert!(c["reached_db"].as_bool().unwrap(), "{h:?} must be refused");
                assert_eq!(
                    concierge_core::owner_auth::digest(token),
                    c["digest"].as_str().unwrap(),
                    "{h:?}"
                );
                assert_eq!(c["detail"], "Session expired or invalid");
            }
            Err(detail) => {
                assert!(
                    !c["reached_db"].as_bool().unwrap(),
                    "{h:?} must reach the lookup"
                );
                assert_eq!(detail, c["detail"].as_str().unwrap(), "{h:?}");
            }
        }
    }
}

fn settings(v: &Value) -> PortalSettings {
    let s = |k: &str| v.get(k).and_then(Value::as_str).unwrap_or("").to_string();
    let b = |k: &str| v.get(k).and_then(Value::as_bool).unwrap_or(false);
    PortalSettings {
        llm_api_key: s("llm_api_key"),
        xai_api_key: s("xai_api_key"),
        website_verified_tenants: s("website_verified_tenants"),
        phone_verified_tenants: s("phone_verified_tenants"),
        phone_receptionist_enabled: b("phone_receptionist_enabled"),
        // `config.Settings` defaults
        phone_voice_provider: v
            .get("phone_voice_provider")
            .and_then(Value::as_str)
            .unwrap_or("grok")
            .to_string(),
        xai_sip_connections: s("xai_sip_connections"),
        twilio_auth_token: s("twilio_auth_token"),
        twilio_account_sid: s("twilio_account_sid"),
        twilio_from_number: s("twilio_from_number"),
        twilio_messaging_service_sid: s("twilio_messaging_service_sid"),
        public_base_url: v
            .get("public_base_url")
            .and_then(Value::as_str)
            .unwrap_or("http://localhost:8000")
            .to_string(),
        sms_provider: v
            .get("sms_provider")
            .and_then(Value::as_str)
            .unwrap_or("twilio")
            .to_string(),
        smsgate_base_url: s("smsgate_base_url"),
        smsgate_username: s("smsgate_username"),
        smsgate_password: s("smsgate_password"),
        smtp_host: s("smtp_host"),
        smtp_from: s("smtp_from"),
        social_service_enabled: b("social_service_enabled"),
        voice_recording_enabled: b("voice_recording_enabled"),
        phone_recording_enabled: b("phone_recording_enabled"),
        inbound_cloudflare_enabled: b("inbound_cloudflare_enabled"),
    }
}

#[test]
fn overview_and_readiness_match_python() {
    let v = vectors();
    let (mut ok, mut failed, mut telephone, mut paired) = (0, 0, 0, 0);
    for c in v["cases"].as_array().unwrap() {
        let s = settings(&c["settings"]);
        let numbers: Vec<(String, bool)> = c["numbers"]
            .as_array()
            .unwrap()
            .iter()
            .map(|n| (n[0].as_str().unwrap().to_string(), n[1].as_bool().unwrap()))
            .collect();
        let device = c["device"].as_object().map(|d| Device {
            last_seen: d["last_seen"]
                .as_f64()
                .map(|t| (t * 1_000_000.0).round() as i64),
            verified: d["verified"].as_bool().unwrap(),
            inbound_verified: d["inbound_verified"].as_bool().unwrap(),
        });
        let now = (c["now"].as_f64().unwrap() * 1_000_000.0).round() as i64;
        let got = op::overview(&c["tenant"], &numbers, device.as_ref(), now, &s);
        let want = &c["overview"];
        match got {
            Err(_) => {
                assert!(want.get("error").is_some(), "overview must not fail: {c}");
                assert!(c["readiness"].get("error").is_some());
                failed += 1;
            }
            Ok(ov) => {
                assert_eq!(&ov, &want["out"], "overview for {c}");
                ok += 1;
                telephone += usize::from(ov["channels"]["telephone"]["configured"] == json!(true));
                paired += usize::from(ov["channels"]["sms"]["connection"] == json!("paired phone"));
                let declarations: Map<String, Value> = c["declarations"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|d| (d[0].as_str().unwrap().to_string(), d[1].clone()))
                    .collect();
                let mut all = Map::new();
                for key in concierge_core::channel_auth::CHANNELS {
                    let authorized = declarations.get(key).is_some_and(|a| a == &json!(true));
                    all.insert(key.to_string(), json!({"authorized": authorized}));
                }
                assert_eq!(
                    op::readiness(&ov, &all, &s),
                    c["readiness"]["out"],
                    "readiness for {c}"
                );
            }
        }
    }
    assert!(
        ok > 300 && failed > 0 && telephone > 10 && paired > 20,
        "{ok} {failed} {telephone} {paired}"
    );
}
