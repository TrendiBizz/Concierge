//! What the gateway needs from Concierge. The real implementation calls Concierge's `/internal/hermes` routes
//! (`api/app/hermes_ops.py`); tests use an in-memory fake.
use crate::policy::{Autonomy, PolicyContext, WorkflowPolicy};
use async_trait::async_trait;
use concierge_core::contact::contact_key;
use serde::Deserialize;
use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::time::Duration;

#[derive(Debug)]
pub enum BackendError {
    NotFound,
    /// Concierge understood and refused (stale case, takeover, opt-out...). Passed through unchanged.
    Refused {
        status: u16,
        body: Value,
    },
    Unavailable(String),
}

#[async_trait]
pub trait Backend: Send + Sync {
    async fn policy_context(
        &self,
        tenant_id: &str,
        case_id: &str,
    ) -> Result<PolicyContext, BackendError>;
    async fn execute(
        &self,
        tenant_id: &str,
        case_id: &str,
        bundle: &Value,
    ) -> Result<Value, BackendError>;
}

/// The JSON `GET /internal/hermes/cases/{id}/policy-context` returns.
#[derive(Deserialize)]
pub struct ContextWire {
    pub tenant_id: String,
    pub case_id: String,
    pub case_version: u64,
    pub automation_paused: bool,
    pub timezone: String,
    pub default_country_code: String,
    pub email_send_authorized: bool,
    pub sms_send_authorized: bool,
    pub case_contacts: Vec<String>,
    pub suppressed: Vec<String>,
    pub knowledge_evidence: String,
    pub autonomy: String,
    pub min_confidence: f64,
    #[serde(default)]
    pub approvals: HashMap<String, String>,
}

impl ContextWire {
    pub fn into_context(self) -> Result<PolicyContext, BackendError> {
        let bad =
            |what: &str| BackendError::Unavailable(format!("policy context has an invalid {what}"));
        let autonomy = match self.autonomy.as_str() {
            "shadow" => Autonomy::Shadow,
            "draft_review" => Autonomy::DraftReview,
            "auto_routine" => Autonomy::AutoRoutine,
            _ => return Err(bad("autonomy")),
        };
        let cc = self.default_country_code.clone();
        Ok(PolicyContext {
            tenant_id: self.tenant_id,
            case_id: self.case_id,
            case_version: self.case_version,
            automation_paused: self.automation_paused,
            timezone: self.timezone.parse().map_err(|_| bad("timezone"))?,
            default_country_code: self.default_country_code,
            email_send_authorized: self.email_send_authorized,
            sms_send_authorized: self.sms_send_authorized,
            // Concierge already sends canonical keys; normalising again is harmless and guards against drift.
            case_contacts: self
                .case_contacts
                .iter()
                .map(|c| contact_key(c, &cc))
                .collect::<HashSet<_>>(),
            suppressed: self
                .suppressed
                .iter()
                .map(|c| contact_key(c, &cc))
                .collect::<HashSet<_>>(),
            knowledge_evidence: self.knowledge_evidence,
            workflow: WorkflowPolicy {
                autonomy,
                min_confidence: self.min_confidence,
            },
            approvals: self.approvals,
        })
    }
}

pub struct HttpBackend {
    base: String,
    key: String,
    client: reqwest::Client,
}

impl HttpBackend {
    pub fn new(base: &str, key: &str) -> Result<Self, String> {
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(10))
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .map_err(|e| e.to_string())?;
        Ok(Self {
            base: base.trim_end_matches('/').to_string(),
            key: key.to_string(),
            client,
        })
    }

    async fn finish(resp: reqwest::Response) -> Result<Value, BackendError> {
        let status = resp.status().as_u16();
        let body: Value = resp.json().await.unwrap_or(Value::Null);
        match status {
            200..=299 => Ok(body),
            404 => Err(BackendError::NotFound),
            409 | 422 => Err(BackendError::Refused { status, body }),
            other => Err(BackendError::Unavailable(format!(
                "concierge answered {other}"
            ))),
        }
    }
}

#[async_trait]
impl Backend for HttpBackend {
    async fn policy_context(
        &self,
        tenant_id: &str,
        case_id: &str,
    ) -> Result<PolicyContext, BackendError> {
        let url = format!(
            "{}/internal/hermes/cases/{case_id}/policy-context",
            self.base
        );
        let resp = self
            .client
            .get(url)
            .query(&[("tenant_id", tenant_id)])
            .header("x-hermes-gateway-key", &self.key)
            .send()
            .await
            .map_err(|e| BackendError::Unavailable(e.to_string()))?;
        let wire: ContextWire = serde_json::from_value(Self::finish(resp).await?)
            .map_err(|e| BackendError::Unavailable(format!("unreadable policy context: {e}")))?;
        wire.into_context()
    }

    async fn execute(
        &self,
        _tenant_id: &str,
        case_id: &str,
        bundle: &Value,
    ) -> Result<Value, BackendError> {
        let url = format!("{}/internal/hermes/cases/{case_id}/execute", self.base);
        let resp = self
            .client
            .post(url)
            .header("x-hermes-gateway-key", &self.key)
            .json(bundle)
            .send()
            .await
            .map_err(|e| BackendError::Unavailable(e.to_string()))?;
        Self::finish(resp).await
    }
}
