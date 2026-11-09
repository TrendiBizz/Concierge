//! Acceptance tests mapped to the framework's test table (HERMES_CONCIERGE_FRAMEWORK §11). Each asserts a decision or a
//! ledger state, not merely "no panic".
use chrono::{TimeZone, Utc};
use concierge_core::contact::contact_key;
use hermes_gateway::capability::{mint, verify, CapError, Capability, MAX_TTL_SECS};
use hermes_gateway::ledger::{
    ActionLedger, ActionState, Begin, CaseState, LedgerError, MemoryLedger, NewAction,
};
use hermes_gateway::ops::Op;
use hermes_gateway::plan::{parse_plan, HermesPlan, PlanError};
use hermes_gateway::policy::{
    delivery_fingerprint, validate_plan, Autonomy, DeliveryMode, PolicyContext, WorkflowPolicy,
};
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};

const SECRET: &[u8] = b"test-secret-not-real-0123456789abcdef";
const NOW: i64 = 1_800_000_000;

fn cap(ops: &[Op]) -> Capability {
    Capability {
        tenant_id: "t-a".into(),
        case_id: "c-1".into(),
        run_id: "r-1".into(),
        ops: ops.to_vec(),
        issued_at: NOW,
        expires_at: NOW + 300,
        nonce: "n-1".into(),
    }
}

fn ctx(autonomy: Autonomy) -> PolicyContext {
    PolicyContext {
        tenant_id: "t-a".into(),
        case_id: "c-1".into(),
        case_version: 7,
        automation_paused: false,
        timezone: "Pacific/Auckland".parse().unwrap(),
        default_country_code: "64".into(),
        email_send_authorized: true,
        sms_send_authorized: true,
        case_contacts: HashSet::from([
            contact_key("ann@example.com", "64"),
            contact_key("+6421123456", "64"),
        ]),
        suppressed: HashSet::new(),
        knowledge_evidence: "Standard service is $120. Call-out fee $45.50.".into(),
        workflow: WorkflowPolicy {
            autonomy,
            min_confidence: 0.8,
        },
        approvals: HashMap::new(),
    }
}

fn plan(v: Value) -> HermesPlan {
    parse_plan(&v.to_string()).expect("valid plan")
}

fn base(extra: Value) -> Value {
    let mut p = json!({"task_id": "task-1", "intent": "factual_question", "next_step": "reply", "confidence": 0.95});
    for (k, v) in extra.as_object().unwrap() {
        p[k] = v.clone();
    }
    p
}

fn draft(channel: &str, recipient: &str, body: &str) -> Value {
    json!({"customer_draft": {"channel": channel, "recipient": recipient, "body": body}})
}

fn action(op: &str, key: &str, version: u64, params: Value) -> Value {
    json!({"op": op, "idempotency_key": key, "expected_case_version": version, "params": params})
}

fn reason(
    r: Result<hermes_gateway::policy::Validated, hermes_gateway::policy::Reject>,
) -> &'static str {
    r.expect_err("expected a rejection").code
}

// ---- capabilities ---------------------------------------------------------------------------------------------
#[test]
fn capability_roundtrip_and_tamper_resistance() {
    let c = cap(&[Op::GetCaseContext, Op::PrepareReply]);
    let tok = mint(SECRET, &c).unwrap();
    assert_eq!(verify(SECRET, &tok, NOW + 1, &|_| false).unwrap(), c);
    // wrong secret, flipped payload, swapped signature, garbage
    assert_eq!(
        verify(
            b"other-secret-xxxxxxxxxxxxxxxxxxxxxxxx",
            &tok,
            NOW + 1,
            &|_| false
        ),
        Err(CapError::BadSignature)
    );
    let (p, s) = tok.split_once('.').unwrap();
    let forged = Capability {
        tenant_id: "t-b".into(),
        ..c.clone()
    };
    let forged_payload = mint(b"attacker-secret-xxxxxxxxxxxxxxxxxxxxx", &forged).unwrap();
    let (fp, _) = forged_payload.split_once('.').unwrap();
    assert_eq!(
        verify(SECRET, &format!("{fp}.{s}"), NOW + 1, &|_| false),
        Err(CapError::BadSignature),
        "another tenant's payload under a real signature"
    );
    assert!(verify(SECRET, &format!("{p}x.{s}"), NOW + 1, &|_| false).is_err());
    for junk in ["", "abc", ".", "a.b.c", "!!.!!"] {
        assert!(
            verify(SECRET, junk, NOW + 1, &|_| false).is_err(),
            "{junk:?}"
        );
    }
}

