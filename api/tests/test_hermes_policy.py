"""Hermes orchestration, in Python.

The Rust `hermes-gateway` holds the right security design, but it is a separate service that is
flagged for later, and `api/app/hermes_ops.py` is only an internal endpoint FOR that gateway (the
gateway is its sole intended caller, and nothing in production calls it). With Rust out of scope
neither half runs, so the orchestration belongs in Python.

This keeps the gateway's guarantees and drops the service boundary. Hermes stays an UNTRUSTED
PLANNER: it is asked for a typed plan and everything it says is re-checked against Concierge's own
records before any effect. Concierge remains the record, the permission boundary and the executor.

The properties worth keeping, each failing CLOSED:
  - a closed set of operations. No shell, SQL, URL-fetch or send operation, because sending is a
    policy outcome rather than something a planner may ask for;
  - nothing customer-facing in shadow mode, which is the default;
  - a human takeover blocks customer effects but never stops a to-do being noted;
  - an unknown operation is refused rather than assumed harmless;
  - a revoked channel is revoked, per channel;
  - a malformed, oversized or tenant-smuggling plan is refused WHOLE -- one bad part rejects the
    plan rather than executing the good parts;
  - the recipient must already belong to the case;
  - an approval binds the EXACT content approved, so editing a draft afterwards voids it.
"""
import pytest

from app import hermes_orchestrator

TENANT = {
    "id": "11111111-1111-1111-1111-111111111111",
    "slug": "fixture",
    "name": "Fixture Business",
    "timezone": "Pacific/Auckland",
    "default_country_code": "64",
    "sla_minutes": 60,
}

LEAD = {
    "id": "22222222-2222-2222-2222-222222222222",
    "tenant_id": TENANT["id"],
    "name": "Hana",
    "phone": "+6421555123",
    "email": "hana@example.com",
    "created_at": "2026-11-10T00:00:00+00:00",
    "status": "new",
}


def _ctx(**over):
    base = {"autonomy": "draft_review", "paused": False, "email_send": True, "sms_send": True}
    base.update(over)
    return base


# ---------------------------------------------------------------- operation allowlist


def test_the_operation_set_is_closed_and_has_no_dangerous_member():
    """No operation may shell out, run SQL, fetch a URL or send.

    Sending is a policy outcome, not a tool: if a planner could ask to send directly then every
    other check would be optional.
    """
    ops = hermes_orchestrator.OPERATIONS
    assert ops, "the allowlist must not be empty"
    for forbidden in ("shell", "exec", "sql", "query_db", "fetch_url", "http_get", "send_email", "send_sms"):
        assert forbidden not in ops, forbidden


def test_read_only_and_mutating_operations_do_not_overlap():
    assert hermes_orchestrator.READ_ONLY <= hermes_orchestrator.OPERATIONS
    assert not (hermes_orchestrator.READ_ONLY & hermes_orchestrator.MUTATING)


# ---------------------------------------------------------------- permission decisions


def test_shadow_mode_permits_nothing_customer_facing():
    """Shadow is the default autonomy and must be genuinely inert."""
    perms = hermes_orchestrator.permit(_ctx(autonomy="shadow"), "prepare_reply")
    assert perms["allowed"] is False
    assert perms["reason"]


def test_a_taken_over_case_permits_no_customer_facing_operation():
    perms = hermes_orchestrator.permit(_ctx(paused=True), "prepare_reply")
    assert perms["allowed"] is False
    assert "takeover" in perms["reason"].lower()


def test_a_taken_over_case_still_allows_internal_work():
    """Taking over a conversation must not stop the assistant noting a to-do."""
    assert hermes_orchestrator.permit(_ctx(paused=True), "create_task")["allowed"] is True


def test_a_revoked_channel_is_refused_on_that_channel_only():
    assert hermes_orchestrator.permit(_ctx(email_send=False), "prepare_reply", channel="email")["allowed"] is False
    assert hermes_orchestrator.permit(_ctx(email_send=False), "prepare_reply", channel="sms")["allowed"] is True


