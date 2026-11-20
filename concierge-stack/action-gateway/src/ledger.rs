//! Action and case state machines plus the idempotent action ledger. Exactly-once external delivery is not achievable:
//! a timeout after a provider accepted a send is `Uncertain`, which can only be reconciled, never blindly retried.
use std::collections::HashMap;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ActionState {
    Proposed,
    PolicyChecked,
    AwaitingApproval,
    Queued,
    Executing,
    Accepted,
    Delivered,
    Failed,
    Uncertain,
    Cancelled,
}

impl ActionState {
    pub fn can_transition(self, to: ActionState) -> bool {
        use ActionState::*;
        matches!(
            (self, to),
            (Proposed, PolicyChecked | Cancelled)
                | (PolicyChecked, AwaitingApproval | Queued | Cancelled)
                | (AwaitingApproval, Queued | Cancelled)
                | (Queued, Executing | Cancelled)
                | (Executing, Accepted | Failed | Uncertain)
                | (Accepted, Delivered | Failed | Uncertain)
                // Reconciliation resolves doubt; only a proven failure may be retried.
                | (Uncertain, Accepted | Delivered | Failed)
                | (Failed, Queued)
        )
    }

    pub fn is_terminal(self) -> bool {
        matches!(self, ActionState::Delivered | ActionState::Cancelled)
    }

    /// May a send be attempted again? Only after a *known* failure; never from doubt.
    pub fn may_resend(self) -> bool {
        self == ActionState::Failed
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CaseState {
    New,
    Triaged,
    InProgress,
    WaitingCustomer,
    WaitingBusiness,
    WaitingApproval,
    Resolved,
    Closed,
}

impl CaseState {
    pub fn can_transition(self, to: CaseState) -> bool {
        use CaseState::*;
        let open = |s| {
            matches!(
                s,
                New | Triaged | InProgress | WaitingCustomer | WaitingBusiness | WaitingApproval
            )
        };
        match (self, to) {
            (New, Triaged) | (Triaged, InProgress) => true,
            (
                InProgress | WaitingCustomer | WaitingBusiness | WaitingApproval,
                InProgress | WaitingCustomer | WaitingBusiness | WaitingApproval,
            ) => self != to,
            (from, Resolved) => open(from),
            (Resolved, InProgress) => true, // a new relevant inbound interaction reopens it
            (Resolved, Closed) => true,
            _ => false,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ActionRecord {
    pub id: u64,
    pub tenant_id: String,
    pub case_id: String,
    pub op: String,
    pub idempotency_key: String,
    pub fingerprint: String,
    pub state: ActionState,
    pub case_version: u64,
    pub approval_ref: Option<String>,
    pub attempts: u32,
    pub provider_id: Option<String>,
}

#[derive(Clone, Debug)]
pub struct NewAction {
    pub tenant_id: String,
    pub case_id: String,
    pub op: String,
    pub idempotency_key: String,
    pub fingerprint: String,
    pub case_version: u64,
    pub approval_ref: Option<String>,
}

#[derive(Debug, PartialEq, Eq)]
pub enum Begin {
    Created(u64),
    /// The same request arrived again: nothing new is created.
    Duplicate(u64),
}

#[derive(Debug, PartialEq, Eq)]
pub enum LedgerError {
    /// The key was used before for a different request. Never reinterpret it.
    KeyReuseConflict(u64),
    /// Unknown id, or an id that belongs to another tenant (indistinguishable on purpose).
    UnknownAction,
    IllegalTransition(ActionState, ActionState),
}

pub trait ActionLedger {
    fn begin(&mut self, new: NewAction) -> Result<Begin, LedgerError>;
    fn transition(
        &mut self,
        tenant_id: &str,
        id: u64,
        to: ActionState,
        provider_id: Option<String>,
    ) -> Result<(), LedgerError>;
    fn get(&self, tenant_id: &str, id: u64) -> Option<&ActionRecord>;
}

#[derive(Default)]
pub struct MemoryLedger {
    records: Vec<ActionRecord>,
    by_key: HashMap<(String, String), u64>,
}

impl ActionLedger for MemoryLedger {
    fn begin(&mut self, new: NewAction) -> Result<Begin, LedgerError> {
        let key = (new.tenant_id.clone(), new.idempotency_key.clone());
        if let Some(&id) = self.by_key.get(&key) {
            let existing = &self.records[id as usize];
            return if existing.fingerprint == new.fingerprint {
                Ok(Begin::Duplicate(id))
            } else {
                Err(LedgerError::KeyReuseConflict(id))
            };
        }
        let id = self.records.len() as u64;
        self.records.push(ActionRecord {
            id,
            tenant_id: new.tenant_id,
            case_id: new.case_id,
            op: new.op,
            idempotency_key: new.idempotency_key,
            fingerprint: new.fingerprint,
            state: ActionState::Proposed,
            case_version: new.case_version,
            approval_ref: new.approval_ref,
            attempts: 0,
            provider_id: None,
        });
        self.by_key.insert(key, id);
        Ok(Begin::Created(id))
    }

    fn transition(
        &mut self,
        tenant_id: &str,
        id: u64,
        to: ActionState,
        provider_id: Option<String>,
    ) -> Result<(), LedgerError> {
        let rec = self
            .records
            .get_mut(id as usize)
            .filter(|r| r.tenant_id == tenant_id)
            .ok_or(LedgerError::UnknownAction)?;
        if !rec.state.can_transition(to) {
            return Err(LedgerError::IllegalTransition(rec.state, to));
        }
        if to == ActionState::Executing {
            rec.attempts += 1;
        }
        rec.state = to;
        if provider_id.is_some() {
            rec.provider_id = provider_id;
        }
        Ok(())
    }

    fn get(&self, tenant_id: &str, id: u64) -> Option<&ActionRecord> {
        self.records
            .get(id as usize)
            .filter(|r| r.tenant_id == tenant_id)
    }
}