#[test]
fn capability_lifetime_scope_and_revocation() {
    let tok = mint(SECRET, &cap(&[Op::GetCaseContext])).unwrap();
    assert_eq!(
        verify(SECRET, &tok, NOW + 300, &|_| false),
        Err(CapError::Expired)
    );
    assert_eq!(
        verify(SECRET, &tok, NOW - 600, &|_| false),
        Err(CapError::NotYetValid)
    );
    assert_eq!(
        verify(SECRET, &tok, NOW + 5, &|n| n == "n-1"),
        Err(CapError::Revoked)
    );
    let long = Capability {
        expires_at: NOW + MAX_TTL_SECS + 1,
        ..cap(&[Op::GetCaseContext])
    };
    assert_eq!(mint(SECRET, &long), Err(CapError::TtlTooLong));
    assert_eq!(mint(SECRET, &cap(&[])), Err(CapError::EmptyScope));
}

// ---- #3 malformed or hostile output --------------------------------------------------------------------------
#[test]
fn malformed_or_hostile_plans_never_parse() {
    let ok = base(json!({}));
    assert!(parse_plan(&ok.to_string()).is_ok());
    // the model cannot smuggle in a tenant, a capability or any other field
    for field in ["tenant_id", "capability", "ops", "shell", "send_now"] {
        let mut p = ok.clone();
        p[field] = json!("x");
        assert!(
            matches!(parse_plan(&p.to_string()), Err(PlanError::Json(_))),
            "{field}"
        );
    }
    for bad in [json!(-0.1), json!(1.5), json!("high")] {
        let mut p = ok.clone();
        p["confidence"] = bad;
        assert!(parse_plan(&p.to_string()).is_err());
    }
    let mut p = ok.clone();
    p["next_step"] = json!("x\u{0}y");
    assert!(
        matches!(parse_plan(&p.to_string()), Err(PlanError::Invalid(_))),
        "control characters"
    );
    p["next_step"] = json!("x".repeat(5000));
    assert!(matches!(
        parse_plan(&p.to_string()),
        Err(PlanError::Invalid(_))
    ));
    assert_eq!(parse_plan(&"x".repeat(70_000)), Err(PlanError::TooLarge));
    assert!(parse_plan("not json").is_err());
    let many: Vec<Value> = (0..11)
        .map(|i| action("get_case_context", &format!("k{i}"), 7, json!({})))
        .collect();
    assert!(parse_plan(&base(json!({"proposed_actions": many})).to_string()).is_err());
}

// ---- #11 #24 capability escalation and cross-tenant ----------------------------------------------------------
#[test]
fn operations_outside_the_allowlist_or_grant_are_refused() {
    let c = cap(&[Op::GetCaseContext]);
    let x = ctx(Autonomy::DraftReview);
    for op in ["shell", "send_email", "run_sql", "fetch_url", "docker"] {
        let p = plan(base(
            json!({"proposed_actions": [action(op, "k1", 7, json!({}))]}),
        ));
        assert_eq!(
            reason(validate_plan(&c, &p, &x, NOW)),
            "unknown_operation",
            "{op}"
        );
    }
    let p = plan(base(
        json!({"proposed_actions": [action("request_booking", "k1", 7, json!({}))]}),
    ));
    assert_eq!(
        reason(validate_plan(&c, &p, &x, NOW)),
        "operation_not_granted"
    );
}

#[test]
fn a_model_cannot_name_another_business_or_case() {
    let c = cap(&[Op::PrepareQuote]);
    let x = ctx(Autonomy::DraftReview);
    for params in [
        json!({"tenant_id": "t-b"}),
        json!({"nested": {"deep": [{"business_id": "t-b"}]}}),
        json!({"case_id": "c-999"}),
    ] {
        let p = plan(base(
            json!({"proposed_actions": [action("prepare_quote", "k1", 7, params)]}),
        ));
        assert_eq!(reason(validate_plan(&c, &p, &x, NOW)), "scope_override");
    }
    // naming its own tenant is harmless
    let p = plan(base(
        json!({"proposed_actions": [action("prepare_quote", "k1", 7, json!({"tenant_id": "t-a"}))]}),
    ));
    assert!(validate_plan(&c, &p, &x, NOW).is_ok());
    // a policy context loaded for another tenant is refused outright
    let mut other = ctx(Autonomy::DraftReview);
    other.tenant_id = "t-b".into();
    assert_eq!(reason(validate_plan(&c, &p, &other, NOW)), "scope_mismatch");
}