def test_an_unknown_operation_is_refused_by_default():
    """A permission check must never say yes because it did not recognise the operation."""
    perms = hermes_orchestrator.permit(_ctx(), "send_everything")
    assert perms["allowed"] is False
    assert "unknown" in perms["reason"].lower()


def test_widening_autonomy_does_not_widen_the_allowlist():
    assert hermes_orchestrator.permit(_ctx(autonomy="auto_routine"), "delete_everything")["allowed"] is False


def test_auto_routine_permits_known_customer_facing_work():
    assert hermes_orchestrator.permit(_ctx(autonomy="auto_routine"), "prepare_reply", channel="sms")["allowed"] is True


def test_every_permission_answer_explains_itself():
    for outcome in (
        hermes_orchestrator.permit(_ctx(), "prepare_reply"),
        hermes_orchestrator.permit(_ctx(autonomy="shadow"), "prepare_reply"),
        hermes_orchestrator.permit(_ctx(), "nonsense"),
    ):
        assert isinstance(outcome["allowed"], bool)
        assert outcome["reason"]


# ---------------------------------------------------------------- plan validation


def test_a_well_formed_plan_is_accepted():
    plan = {"confidence": 0.9, "actions": [{"op": "prepare_reply", "params": {}}]}
    result = hermes_orchestrator.validate_plan(plan)
    assert result["ok"] is True
    assert result["plan"]["actions"][0]["op"] == "prepare_reply"


def test_an_unknown_operation_rejects_the_whole_plan():
    """One bad part rejects the plan rather than executing the good parts."""
    plan = {"confidence": 0.9, "actions": [
        {"op": "prepare_reply", "params": {}},
        {"op": "send_everything", "params": {}},
    ]}
    result = hermes_orchestrator.validate_plan(plan)
    assert result["ok"] is False
    assert "unknown" in result["reason"].lower()


def test_a_plan_carrying_a_tenant_is_refused():
    """The tenant comes from the token, never from model output."""
    plan = {"confidence": 0.9, "tenant_id": "33333333-3333-3333-3333-333333333333",
            "actions": [{"op": "prepare_reply", "params": {}}]}
    result = hermes_orchestrator.validate_plan(plan)
    assert result["ok"] is False
    assert "tenant" in result["reason"].lower()


def test_a_plan_carrying_credentials_is_refused():
    """A model must not be able to smuggle in its own capability."""
    for field in ("capability", "capability_token", "token"):
        plan = {"confidence": 0.9, field: "forged", "actions": [{"op": "prepare_reply", "params": {}}]}
        assert hermes_orchestrator.validate_plan(plan)["ok"] is False, field


def test_confidence_outside_zero_to_one_is_refused():
    for bad in (-0.1, 1.5, "high", None):
        plan = {"confidence": bad, "actions": [{"op": "prepare_reply", "params": {}}]}
        assert hermes_orchestrator.validate_plan(plan)["ok"] is False, bad


def test_a_non_object_plan_is_refused():
    for bad in ("just text", [], None, 42):
        assert hermes_orchestrator.validate_plan(bad)["ok"] is False, bad


def test_control_characters_are_refused():
    """Control characters can smuggle structure into a downstream renderer."""
    plan = {"confidence": 0.9, "actions": [{"op": "prepare_reply", "params": {"subject": "a\x00b"}}]}
    assert hermes_orchestrator.validate_plan(plan)["ok"] is False


def test_an_oversized_plan_is_refused():
    plan = {"confidence": 0.9, "actions": [{"op": "prepare_reply", "params": {"body": "x" * 200_000}}]}
    assert hermes_orchestrator.validate_plan(plan)["ok"] is False


def test_too_many_actions_is_refused():
    plan = {"confidence": 0.9, "actions": [{"op": "prepare_reply", "params": {}}] * 200}
    assert hermes_orchestrator.validate_plan(plan)["ok"] is False


# ---------------------------------------------------------------- recipient binding


