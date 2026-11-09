//! The typed plan Hermes returns. Parsing is strict: unknown fields, oversized text, control characters, out-of-range
//! confidence and excessive counts are all errors, so a malformed or hostile response never reaches policy.
use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const MAX_PLAN_BYTES: usize = 64 * 1024;
const MAX_ACTIONS: usize = 10;
const MAX_LIST: usize = 50;
const MAX_TEXT: usize = 4000;
const MAX_SHORT: usize = 300;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Intent {
    FactualQuestion,
    BookingRequest,
    QuoteRequest,
    Complaint,
    RefundRequest,
    HumanRequest,
    FollowUp,
    Other,
}

impl Intent {
    /// Always handled by a person, whatever the autonomy setting.
    pub fn is_sensitive(self) -> bool {
        matches!(
            self,
            Intent::Complaint | Intent::RefundRequest | Intent::HumanRequest
        )
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Channel {
    Email,
    Sms,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CustomerDraft {
    pub channel: Channel,
    pub recipient: String,
    #[serde(default)]
    pub subject: String,
    pub body: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProposedAction {
    pub op: String,
    pub idempotency_key: String,
    pub expected_case_version: u64,
    #[serde(default)]
    pub params: Value,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HermesPlan {
    pub task_id: String,
    pub intent: Intent,
    #[serde(default)]
    pub evidence: Vec<String>,
    #[serde(default)]
    pub missing_facts: Vec<String>,
    #[serde(default)]
    pub proposed_actions: Vec<ProposedAction>,
    #[serde(default)]
    pub customer_draft: Option<CustomerDraft>,
    pub next_step: String,
    pub confidence: f64,
    #[serde(default)]
    pub escalation_reason: Option<String>,
    #[serde(default)]
    pub approval_ref: Option<String>,
}

#[derive(Debug, PartialEq, Eq)]
pub enum PlanError {
    TooLarge,
    Json(String),
    Invalid(&'static str),
}

fn clean(s: &str, max: usize, what: &'static str) -> Result<(), PlanError> {
    if s.chars().count() > max {
        return Err(PlanError::Invalid(what));
    }
    if s.chars()
        .any(|c| c.is_control() && c != '\n' && c != '\t' && c != '\r')
    {
        return Err(PlanError::Invalid("control characters are not allowed"));
    }
    Ok(())
}

pub fn parse_plan(raw: &str) -> Result<HermesPlan, PlanError> {
    if raw.len() > MAX_PLAN_BYTES {
        return Err(PlanError::TooLarge);
    }
    let plan: HermesPlan = serde_json::from_str(raw).map_err(|e| PlanError::Json(e.to_string()))?;
    if plan.task_id.is_empty() {
        return Err(PlanError::Invalid("task_id is required"));
    }
    if !plan.confidence.is_finite() || !(0.0..=1.0).contains(&plan.confidence) {
        return Err(PlanError::Invalid("confidence must be between 0 and 1"));
    }
    if plan.proposed_actions.len() > MAX_ACTIONS
        || plan.evidence.len() > MAX_LIST
        || plan.missing_facts.len() > MAX_LIST
    {
        return Err(PlanError::Invalid("too many list entries"));
    }
    clean(&plan.task_id, MAX_SHORT, "task_id too long")?;
    clean(&plan.next_step, MAX_TEXT, "next_step too long")?;
    for s in plan.evidence.iter().chain(&plan.missing_facts) {
        clean(s, MAX_SHORT, "list entry too long")?;
    }
    if let Some(r) = &plan.escalation_reason {
        clean(r, MAX_TEXT, "escalation_reason too long")?;
    }
    for a in &plan.proposed_actions {
        clean(&a.op, MAX_SHORT, "op too long")?;
        clean(&a.idempotency_key, MAX_SHORT, "idempotency_key too long")?;
    }
    if let Some(d) = &plan.customer_draft {
        clean(&d.recipient, MAX_SHORT, "recipient too long")?;
        clean(&d.subject, MAX_SHORT, "subject too long")?;
        clean(&d.body, MAX_TEXT, "body too long")?;
    }
    Ok(plan)
}
