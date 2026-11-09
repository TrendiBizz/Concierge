"""What is actually blocking each provider, and what is needed to unblock it.

This exists because "the provider is not approved yet" is not an actionable statement. The
operational question is always the same: WHICH step is next, on WHICH provider, and does it need a
human in a dashboard or can the code do it?

Readiness is reported in three kinds, and the distinction is the whole point:

  ready        everything the SOFTWARE can verify is satisfied.
  action_needed a human must do something outside this repository -- approve an app in a provider
               dashboard, sign in and grant access, buy a number. Nothing in the code can do it.
  unconfigured the operator has not set the value yet, which is also a human action but a local one.

Nothing here invents a status. A provider is only reported as ready when the configuration it needs
is actually present, and the check names the exact setting involved. This deliberately does NOT
claim that a provider accepts traffic: only the provider can say that, and a green tick derived from
our own config would be exactly the false assurance the audit warned about.
"""
from __future__ import annotations

from .config import get_settings

SOCIAL_PLATFORMS = (
    "facebook", "instagram", "linkedin", "tiktok", "x", "google_business", "mastodon",
)


def _step(what: str, kind: str, detail: str = "", setting: str = "") -> dict:
    """One readiness step. `kind` is ready | action_needed | unconfigured."""
    step = {"what": what, "status": kind, "detail": detail}
    if setting:
        step["setting"] = setting
    return step


def _social() -> dict:
    s = get_settings()
    steps = [
        _step(
            "Run the social service",
            "ready" if s.social_service_enabled and len(s.social_concierge_key or "") >= 32 else "unconfigured",
            "The Rust social service holds the provider tokens; it is a separate internal process.",
            "SOCIAL_SERVICE_ENABLED / SOCIAL_CONCIERGE_KEY",
        ),
        _step(
            "Register each provider application",
            "action_needed",
            "Each network needs its own app registered and its redirect URI pointed at this "
            "deployment. This happens in the provider's developer dashboard, by the account owner.",
        ),
        _step(
            "Submit for provider review where required",
            "action_needed",
            "Meta (6 permissions), LinkedIn Pages, TikTok Login Kit and Google Business Profile each "
            "require an approval that only the account owner can request and only the provider can grant.",
        ),
        _step(
            "Grant access per customer",
            "action_needed",
            "Even with an approved app, each business owner signs in once and grants access. Per "
            "tenant, by design: one customer's grant must never cover another.",
        ),
    ]
    return {
        "area": "social",
        "summary": "Fully implemented and routed; blocked on provider approval and per-customer grants.",
        "platforms": list(SOCIAL_PLATFORMS),
        "steps": steps,
        # A provider status can only come from the social service itself.
        "verifiable_here": ["service_reachable"],
    }


def _telephony() -> dict:
    s = get_settings()
    has_sip = bool((s.xai_sip_connections or "").strip() not in ("", "{}"))
    steps = [
        _step(
            "Choose a carrier path",
            "action_needed",
            "Either a carrier/SIP trunk that forwards a real number here, or an xAI SIP connection. "
            "Both are accounts to open, not code to write.",
        ),
        _step(
            "Record the SIP connection",
            "ready" if has_sip else "unconfigured",
            "Maps an inbound connection to a tenant.",
            "XAI_SIP_CONNECTIONS",
        ),
        _step(
            "Enable the tenant phone line",
            "unconfigured",
            "Per tenant: PHONE_ENABLED is off by default, so no number answers until a business opts in.",
            "tenants.phone_enabled / phone_receptionist_enabled",
        ),
        _step(
            "Place one real inbound call",
            "action_needed",
            "The only proof that the path works end to end. Needs a real handset and a real number; "
            "no test harness can stand in for it.",
        ),
        _step(
            "Confirm recording consent and CRM capture",
            "action_needed",
            "Consent wording and the resulting recording/transcript must be checked on a real call.",
        ),
    ]
    return {
        "area": "telephony",
        "summary": "Webhook path and tenant gating exist; blocked on a carrier account and one real call.",
        "steps": steps,
        "verifiable_here": ["signature_validation", "route_registration"],
    }


def _payments() -> dict:
    steps = [
        _step(
            "Decide whether payments should process money at all",
            "action_needed",
            "Not an oversight: payments/README.md records this as 'a deliberate, separate decision, "
            "not a default'. Invoicing exists; taking card payments is a business decision with "
            "compliance consequences, so it is not enabled by implication.",
        ),
        _step(
            "Open a payment provider account",
            "action_needed",
            "Stripe or equivalent, in the business's own legal name, with its own bank account.",
        ),
        _step(
            "Implement the gateway against a feature flag",
            "unconfigured",
            "Deliberately not written yet. Doing it before the account exists would mean guessing the "
            "provider, the country and the payout model.",
        ),
    ]
    return {
        "area": "payments",
        "summary": "Invoicing only. No gateway by design, so there is nothing broken to fix.",
        "steps": steps,
        "verifiable_here": ["invoicing"],
    }


def report() -> dict:
    """Every provider area with its next actionable step. Reads configuration; changes nothing."""
    areas = {"social": _social(), "telephony": _telephony(), "payments": _payments()}
    blocking = [
        {"area": name, "what": step["what"]}
        for name, area in areas.items()
        for step in area["steps"]
        if step["status"] != "ready"
    ]
    return {
        "areas": areas,
        # The honest headline: these need a person outside the repository, not another commit.
        "needs_human": blocking,
        "needs_human_count": len(blocking),
        "note": (
            "A status of ready means the SOFTWARE side is satisfied, not that the provider has "
            "accepted anything. Only the provider can confirm that, and this report deliberately "
            "does not imply otherwise."
        ),
    }