// ---- #30 stale facts, mutation contract ----------------------------------------------------------------------
#[test]
fn mutations_need_a_valid_key_and_the_current_case_version() {
    let c = cap(&[Op::RequestBooking]);
    let x = ctx(Autonomy::DraftReview);
    let stale = plan(base(
        json!({"proposed_actions": [action("request_booking", "k1", 6, json!({}))]}),
    ));
    assert_eq!(reason(validate_plan(&c, &stale, &x, NOW)), "stale_case");
    for key in ["", "has space", "semi;colon", &"k".repeat(129)] {
        let p = plan(base(
            json!({"proposed_actions": [action("request_booking", key, 7, json!({}))]}),
        ));
        assert_eq!(
            reason(validate_plan(&c, &p, &x, NOW)),
            "bad_idempotency_key",
            "{key:?}"
        );
    }
    let good = plan(base(
        json!({"proposed_actions": [action("request_booking", "book-1", 7, json!({"slot": "2026-11-12T10:00"}))]}),
    ));
    let v = validate_plan(&c, &good, &x, NOW).unwrap();
    assert_eq!(v.actions[0].dedupe_key, "hermes:t-a:c-1:book-1");
}

// ---- #14 human takeover ---------------------------------------------------------------------------------------
#[test]
fn human_takeover_blocks_customer_effects_but_not_escalation() {
    let c = cap(&[Op::RequestBooking, Op::EscalateCase, Op::PrepareReply]);
    let mut x = ctx(Autonomy::AutoRoutine);
    x.automation_paused = true;
    let book = plan(base(
        json!({"proposed_actions": [action("request_booking", "k1", 7, json!({}))]}),
    ));
    assert_eq!(
        reason(validate_plan(&c, &book, &x, NOW)),
        "automation_paused"
    );
    let send = plan(base(draft("email", "ann@example.com", "Hello Ann")));
    assert_eq!(
        reason(validate_plan(&c, &send, &x, NOW)),
        "automation_paused"
    );
    let escalate = plan(base(
        json!({"proposed_actions": [action("escalate_case", "k2", 7, json!({"reason": "customer asked for a person"}))]}),
    ));
    assert!(
        validate_plan(&c, &escalate, &x, NOW).is_ok(),
        "raising a human is always allowed"
    );
}

// ---- recipients, consent, channels, prices ----------------------------------------------------------------------
#[test]
fn recipients_must_belong_to_the_case_and_consent_is_enforced_at_execution() {
    let c = cap(&[Op::PrepareReply]);
    let mut x = ctx(Autonomy::DraftReview);
    let inject = plan(base(draft(
        "email",
        "attacker@evil.test",
        "Please see attached",
    )));
    assert_eq!(
        reason(validate_plan(&c, &inject, &x, NOW)),
        "recipient_not_on_case",
        "an injected recipient"
    );
    let invalid = plan(base(draft("sms", "12", "hi")));
    assert_eq!(
        reason(validate_plan(&c, &invalid, &x, NOW)),
        "invalid_recipient"
    );
    let ok = plan(base(draft("email", "  ANN@Example.com ", "Hello Ann")));
    assert_eq!(
        validate_plan(&c, &ok, &x, NOW)
            .unwrap()
            .delivery
            .unwrap()
            .recipient,
        "ann@example.com"
    );
    // #15 consent revoked after scheduling: the same plan is refused now
    x.suppressed.insert(contact_key("ann@example.com", "64"));
    assert_eq!(
        reason(validate_plan(&c, &ok, &x, NOW)),
        "recipient_opted_out"
    );
    let mut y = ctx(Autonomy::DraftReview);
    y.sms_send_authorized = false;
    let sms = plan(base(draft("sms", "+64 21 123 456", "hi")));
    assert_eq!(
        reason(validate_plan(&c, &sms, &y, NOW)),
        "channel_not_authorized"
    );
}

