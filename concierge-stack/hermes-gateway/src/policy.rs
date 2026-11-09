//! Policy validation of a Hermes plan. Fail closed: the first problem rejects the whole plan, so nothing partial runs.
//! Every input here is server-derived (capability and `PolicyContext`); nothing is trusted because the model said it.
use crate::capability::Capability;
use crate::ops::Op;
use crate::plan::{Channel, HermesPlan};
use chrono::{DateTime, Utc};
use chrono_tz::Tz;
use concierge_core::contact::{contact_key, is_email, normalize_phone};
use concierge_core::{guard, schedule};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};

const SMS_MAX: usize = 1500;
const EMAIL_MAX: usize = 4000;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Autonomy {
    /// Record what Hermes would do; execute nothing.
    Shadow,
    /// Prepare drafts; a person approves every customer-visible send.
    DraftReview,
    /// Routine factual replies may send themselves; anything else still needs a person.
    AutoRoutine,
}

#[derive(Clone, Debug)]
pub struct WorkflowPolicy {
    pub autonomy: Autonomy,
    pub min_confidence: f64,
}

#[derive(Clone, Debug)]
pub struct PolicyContext {
    pub tenant_id: String,
    pub case_id: String,
    pub case_version: u64,
    /// A person has taken over: nothing customer-facing may execute.
    pub automation_paused: bool,
    pub timezone: Tz,
    pub default_country_code: String,
    pub email_send_authorized: bool,
    pub sms_send_authorized: bool,
    /// `contact_key` values already verified as belonging to this case. A recipient outside this set is refused.
    pub case_contacts: HashSet<String>,
    /// `contact_key` values that opted out.
    pub suppressed: HashSet<String>,
    /// Business-approved text a quoted price must appear in.
    pub knowledge_evidence: String,
    pub workflow: WorkflowPolicy,
    /// approval reference -> fingerprint of the exact content a person approved.
    pub approvals: HashMap<String, String>,
}

#[derive(Debug, PartialEq, Eq)]
pub struct Reject {
    pub code: &'static str,
    pub detail: String,
}

fn rej<T>(code: &'static str, detail: impl Into<String>) -> Result<T, Reject> {
    Err(Reject {
        code,
        detail: detail.into(),
    })
}

#[derive(Debug, PartialEq, Eq)]
pub struct ValidatedAction {
    pub op: Op,
    pub idempotency_key: String,
    pub dedupe_key: String,
    pub fingerprint: String,
    pub case_version: u64,
}

#[derive(Debug, PartialEq, Eq)]
pub enum DeliveryMode {
    /// Autonomy is Shadow: record only.
    ShadowOnly,
    NeedsApproval,
    /// Either a person approved exactly this content, or routine policy allows it.
    Auto,
}

#[derive(Debug, PartialEq, Eq)]
pub struct Delivery {
    pub channel: Channel,
    pub recipient: String,
    pub subject: String,
    pub body: String,
    pub send_at: DateTime<Utc>,
    pub fingerprint: String,
    pub dedupe_key: String,
    pub mode: DeliveryMode,
}

#[derive(Debug, PartialEq, Eq)]
pub struct Validated {
    pub actions: Vec<ValidatedAction>,
    pub delivery: Option<Delivery>,
    pub shadow: bool,
}

fn sha(parts: &[&str]) -> String {
    let mut h = Sha256::new();
    for p in parts {
        h.update((p.len() as u64).to_be_bytes()); // length-prefixed: ("ab","c") != ("a","bc")
        h.update(p.as_bytes());
    }
    h.finalize().iter().map(|b| format!("{b:02x}")).collect()
}

/// What a person approves is exactly this: tenant, case, channel, recipient, subject and body.
pub fn delivery_fingerprint(
    tenant: &str,
    case: &str,
    channel: Channel,
    recipient: &str,
    subject: &str,
    body: &str,
) -> String {
    let ch = match channel {
        Channel::Email => "email",
        Channel::Sms => "sms",
    };
    sha(&["delivery", tenant, case, ch, recipient, subject, body])
}

fn canonical(v: &Value) -> String {
    match v {
        Value::Object(m) => {
            let mut keys: Vec<&String> = m.keys().collect();
            keys.sort();
            format!(
                "{{{}}}",
                keys.iter()
                    .map(|k| format!(
                        "{}:{}",
                        serde_json::to_string(k).unwrap(),
                        canonical(&m[*k])
                    ))
                    .collect::<Vec<_>>()
                    .join(",")
            )
        }
        Value::Array(a) => format!(
            "[{}]",
            a.iter().map(canonical).collect::<Vec<_>>().join(",")
        ),
        other => other.to_string(),
    }
}

/// A model must not name another business or case, even inside nested parameters.
fn scope_violation(v: &Value, cap: &Capability) -> Option<String> {
    match v {
        Value::Object(m) => {
            for (k, val) in m {
                let own = match k.as_str() {
                    "tenant_id" | "business_id" => Some(cap.tenant_id.as_str()),
                    "case_id" => Some(cap.case_id.as_str()),
                    _ => None,
                };
                if let Some(own) = own {
                    if val.as_str() != Some(own) {
                        return Some(k.clone());
                    }
                }
                if let Some(found) = scope_violation(val, cap) {
                    return Some(found);
                }
            }
            None
        }
        Value::Array(a) => a.iter().find_map(|x| scope_violation(x, cap)),
        _ => None,
    }
}

fn valid_key(k: &str) -> bool {
    (1..=128).contains(&k.len())
        && k.bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"-_:.".contains(&b))
}

