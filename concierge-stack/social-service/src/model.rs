//! Social publishing lifecycle. Approval of the current revision is mandatory.
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Draft,
    PendingApproval,
    Approved,
    Scheduled,
    Publishing,
    Published,
    Failed,
    Rejected,
}

impl Status {
    pub fn can_move_to(self, next: Status) -> bool {
        use Status::*;
        matches!(
            (self, next),
            (Draft, PendingApproval)
                | (PendingApproval, Approved)
                | (PendingApproval, Rejected)
                | (PendingApproval, Draft)
                | (Approved, Scheduled)
                | (Approved, Draft)
                | (Scheduled, Publishing)
                | (Scheduled, Draft)
                | (Publishing, Published)
                | (Publishing, Failed)
                | (Publishing, Scheduled)
                | (Failed, Scheduled)
                | (Failed, Draft)
                | (Rejected, Draft)
        )
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Post {
    pub id: String,
    pub customer_id: String,
    pub content: String,
    pub link: String,
    pub hashtags: String,
    pub account_ids: Vec<String>,
    pub media: Vec<String>,
    pub status: Status,
    pub scheduled_at: Option<i64>,
    pub revision: u64,
    pub approved_revision: Option<u64>,
    pub attempts: u32,
    pub last_error: Option<String>,
    pub created_at: i64,
    pub updated_at: i64,
}

impl Post {
    /// The scheduler must check the approved revision again immediately before publishing.
    pub fn may_publish(&self, now: i64) -> bool {
        self.status == Status::Scheduled
            && self.approved_revision == Some(self.revision)
            && self.scheduled_at.is_some_and(|time| time <= now)
    }

    pub fn edit(&mut self, content: String, now: i64) -> Result<(), &'static str> {
        if matches!(self.status, Status::Publishing | Status::Published) {
            return Err("Cannot edit a publishing or published post");
        }
        self.content = content;
        self.revision = self.revision.checked_add(1).ok_or("Revision overflow")?;
        self.status = Status::Draft;
        self.approved_revision = None;
        self.scheduled_at = None;
        self.last_error = None;
        self.updated_at = now;
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct NewPost {
    pub content: String,
    #[serde(default)]
    pub link: String,
    #[serde(default)]
    pub hashtags: String,
    pub account_ids: Vec<String>,
    #[serde(default)]
    pub media: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Customer {
    pub id: String,
    pub name: String,
    pub rules: crate::guardrails::Rules,
    pub approval_contact: String,
    pub created_at: i64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Account {
    pub id: String,
    pub customer_id: String,
    pub network: String,
    pub display_name: String,
    pub external_id: String,
    pub needs_reauth: bool,
    pub expires_at: Option<i64>,
}