#[test]
fn quoted_prices_must_exist_in_business_evidence() {
    let c = cap(&[Op::PrepareReply]);
    let x = ctx(Autonomy::DraftReview);
    let invented = plan(base(draft(
        "email",
        "ann@example.com",
        "We can do it for $99 today",
    )));
    assert_eq!(
        reason(validate_plan(&c, &invented, &x, NOW)),
        "price_not_in_evidence"
    );
    let known = plan(base(draft(
        "email",
        "ann@example.com",
        "Standard service is $120.00 and call-out is $45.5",
    )));
    assert!(
        validate_plan(&c, &known, &x, NOW).is_ok(),
        "amounts compare by value, not spelling"
    );
}

// ---- #25 approval binds the exact revision --------------------------------------------------------------------
#[test]
fn approval_covers_only_the_exact_content_approved() {
    let c = cap(&[Op::PrepareReply]);
    let mut x = ctx(Autonomy::DraftReview);
    let body = "Hello Ann, we can visit Thursday.";
    let fp = delivery_fingerprint(
        "t-a",
        "c-1",
        hermes_gateway::plan::Channel::Email,
        "ann@example.com",
        "",
        body,
    );
    x.approvals.insert("appr-1".into(), fp);
    let mut approved = base(draft("email", "ann@example.com", body));
    approved["approval_ref"] = json!("appr-1");
    let v = validate_plan(&c, &plan(approved), &x, NOW).unwrap();
    assert_eq!(
        v.delivery.unwrap().mode,
        DeliveryMode::Auto,
        "approved exactly"
    );
    let mut edited = base(draft(
        "email",
        "ann@example.com",
        "Hello Ann, we can visit Friday.",
    ));
    edited["approval_ref"] = json!("appr-1");
    assert_eq!(
        reason(validate_plan(&c, &plan(edited), &x, NOW)),
        "approval_mismatch"
    );
    let mut unknown = base(draft("email", "ann@example.com", body));
    unknown["approval_ref"] = json!("appr-404");
    assert_eq!(
        reason(validate_plan(&c, &plan(unknown), &x, NOW)),
        "approval_mismatch"
    );
    // the same text to a different recipient is a different approval
    let other = delivery_fingerprint(
        "t-a",
        "c-1",
        hermes_gateway::plan::Channel::Email,
        "bob@example.com",
        "",
        body,
    );
    assert_ne!(
        other,
        delivery_fingerprint(
            "t-a",
            "c-1",
            hermes_gateway::plan::Channel::Email,
            "ann@example.com",
            "",
            body
        )
    );
}

// ---- autonomy levels -----------------------------------------------------------------------------------------
#[test]
fn autonomy_levels_decide_who_sends() {
    let c = cap(&[Op::PrepareReply]);
    let routine = plan(base(draft(
        "email",
        "ann@example.com",
        "We open at 9am on weekdays.",
    )));
    let mode = |a: Autonomy, p: &HermesPlan| {
        validate_plan(&c, p, &ctx(a), NOW)
            .unwrap()
            .delivery
            .unwrap()
            .mode
    };
    assert_eq!(mode(Autonomy::Shadow, &routine), DeliveryMode::ShadowOnly);
    assert_eq!(
        mode(Autonomy::DraftReview, &routine),
        DeliveryMode::NeedsApproval
    );
    assert_eq!(mode(Autonomy::AutoRoutine, &routine), DeliveryMode::Auto);
    let shadow = validate_plan(&c, &routine, &ctx(Autonomy::Shadow), NOW).unwrap();
    assert!(shadow.shadow);
    // routine automation still stops for anything sensitive, uncertain, priced or escalated
    let mut sensitive = base(draft("email", "ann@example.com", "We open at 9am."));
    sensitive["intent"] = json!("complaint");
    assert_eq!(
        mode(Autonomy::AutoRoutine, &plan(sensitive)),
        DeliveryMode::NeedsApproval
    );
    let mut unsure = base(draft("email", "ann@example.com", "We open at 9am."));
    unsure["confidence"] = json!(0.5);
    assert_eq!(
        mode(Autonomy::AutoRoutine, &plan(unsure)),
        DeliveryMode::NeedsApproval
    );
    let mut missing = base(draft("email", "ann@example.com", "We open at 9am."));
    missing["missing_facts"] = json!(["which suburb"]);
    assert_eq!(
        mode(Autonomy::AutoRoutine, &plan(missing)),
        DeliveryMode::NeedsApproval
    );
    let mut escalated = base(draft("email", "ann@example.com", "We open at 9am."));
    escalated["escalation_reason"] = json!("customer sounds upset");
    assert_eq!(
        mode(Autonomy::AutoRoutine, &plan(escalated)),
        DeliveryMode::NeedsApproval
    );
    let priced = plan(base(draft(
        "email",
        "ann@example.com",
        "Standard service is $120.",
    )));
    assert_eq!(
        mode(Autonomy::AutoRoutine, &priced),
        DeliveryMode::NeedsApproval,
        "any price needs a person"
    );
}