pub fn validate_plan(
    cap: &Capability,
    plan: &HermesPlan,
    ctx: &PolicyContext,
    now: i64,
) -> Result<Validated, Reject> {
    if ctx.tenant_id != cap.tenant_id || ctx.case_id != cap.case_id {
        return rej(
            "scope_mismatch",
            "policy context does not belong to the capability",
        );
    }
    let shadow = ctx.workflow.autonomy == Autonomy::Shadow;
    let mut actions = Vec::new();
    for a in &plan.proposed_actions {
        let Some(op) = Op::parse(&a.op) else {
            return rej("unknown_operation", a.op.clone());
        };
        if !cap.allows(op) {
            return rej("operation_not_granted", op.name());
        }
        if let Some(k) = scope_violation(&a.params, cap) {
            return rej("scope_override", format!("params name a different {k}"));
        }
        if ctx.automation_paused && op.affects_customer() {
            return rej("automation_paused", op.name());
        }
        if op.is_mutating() {
            if !valid_key(&a.idempotency_key) {
                return rej("bad_idempotency_key", op.name());
            }
            if a.expected_case_version != ctx.case_version {
                return rej(
                    "stale_case",
                    format!(
                        "planned against v{}, case is v{}",
                        a.expected_case_version, ctx.case_version
                    ),
                );
            }
        }
        actions.push(ValidatedAction {
            op,
            idempotency_key: a.idempotency_key.clone(),
            dedupe_key: format!(
                "hermes:{}:{}:{}",
                cap.tenant_id, cap.case_id, a.idempotency_key
            ),
            fingerprint: sha(&[
                "action",
                op.name(),
                &canonical(&a.params),
                &a.expected_case_version.to_string(),
            ]),
            case_version: a.expected_case_version,
        });
    }
    let delivery = match &plan.customer_draft {
        Some(d) => Some(validate_delivery(cap, plan, d, ctx, now)?),
        None => None,
    };
    Ok(Validated {
        actions,
        delivery,
        shadow,
    })
}

fn validate_delivery(
    cap: &Capability,
    plan: &HermesPlan,
    d: &crate::plan::CustomerDraft,
    ctx: &PolicyContext,
    now: i64,
) -> Result<Delivery, Reject> {
    if ctx.automation_paused {
        return rej("automation_paused", "a person has taken over this case");
    }
    let authorized = match d.channel {
        Channel::Email => ctx.email_send_authorized,
        Channel::Sms => ctx.sms_send_authorized,
    };
    if !authorized {
        return rej(
            "channel_not_authorized",
            "the business has not authorized this channel",
        );
    }
    let recipient = match d.channel {
        Channel::Email => {
            let r = d.recipient.trim().to_lowercase();
            if !is_email(&r) {
                return rej("invalid_recipient", "not a valid email address");
            }
            r
        }
        Channel::Sms => match normalize_phone(&d.recipient, &ctx.default_country_code) {
            Some(p) => p,
            None => return rej("invalid_recipient", "not a valid phone number"),
        },
    };
    let key = contact_key(&recipient, &ctx.default_country_code);
    if !ctx.case_contacts.contains(&key) {
        return rej(
            "recipient_not_on_case",
            "recipients must already belong to this case",
        );
    }
    if ctx.suppressed.contains(&key) {
        return rej("recipient_opted_out", "the recipient opted out");
    }
    let body = d.body.trim();
    let max = if d.channel == Channel::Sms {
        SMS_MAX
    } else {
        EMAIL_MAX
    };
    if body.is_empty() || body.chars().count() > max {
        return rej("bad_body", "empty or too long for the channel");
    }
    if !guard::unknown_amounts(body, &ctx.knowledge_evidence).is_empty() {
        return rej(
            "price_not_in_evidence",
            "a dollar amount is not in the business evidence",
        );
    }
    let fingerprint = delivery_fingerprint(
        &cap.tenant_id,
        &cap.case_id,
        d.channel,
        &recipient,
        d.subject.trim(),
        body,
    );
    let approved = match &plan.approval_ref {
        Some(r) => match ctx.approvals.get(r) {
            Some(f) if *f == fingerprint => true,
            _ => {
                return rej(
                    "approval_mismatch",
                    "the approval does not cover this exact content",
                )
            }
        },
        None => false,
    };
    let routine_ok = ctx.workflow.autonomy == Autonomy::AutoRoutine
        && plan.confidence >= ctx.workflow.min_confidence
        && plan.escalation_reason.is_none()
        && !plan.intent.is_sensitive()
        && plan.missing_facts.is_empty()
        && guard::amounts(body).is_empty();
    let mode = if ctx.workflow.autonomy == Autonomy::Shadow {
        DeliveryMode::ShadowOnly
    } else if approved || routine_ok {
        DeliveryMode::Auto
    } else {
        DeliveryMode::NeedsApproval
    };
    let when = DateTime::from_timestamp(now, 0).expect("timestamp in range");
    Ok(Delivery {
        channel: d.channel,
        recipient,
        subject: d.subject.trim().to_string(),
        body: body.to_string(),
        send_at: schedule::next_allowed_send(ctx.timezone, when, 8, 21),
        dedupe_key: format!(
            "hermes:{}:{}:{}:{}",
            cap.tenant_id,
            cap.case_id,
            plan.task_id,
            if d.channel == Channel::Sms {
                "sms"
            } else {
                "email"
            }
        ),
        fingerprint,
        mode,
    })
}