def test_a_recipient_who_is_not_on_the_case_is_refused():
    """Prevents a planner aiming a reply at an address it invented."""
    assert hermes_orchestrator.recipient_on_case(LEAD, "hana@example.com", TENANT) is True
    assert hermes_orchestrator.recipient_on_case(LEAD, "attacker@example.com", TENANT) is False


def test_the_case_recipient_matches_across_phone_spellings():
    """A case phone must match whatever spelling the planner echoes back."""
    for spelling in ("+6421555123", "021555123", "6421555123", "021 555 123"):
        assert hermes_orchestrator.recipient_on_case(LEAD, spelling, TENANT) is True, spelling


# ---------------------------------------------------------------- approval binding


def test_an_approval_covers_only_the_exact_content_approved():
    """Editing a draft after approval must void the approval.

    Otherwise 'approve' would mean 'approve whatever follows', which is how an unreviewed message
    reaches a customer.
    """
    kw = dict(tenant_id=TENANT["id"], case_id=LEAD["id"], channel="email",
              recipient="hana@example.com", subject="Your quote")
    approved = hermes_orchestrator.approval_fingerprint(body="It is $50.", **kw)
    assert approved == hermes_orchestrator.approval_fingerprint(body="It is $50.", **kw)
    assert approved != hermes_orchestrator.approval_fingerprint(body="It is $500.", **kw)


def test_an_approval_is_scoped_to_its_tenant():
    a = hermes_orchestrator.approval_fingerprint(
        tenant_id=TENANT["id"], case_id=LEAD["id"], channel="sms",
        recipient="+6421555123", subject="", body="hi")
    b = hermes_orchestrator.approval_fingerprint(
        tenant_id="99999999-9999-9999-9999-999999999999", case_id=LEAD["id"], channel="sms",
        recipient="+6421555123", subject="", body="hi")
    assert a != b


# ---------------------------------------------------------------- response deadlines


def test_deadline_is_arrival_plus_the_tenant_target():
    due = hermes_orchestrator.response_deadline(TENANT, LEAD, now="2026-11-10T00:30:00+00:00")
    assert due == "2026-11-10T01:00:00+00:00"


def test_reading_a_case_later_does_not_move_its_deadline():
    """The clock starts when the customer wrote, not when anything reads the case."""
    a = hermes_orchestrator.response_deadline(TENANT, LEAD, now="2026-11-10T00:10:00+00:00")
    b = hermes_orchestrator.response_deadline(TENANT, LEAD, now="2026-11-10T05:00:00+00:00")
    assert a == b == "2026-11-10T01:00:00+00:00"


def test_no_target_means_no_deadline_is_invented():
    assert hermes_orchestrator.response_deadline({**TENANT, "sla_minutes": 0}, LEAD) is None
    assert hermes_orchestrator.response_deadline({**TENANT, "sla_minutes": None}, LEAD) is None
    assert hermes_orchestrator.response_deadline(TENANT, {**LEAD, "created_at": None}) is None


def test_lateness_is_reported():
    state = hermes_orchestrator.deadline_state(TENANT, LEAD, now="2026-11-10T02:00:00+00:00")
    assert state["overdue"] is True
    assert state["minutes_overdue"] == 60


def test_a_case_inside_its_window_is_not_overdue():
    state = hermes_orchestrator.deadline_state(TENANT, LEAD, now="2026-11-10T00:30:00+00:00")
    assert state["overdue"] is False
    assert state["minutes_remaining"] == 30


def test_a_later_message_does_not_reset_the_deadline():
    """A second SMS must not silently restart the business's clock."""
    now = "2026-11-10T02:00:00+00:00"
    touched = {**LEAD, "message": "and another thing"}
    assert (hermes_orchestrator.deadline_state(TENANT, LEAD, now=now)["due_at"]
            == hermes_orchestrator.deadline_state(TENANT, touched, now=now)["due_at"])


def test_deadline_state_with_the_feature_off_is_explicit():
    state = hermes_orchestrator.deadline_state({**TENANT, "sla_minutes": 0}, LEAD)
    assert state == {"due_at": None, "overdue": False, "minutes_overdue": 0, "minutes_remaining": None}