// ---- #26 quiet hours, #1 duplicates --------------------------------------------------------------------------
#[test]
fn quiet_hours_and_duplicate_plans() {
    let c = cap(&[Op::PrepareReply]);
    let x = ctx(Autonomy::AutoRoutine);
    // 03:00 in Auckland on 10 Nov 2026 -> the message waits until 08:00 local
    let three_am = chrono_tz::Pacific::Auckland
        .with_ymd_and_hms(2026, 11, 10, 3, 0, 0)
        .unwrap()
        .with_timezone(&Utc);
    let eight_am = chrono_tz::Pacific::Auckland
        .with_ymd_and_hms(2026, 11, 10, 8, 0, 0)
        .unwrap()
        .with_timezone(&Utc);
    let p = plan(base(draft("sms", "+64 21 123 456", "We open at 9am.")));
    let v = validate_plan(&c, &p, &x, three_am.timestamp()).unwrap();
    assert_eq!(v.delivery.as_ref().unwrap().send_at, eight_am);
    // the same task delivered three times yields the same dedupe key, so it can only enqueue once
    let keys: Vec<String> = (0..3)
        .map(|_| {
            validate_plan(&c, &p, &x, three_am.timestamp())
                .unwrap()
                .delivery
                .unwrap()
                .dedupe_key
        })
        .collect();
    assert!(keys.windows(2).all(|w| w[0] == w[1]));
    assert_eq!(keys[0], "hermes:t-a:c-1:task-1:sms");
    // inside the window it sends immediately
    let noon = chrono_tz::Pacific::Auckland
        .with_ymd_and_hms(2026, 11, 10, 12, 0, 0)
        .unwrap()
        .with_timezone(&Utc);
    assert_eq!(
        validate_plan(&c, &p, &x, noon.timestamp())
            .unwrap()
            .delivery
            .unwrap()
            .send_at,
        noon
    );
}

#[test]
fn one_bad_part_rejects_the_whole_plan() {
    let c = cap(&[Op::PrepareReply, Op::ScheduleFollowup]);
    let x = ctx(Autonomy::AutoRoutine);
    let mut p = base(draft("email", "ann@example.com", "We open at 9am."));
    p["proposed_actions"] = json!([
        action("schedule_followup", "k1", 7, json!({})),
        action("schedule_followup", "k2", 3, json!({}))
    ]);
    assert_eq!(
        reason(validate_plan(&c, &plan(p), &x, NOW)),
        "stale_case",
        "nothing partial is returned for execution"
    );
}

// ---- ledger: #1 #12 -------------------------------------------------------------------------------------------
fn new_action(tenant: &str, key: &str, fp: &str) -> NewAction {
    NewAction {
        tenant_id: tenant.into(),
        case_id: "c-1".into(),
        op: "request_booking".into(),
        idempotency_key: key.into(),
        fingerprint: fp.into(),
        case_version: 7,
        approval_ref: None,
    }
}

