//! Port of the outbox worker in `outbox.py` (`_deliver`, `process_once`): the durable follow-up queue. Every database write and
//! every send goes through `Env`, so the exact decisions and their order are comparable with Python. Nothing is sent here: a
//! sender only runs after authorization is rechecked at delivery time, opt-outs, the campaign kill switch and quiet hours.
use crate::schedule::next_allowed_send;
use chrono::{DateTime, Utc};
use chrono_tz::Tz;
use serde_json::{json, Value};

pub const MAX_ATTEMPTS: i64 = 3;
const OWNER_KINDS: [&str; 1] = ["owner_alert"];

pub enum SmsSend {
    Sent,
    AwaitingReceipt,
    ReconciliationRequired,
    Failed(String),
}

pub struct Settings {
    pub quiet_start_hour: u32,
    pub quiet_end_hour: u32,
    pub email_configured: bool,
}

pub trait Env {
    fn recover_stale(&mut self);
    fn claim(&mut self) -> Vec<Value>;
    fn tenant(&mut self, tenant_id: &str) -> Result<Option<Value>, String>;
    fn authorized(&mut self, tenant_id: &str, permission: &str) -> bool;
    fn opted_out(&mut self, tenant_id: &str, contact: &str) -> bool;
    fn sender_ready(&mut self, tenant: &Value) -> bool;
    fn now(&mut self) -> DateTime<Utc>;
    fn requeue_quiet(&mut self, id: i64, send_at: DateTime<Utc>);
    fn send_sms(
        &mut self,
        to: &str,
        body: &str,
        from: Option<&str>,
        request_key: &str,
        outbox_id: i64,
    ) -> SmsSend;
    fn mark_awaiting_receipt(&mut self, id: i64);
    fn unsubscribe_url(&mut self, tenant_id: &str, to: &str) -> String;
    fn send_email(
        &mut self,
        to: &str,
        subject: &str,
        body: &str,
        headers: Option<Value>,
    ) -> Result<(), String>;
    fn finish(&mut self, id: i64, status: &str, error: &str);
    fn retry_later(&mut self, id: i64, error: &str, minutes: i64);
}

fn truthy_str(v: &Value, k: &str) -> bool {
    crate::pyval::truthy(v.get(k))
}

fn skip(env: &mut dyn Env, id: i64, why: &str) -> Result<(), String> {
    env.finish(id, "skipped", why);
    Ok(())
}

/// `_deliver`: `Err(text)` is the exception text Python would catch in `process_once`.
pub fn deliver(env: &mut dyn Env, cfg: &Settings, row: &Value) -> Result<(), String> {
    let id = row["id"].as_i64().unwrap_or(0);
    let tid = row["tenant_id"].as_str().unwrap_or("").to_string();
    let kind = row["kind"].as_str().unwrap_or("");
    let channel = row["channel"].as_str().unwrap_or("");
    let to = row["to_addr"].as_str().unwrap_or("").to_string();
    let Some(tenant) = env.tenant(&tid)? else {
        return skip(env, id, "tenant_deleted");
    };
    if kind == "email_secretary_reply"
        && (!truthy_str(&tenant, "email_auto_reply") || !env.authorized(&tid, "email_read"))
    {
        return skip(env, id, "email_secretary_authorization_revoked");
    }
    let owner_kind = OWNER_KINDS.contains(&kind);
    if (!owner_kind || channel == "sms") && (channel == "email" || channel == "sms") {
        let permission = if channel == "email" {
            "email_send"
        } else {
            "sms_send"
        };
        if !env.authorized(&tid, permission) {
            return skip(env, id, "channel_authorization_missing");
        }
    }
    if !owner_kind && env.opted_out(&tid, &to) {
        return skip(env, id, "opted_out");
    }
    if truthy_str(row, "campaign_id") && !truthy_str(&tenant, "campaigns_enabled") {
        return skip(env, id, "campaigns_disabled");
    }
    match channel {
        "sms" => {
            if !env.sender_ready(&tenant) {
                return skip(env, id, "sms_not_configured");
            }
            let tz: Tz = tenant["timezone"]
                .as_str()
                .unwrap_or("UTC")
                .parse()
                .map_err(|_| "No time zone found".to_string())?;
            let now = env.now();
            let allowed = next_allowed_send(tz, now, cfg.quiet_start_hour, cfg.quiet_end_hour);
            if allowed > env.now() {
                env.requeue_quiet(id, allowed);
                return Ok(());
            }
            match env.send_sms(
                &to,
                row["body"].as_str().unwrap_or(""),
                tenant["sms_from"].as_str(),
                &format!("outbox:{id}"),
                id,
            ) {
                SmsSend::Sent => {}
                SmsSend::AwaitingReceipt => {
                    env.mark_awaiting_receipt(id);
                    return Ok(());
                }
                SmsSend::ReconciliationRequired => {
                    env.finish(id, "held", "Phone SMS requires owner reconciliation");
                    return Ok(());
                }
                SmsSend::Failed(e) => return Err(e),
            }
        }
        "email" => {
            if !cfg.email_configured {
                return skip(env, id, "email_not_configured");
            }
            let headers = if truthy_str(row, "campaign_id") {
                let link = env.unsubscribe_url(&tid, &to);
                Some(
                    json!({"List-Unsubscribe": format!("<{link}>"), "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}),
                )
            } else {
                None
            };
            let subject = match row["subject"].as_str() {
                Some(s) if !s.is_empty() => s.to_string(),
                _ => format!("Message from {}", tenant["name"].as_str().unwrap_or("")),
            };
            env.send_email(&to, &subject, row["body"].as_str().unwrap_or(""), headers)?;
        }
        other => {
            env.finish(id, "failed", &format!("unknown channel {other}"));
            return Ok(());
        }
    }
    env.finish(id, "sent", "");
    Ok(())
}

/// `process_once`: returns how many rows were claimed.
pub fn process_once(env: &mut dyn Env, cfg: &Settings) -> usize {
    env.recover_stale();
    let rows = env.claim();
    for row in &rows {
        if let Err(e) = deliver(env, cfg, row) {
            let id = row["id"].as_i64().unwrap_or(0);
            let attempts = row["attempts"].as_i64().unwrap_or(0);
            if attempts >= MAX_ATTEMPTS {
                env.finish(id, "failed", &e);
            } else {
                env.retry_later(id, &e, attempts * 2);
            }
        }
    }
    rows.len()
}
