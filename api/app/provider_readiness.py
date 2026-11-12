"""What is actually blocking each provider, and what is needed to unblock it.

This exists because "the provider is not approved yet" is not an actionable statement. The
operational question is always the same: WHICH step is next, on WHICH provider, and does it need a
human in a dashboard or can the code do it?

Readiness is reported in four kinds, and the distinction is the whole point:

  ready        everything the SOFTWARE can verify is satisfied.
  action_needed a human must do something outside this repository -- approve an app in a provider
               dashboard, sign in and grant access, buy a number. Nothing in the code can do it.
  unconfigured configuration must be checked or supplied.
  code_needed  implementation remains; this is not a provider approval.

Nothing here invents a status. A provider is only reported as ready when the configuration it needs
is actually present, and the check names the exact setting involved. This deliberately does NOT
claim that a provider accepts traffic: only the provider can say that, and a green tick derived from
our own config would be exactly the false assurance the audit warned about.
"""
from __future__ import annotations

import json

from .config import get_settings

SOCIAL_PLATFORMS = (
    "facebook", "instagram", "linkedin", "tiktok", "x", "google_business",
)


def _step(what: str, kind: str, detail: str = "", setting: str = "") -> dict:
    """One readiness step. `kind` is ready | action_needed | unconfigured | code_needed."""
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
            "Verify existing provider applications",
            "action_needed",
            "Check the existing provider applications and redirect URIs before creating anything. "
            "This configuration check does not determine registration or review status.",
        ),
        _step(
            "Verify provider review status where required",
            "action_needed",
            "Check Meta permissions, LinkedIn Pages and TikTok reviews. Google Business Profile API "
            "access, OAuth production verification and per-business consent are separate gates. "
            "A pending review must not be submitted again merely because this report cannot read it.",
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
        "summary": "Social routes exist; provider review, customer grants and live acceptance must be verified separately.",
        "platforms": list(SOCIAL_PLATFORMS),
        "steps": steps,
        # A provider status can only come from the social service itself.
        "verifiable_here": ["service_reachable"],
    }


def _telephony() -> dict:
    s = get_settings()
    from . import phone_sip
    from fastapi import HTTPException

    try:
        connections = json.loads(s.xai_sip_connections or "{}")
    except (ValueError, TypeError):
        connections = {}
    has_sip = False
    if isinstance(connections, dict):
        for ident in connections:
            try:
                phone_sip.connection_config(ident)
            except HTTPException:
                continue
            has_sip = True
            break
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
    return {
        "area": "payments",
        "summary": "Existing Stripe website checkout is separate from Concierge invoicing and subscription reconciliation.",
        "steps": [
            _step(
                "Verify existing Stripe checkout",
                "action_needed",
                "Preserve the existing Stripe website payment links. Confirm the intended product, "
                "currency and account rather than opening a replacement account. This endpoint "
                "does not query Stripe or prove a successful payment.",
            ),
            _step(
                "Configure the Concierge subscription link",
                "unconfigured",
                "The website's Concierge subscription link was empty in the inspected source. "
                "Check the deployed website and existing Stripe products before wiring a link. "
                "This API cannot read that separate website configuration.",
                "website site/products.js: concierge.monthly.stripeLink",
            ),
            _step(
                "Implement and verify payment reconciliation",
                "code_needed",
                "The invoicing module tracks manual status. Automatic subscription activation, "
                "verified webhook handling and reconciliation are code work, not a dashboard approval. "
                "They must be implemented and tested if required for Concierge billing.",
            ),
        ],
        "verifiable_here": ["invoicing"],
    }


def _included() -> dict:
    """What Concierge already does for a business, so nobody has to read a changelog to know.

    One step per shipped capability. A capability whose only dependency is a per-tenant toggle is
    `ready`; one that needs an account or setting is reported by the area that owns it. Keep this
    list to things a customer would recognise as a benefit, not to internals.
    """
    steps = [
        _step(
            "A summary of every call",
            "ready",
            "Each finished call gets a short summary, an outcome (booked, quote requested, ring back, "
            "unresolved…), how the caller felt, and — for a callback or an unresolved call — a task "
            "for you. Visible in Studio, Bookings, 'Recent calls'.",
            "call_insights / GET /owner/call-insights",
        ),
        _step(
            "One timeline per customer",
            "ready",
            "Studio → Contacts shows every email, text, call, chat, quote and appointment for a "
            "person in one thread, and a repeat customer is merged onto the same record instead of "
            "appearing twice. Take over pauses the assistant for that one customer.",
            "GET /owner/contacts",
        ),
        _step(
            "Missed-call text-back",
            "ready",
            "A caller who hangs up before saying anything gets one text back with the booking link, "
            "and is recorded as an enquiry. On by default for every business with SMS enabled; "
            "switch it off per business in Studio, Setup.",
            "tenants.missed_call_textback",
        ),
    ]
    return {
        "area": "included",
        "summary": "Capabilities that are already live for every business, and how to switch them off.",
        "steps": steps,
        "verifiable_here": ["runtime_behaviour"],
    }


def report() -> dict:
    """Provider checks, configuration and code work. Reads configuration; changes nothing."""
    areas = {"social": _social(), "telephony": _telephony(), "payments": _payments(),
             "included": _included()}
    blocking = [
        {"area": name, "what": step["what"]}
        for name, area in areas.items()
        for step in area["steps"]
        if step["status"] == "action_needed"
    ]
    code = [
        {"area": name, "what": step["what"]}
        for name, area in areas.items() for step in area["steps"]
        if step["status"] == "code_needed"
    ]
    configuration = [
        {"area": name, "what": step["what"]}
        for name, area in areas.items() for step in area["steps"]
        if step["status"] == "unconfigured"
    ]
    return {
        "areas": areas,
        "needs_code": code,
        "needs_code_count": len(code),
        "needs_configuration": configuration,
        "needs_configuration_count": len(configuration),
        # Unknown external review state is a verification task, not proof of rejection.
        "needs_human": blocking,
        "needs_human_count": len(blocking),
        "note": (
            "A status of ready means the SOFTWARE side is satisfied, not that the provider has "
            "accepted anything. Only the provider can confirm that, and this report deliberately "
            "does not imply otherwise."
        ),
    }
