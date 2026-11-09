//! The closed set of operations the customer coordinator may request. There is deliberately no shell, SQL, URL fetch
//! or send-mail operation: sending is a policy decision made after validation, never a tool Hermes holds.
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, PartialEq, Eq, Debug, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Op {
    GetCaseContext,
    SearchBusinessKnowledge,
    GetChannelReadiness,
    CheckAvailability,
    PrepareReply,
    PrepareQuote,
    RequestBooking,
    ScheduleFollowup,
    EscalateCase,
    GetActionStatus,
}

pub const ALL: [Op; 10] = [
    Op::GetCaseContext,
    Op::SearchBusinessKnowledge,
    Op::GetChannelReadiness,
    Op::CheckAvailability,
    Op::PrepareReply,
    Op::PrepareQuote,
    Op::RequestBooking,
    Op::ScheduleFollowup,
    Op::EscalateCase,
    Op::GetActionStatus,
];

impl Op {
    pub fn name(self) -> &'static str {
        match self {
            Op::GetCaseContext => "get_case_context",
            Op::SearchBusinessKnowledge => "search_business_knowledge",
            Op::GetChannelReadiness => "get_channel_readiness",
            Op::CheckAvailability => "check_availability",
            Op::PrepareReply => "prepare_reply",
            Op::PrepareQuote => "prepare_quote",
            Op::RequestBooking => "request_booking",
            Op::ScheduleFollowup => "schedule_followup",
            Op::EscalateCase => "escalate_case",
            Op::GetActionStatus => "get_action_status",
        }
    }

    pub fn parse(s: &str) -> Option<Op> {
        ALL.iter().copied().find(|o| o.name() == s)
    }

    /// Changes state: needs an idempotency key and the expected case version.
    pub fn is_mutating(self) -> bool {
        matches!(
            self,
            Op::PrepareReply
                | Op::PrepareQuote
                | Op::RequestBooking
                | Op::ScheduleFollowup
                | Op::EscalateCase
        )
    }

    /// Commits something the customer can feel (a booking, a promised follow-up). Blocked while a human has taken over.
    pub fn affects_customer(self) -> bool {
        matches!(self, Op::RequestBooking | Op::ScheduleFollowup)
    }

    /// Always allowed, even under takeover: raising a human is the safe direction.
    pub fn is_safety_valve(self) -> bool {
        matches!(self, Op::EscalateCase)
    }
}