#[test]
fn ledger_is_idempotent_and_tenant_scoped() {
    let mut l = MemoryLedger::default();
    let id = match l.begin(new_action("t-a", "k1", "fp1")).unwrap() {
        Begin::Created(id) => id,
        other => panic!("{other:?}"),
    };
    assert_eq!(
        l.begin(new_action("t-a", "k1", "fp1")).unwrap(),
        Begin::Duplicate(id),
        "same webhook three times -> one action"
    );
    assert_eq!(
        l.begin(new_action("t-a", "k1", "different")),
        Err(LedgerError::KeyReuseConflict(id)),
        "a key is never reinterpreted"
    );
    // another tenant may reuse the key string, and can neither see nor touch tenant A's action
    assert!(matches!(
        l.begin(new_action("t-b", "k1", "fp1")).unwrap(),
        Begin::Created(_)
    ));
    assert!(l.get("t-b", id).is_none());
    assert_eq!(
        l.transition("t-b", id, ActionState::PolicyChecked, None),
        Err(LedgerError::UnknownAction)
    );
    assert_eq!(l.get("t-a", id).unwrap().state, ActionState::Proposed);
}

#[test]
fn uncertain_sends_are_reconciled_never_blindly_repeated() {
    let mut l = MemoryLedger::default();
    let Begin::Created(id) = l.begin(new_action("t-a", "k1", "fp1")).unwrap() else {
        panic!()
    };
    for s in [
        ActionState::PolicyChecked,
        ActionState::Queued,
        ActionState::Executing,
    ] {
        l.transition("t-a", id, s, None).unwrap();
    }
    // provider accepted, connection dropped before we heard back
    l.transition("t-a", id, ActionState::Uncertain, None)
        .unwrap();
    assert!(!l.get("t-a", id).unwrap().state.may_resend());
    assert_eq!(
        l.transition("t-a", id, ActionState::Queued, None),
        Err(LedgerError::IllegalTransition(
            ActionState::Uncertain,
            ActionState::Queued
        ))
    );
    assert_eq!(
        l.transition("t-a", id, ActionState::Executing, None),
        Err(LedgerError::IllegalTransition(
            ActionState::Uncertain,
            ActionState::Executing
        ))
    );
    // reconciliation finds the provider did deliver
    l.transition("t-a", id, ActionState::Delivered, Some("prov-123".into()))
        .unwrap();
    let r = l.get("t-a", id).unwrap();
    assert_eq!(
        (r.state, r.attempts, r.provider_id.as_deref()),
        (ActionState::Delivered, 1, Some("prov-123"))
    );
    assert!(r.state.is_terminal());
    assert!(
        l.transition("t-a", id, ActionState::Queued, None).is_err(),
        "delivered is final"
    );
}

#[test]
fn only_a_known_failure_may_be_retried() {
    let mut l = MemoryLedger::default();
    let Begin::Created(id) = l.begin(new_action("t-a", "k2", "fp2")).unwrap() else {
        panic!()
    };
    for s in [
        ActionState::PolicyChecked,
        ActionState::AwaitingApproval,
        ActionState::Queued,
        ActionState::Executing,
        ActionState::Failed,
    ] {
        l.transition("t-a", id, s, None).unwrap();
    }
    assert!(l.get("t-a", id).unwrap().state.may_resend());
    l.transition("t-a", id, ActionState::Queued, None).unwrap();
    l.transition("t-a", id, ActionState::Executing, None)
        .unwrap();
    assert_eq!(l.get("t-a", id).unwrap().attempts, 2);
    // no skipping the approval or policy steps
    let Begin::Created(other) = l.begin(new_action("t-a", "k3", "fp3")).unwrap() else {
        panic!()
    };
    assert!(l
        .transition("t-a", other, ActionState::Queued, None)
        .is_err());
    assert!(l
        .transition("t-a", other, ActionState::Executing, None)
        .is_err());
}

#[test]
fn case_lifecycle() {
    use CaseState::*;
    assert!(New.can_transition(Triaged) && Triaged.can_transition(InProgress));
    assert!(
        InProgress.can_transition(WaitingCustomer) && WaitingCustomer.can_transition(InProgress)
    );
    assert!(
        InProgress.can_transition(Resolved) && Resolved.can_transition(InProgress),
        "a new inbound reopens a resolved case"
    );
    assert!(Resolved.can_transition(Closed));
    assert!(
        New.can_transition(Resolved),
        "an open case can be resolved directly"
    );
    assert!(!Closed.can_transition(InProgress), "closed is final");
    assert!(!New.can_transition(Closed) && !Closed.can_transition(Resolved));
}
