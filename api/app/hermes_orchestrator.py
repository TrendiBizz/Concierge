"""Hermes orchestration in Python: an untrusted planner behind a closed allowlist.

WHY THIS IS PYTHON AND NOT THE GATEWAY SERVICE
The Rust `hermes-gateway` has the right security design, but it is a separate service and the Rust
workstream is flagged for later. `api/app/hermes_ops.py` is only the internal endpoint that gateway
calls; nothing in production calls it. So neither half of the original design runs. Rather than
leave the capability dead, the orchestration is expressed here, in-process, without the service
boundary. `hermes_ops.py` is left in place and untouched for whenever Rust is revisited.

THE TRUST MODEL, unchanged from the original design
Hermes is an UNTRUSTED PLANNER. It is asked for one typed JSON plan and nothing it says is believed:

  - the tenant and case come from OUR records, never from the plan. A plan that carries them is
    rejected outright, so a model cannot aim work at another business or another customer;
  - every operation must be in a closed allowlist. There is deliberately no shell, SQL, URL-fetch
    or send operation: sending is a policy outcome in Concierge, not a tool a planner may ask for;
  - one bad part rejects the WHOLE plan rather than executing the good parts;
  - the recipient must already belong to the case;
  - a human takeover blocks customer-facing effects but never stops an internal to-do;
  - an approval binds the exact content approved, so editing a draft afterwards voids it.

NOTHING HERE SENDS. Customer-facing work becomes a human-reviewed draft or a to-do; the owner
approves in the portal, which uses the existing outbox. That is deliberate: the safest default is
that an unreviewed message does not reach a customer.

This module is pure policy and pure functions. It does not talk to a model or a database, which is
what makes every rule directly testable.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from .contact import contact_key

# ------------------------------------------------------------------ trust level

AUTONOMY_LEVELS = ("shadow", "draft_review", "auto_routine")
DEFAULT_AUTONOMY = "shadow"

# ------------------------------------------------------------------ operations

# The closed allowlist. Deliberately absent: any shell, SQL, HTTP-fetch or direct send. If a planner
# could ask to send, every other check would become optional.
OPERATIONS = frozenset({
    "get_case_context",
    "search_business_knowledge",
    "check_availability",
    "draft_reply",
    "prepare_reply",
    "create_task",
    "schedule_followup",
    "escalate_case",
})

READ_ONLY = frozenset({
    "get_case_context",
    "search_business_knowledge",
    "check_availability",
})

MUTATING = OPERATIONS - READ_ONLY

# Effects a customer can observe. These are what a human takeover must stop.
CUSTOMER_FACING = frozenset({
    "draft_reply",
    "prepare_reply",
    "schedule_followup",
})

# Fields a model must never be able to set: they come from our own records.
FORBIDDEN_PLAN_FIELDS = frozenset({
    "tenant_id", "tenant", "case_id", "lead_id",
    "capability", "capability_token", "token", "secret",
})

# ------------------------------------------------------------------ limits

MAX_PLAN_BYTES = 64_000
MAX_ACTIONS = 20
MAX_PARAM_BYTES = 8_000


def _reason(allowed: bool, why: str) -> dict:
    """Every answer carries a machine-readable reason, so no caller has to infer one."""
    return {"allowed": bool(allowed), "reason": why}


def permit(ctx: dict, op: str, channel: str = "") -> dict:
    """May this operation run, given the case context? Fails CLOSED on every uncertainty.

    `ctx` is assembled by Concierge from its own records: autonomy for the tenant, whether a human
    has taken the case over, and which channels are currently authorized. Nothing in it comes from
    the model.
    """
    if op not in OPERATIONS:
        # Refusing an unrecognised operation is the whole point: a check that returned "allowed"
        # because it did not understand the operation would be worse than no check at all.
        return _reason(False, f"unknown operation {op!r}; not in the allowlist")

    autonomy = ctx.get("autonomy") or DEFAULT_AUTONOMY
    if autonomy not in AUTONOMY_LEVELS:
        return _reason(False, f"unknown autonomy {autonomy!r}")

    if autonomy == "shadow":
        return _reason(False, "shadow mode: nothing customer-facing or mutating runs")

    if ctx.get("paused") and op in CUSTOMER_FACING:
        # Human takeover closes customer effects. It must NOT block internal notes, or taking over a
        # conversation would also blind the assistant's record-keeping.
        return _reason(False, f"human takeover: {op} may not reach the customer")

    if channel and op in CUSTOMER_FACING:
        permission = {"email": "email_send", "sms": "sms_send"}.get(channel)
        if permission and not ctx.get(permission):
            # A revocation is per channel, so it must not silently disable the other one.
            return _reason(False, f"channel {channel} is not authorized for sending")

    if autonomy == "draft_review" and op in CUSTOMER_FACING:
        return _reason(True, "draft_review: a human must approve before this reaches the customer")

    return _reason(True, "permitted")


# ------------------------------------------------------------------ plan validation


def _scan_for_forbidden(value, path: str = "") -> str | None:
    """Find a smuggled identity or credential anywhere in the plan, at any depth."""
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_PLAN_FIELDS:
                return f"plan sets {key!r}, which only Concierge may set"
            found = _scan_for_forbidden(item, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _scan_for_forbidden(item, path)
            if found:
                return found
    return None


def _has_control_chars(value) -> bool:
    """Control characters can smuggle structure into a downstream renderer."""
    if isinstance(value, str):
        return any(ord(ch) < 32 and ch not in "\t\n\r" for ch in value)
    if isinstance(value, dict):
        return any(_has_control_chars(k) or _has_control_chars(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_has_control_chars(v) for v in value)
    return False


def validate_plan(plan) -> dict:
    """Accept one typed plan, or reject it whole. Returns {'ok': bool, ...}.

    Rejection is all-or-nothing on purpose. Executing the valid parts of a partly-invalid plan would
    let a planner append a disallowed action and rely on the rest being carried out.
    """
    if not isinstance(plan, dict):
        return {"ok": False, "reason": "plan must be a single JSON object"}

    try:
        encoded = json.dumps(plan)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "plan is not serialisable as JSON"}
    if len(encoded.encode()) > MAX_PLAN_BYTES:
        return {"ok": False, "reason": "plan is too large"}

    smuggled = _scan_for_forbidden(plan)
    if smuggled:
        return {"ok": False, "reason": smuggled}

    if _has_control_chars(plan):
        return {"ok": False, "reason": "plan contains control characters"}

    confidence = plan.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return {"ok": False, "reason": "confidence must be a number in 0..1"}
    if not (0.0 <= float(confidence) <= 1.0):
        return {"ok": False, "reason": "confidence must be in 0..1"}

    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        return {"ok": False, "reason": "plan must contain a non-empty actions list"}
    if len(actions) > MAX_ACTIONS:
        return {"ok": False, "reason": f"plan has more than {MAX_ACTIONS} actions"}

    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            return {"ok": False, "reason": f"action {index} is not an object"}
        op = action.get("op")
        if op not in OPERATIONS:
            return {"ok": False, "reason": f"unknown operation {op!r} at action {index}"}
        params = action.get("params", {})
        if params is not None and not isinstance(params, dict):
            return {"ok": False, "reason": f"action {index} params must be an object"}
        if params:
            try:
                if len(json.dumps(params).encode()) > MAX_PARAM_BYTES:
                    return {"ok": False, "reason": f"action {index} params are too large"}
            except (TypeError, ValueError):
                return {"ok": False, "reason": f"action {index} params are not serialisable"}

    return {"ok": True, "plan": plan, "reason": "valid"}


# ------------------------------------------------------------------ recipient binding


def recipient_on_case(lead: dict, recipient: str, tenant: dict | None = None) -> bool:
    """True when this recipient already belongs to the case.

    Stops a planner aiming a reply at an address it invented. Phone spellings are compared through
    contact_key with the TENANT's dialling country, so the national and international forms of one
    number are the same recipient rather than two different ones.
    """
    if not recipient:
        return False
    from . import casetimeline

    cc = casetimeline.tenant_country_code(tenant)
    want = contact_key(recipient, cc)
    for field in ("email", "phone"):
        existing = lead.get(field) or ""
        if existing and contact_key(existing, cc) == want:
            return True
    return False


# ------------------------------------------------------------------ approval binding


def approval_fingerprint(*, tenant_id, case_id, channel: str, recipient: str,
                         subject: str = "", body: str = "") -> str:
    """A digest binding an approval to the EXACT content approved.

    Without this, "approve" would mean "approve whatever this draft becomes", so an edit made after
    review would still send. Every field that a customer can observe is included, and the tenant and
    case are included so an approval cannot be replayed onto another business or customer.
    """
    material = "\x00".join([
        str(tenant_id), str(case_id), str(channel or ""), str(recipient or ""),
        str(subject or ""), str(body or ""),
    ])
    return hashlib.sha256(material.encode()).hexdigest()


# ------------------------------------------------------------------ response deadlines


def _parse(moment) -> datetime | None:
    if moment is None:
        return None
    if isinstance(moment, datetime):
        return moment
    try:
        return datetime.fromisoformat(str(moment).replace("Z", "+00:00"))
    except ValueError:
        return None


def response_deadline(tenant: dict, lead: dict, now=None) -> str | None:
    """When this enquiry should have been answered by, or None when no promise applies.

    Derived from the enquiry's ARRIVAL plus the tenant's target, never from the current time. That
    matters: if it were measured from now, reading a case twice would move its deadline and a case
    could never be shown as late. A tenant with no target has made no promise, so no deadline is
    invented for it.

    `now` is accepted only so callers can pass a clock; it deliberately does not affect the result.
    """
    minutes = int(tenant.get("sla_minutes") or 0)
    if minutes <= 0:
        return None
    arrived = _parse(lead.get("created_at"))
    if arrived is None:
        return None
    if arrived.tzinfo is None:
        arrived = arrived.replace(tzinfo=timezone.utc)
    return (arrived + timedelta(minutes=minutes)).astimezone(timezone.utc).isoformat()


def deadline_state(tenant: dict, lead: dict, now=None) -> dict:
    """The deadline and whether the case is already late, as a flat machine-readable record."""
    due = response_deadline(tenant, lead)
    if due is None:
        return {"due_at": None, "overdue": False, "minutes_overdue": 0, "minutes_remaining": None}

    due_at = datetime.fromisoformat(due)
    current = _parse(now) or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    if current >= due_at:
        return {
            "due_at": due,
            "overdue": True,
            "minutes_overdue": int((current - due_at).total_seconds() // 60),
            "minutes_remaining": 0,
        }
    return {
        "due_at": due,
        "overdue": False,
        "minutes_overdue": 0,
        "minutes_remaining": int((due_at - current).total_seconds() // 60),
    }
