//! Port of the decision rules in `config.py`: the owner-portal URL validator and the derived settings properties.
//! Environment loading stays in Python/pydantic-settings.
use crate::pyurl::{hostname, urlsplit, userinfo, Fail};
use serde_json::Value;

/// `valid_owner_portal` on any input value: `Ok(())`, or pydantic's error type. `Err(Fail::Unsupported)` is a declined case.
pub fn owner_portal(value: &Value) -> Result<(), Result<&'static str, Fail>> {
    let Value::String(s) = value else {
        return Err(Ok("string_type"));
    };
    let url = match urlsplit(s, "") {
        Ok(u) => u,
        Err(Fail::Value) => return Err(Ok("value_error")),
        Err(e) => return Err(Err(e)),
    };
    let host = hostname(&url.netloc);
    let local_http =
        url.scheme == "http" && matches!(host.as_deref(), Some("127.0.0.1" | "localhost" | "::1"));
    let (user, pass) = userinfo(&url.netloc);
    let bad = (url.scheme != "https" && !local_http)
        || host.is_none()
        || user.is_some_and(|u| !u.is_empty())
        || pass.is_some_and(|p| !p.is_empty())
        || !url.query.is_empty()
        || !url.fragment.is_empty()
        || url.path != "/owner-ui";
    if bad {
        Err(Ok("value_error"))
    } else {
        Ok(())
    }
}

pub struct Settings<'a> {
    pub xai_api_key: &'a str,
    pub llm_api_key: &'a str,
    pub voice_model: &'a str,
    pub xai_realtime_url: &'a str,
    pub sms_provider: &'a str,
    pub twilio_account_sid: &'a str,
    pub twilio_auth_token: &'a str,
    pub twilio_from_number: &'a str,
    pub twilio_messaging_service_sid: &'a str,
    pub smsgate_base_url: &'a str,
    pub smsgate_username: &'a str,
    pub smsgate_password: &'a str,
    pub smtp_host: &'a str,
    pub smtp_from: &'a str,
}

impl Settings<'_> {
    pub fn effective_llm_key(&self) -> &str {
        if self.llm_api_key.is_empty() {
            self.xai_api_key
        } else {
            self.llm_api_key
        }
    }

    pub fn voice_ws_url(&self) -> String {
        if self.voice_model.is_empty() {
            return self.xai_realtime_url.to_string();
        }
        let sep = if self.xai_realtime_url.contains('?') {
            "&"
        } else {
            "?"
        };
        format!("{}{}model={}", self.xai_realtime_url, sep, self.voice_model)
    }

    pub fn sms_configured(&self) -> bool {
        let name = if self.sms_provider.is_empty() {
            "none"
        } else {
            self.sms_provider
        };
        match crate::py_strip(name).to_lowercase().as_str() {
            "twilio" => {
                !self.twilio_account_sid.is_empty()
                    && !self.twilio_auth_token.is_empty()
                    && (!self.twilio_from_number.is_empty()
                        || !self.twilio_messaging_service_sid.is_empty())
            }
            "smsgate" => {
                !self.smsgate_base_url.is_empty()
                    && !self.smsgate_username.is_empty()
                    && !self.smsgate_password.is_empty()
            }
            _ => false,
        }
    }

    pub fn email_configured(&self) -> bool {
        !self.smtp_host.is_empty() && !self.smtp_from.is_empty()
    }
}
