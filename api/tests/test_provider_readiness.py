"""Provider readiness: what is blocking, and whether the code can unblock it.

The failure mode this guards against is a readiness report that says "ready" because it could not
tell. A green tick derived from our own configuration would be exactly the false assurance the audit
warned about, so the tests here check that the report:
  - reflects the REAL configuration rather than a hardcoded list;
  - never reports ready when a required setting is missing;
  - names the specific setting involved, so a step is actionable;
  - states plainly that only the provider can confirm acceptance.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app import provider_readiness


def _settings(**over):
    base = {
        "social_service_enabled": False,
        "social_concierge_key": "",
        "social_service_url": "http://127.0.0.1:4390",
        "phone_receptionist_enabled": False,
        "phone_voice_provider": "gemini_live",
        "gemini_api_key": "",
    }
    base.update(over)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------- shape


def test_the_report_covers_every_area_the_audit_names():
    with patch.object(provider_readiness, "get_settings", lambda: _settings()):
        rep = provider_readiness.report()
    # "included" is the customer-facing half of the report: what Concierge already does, so a
    # business never has to read a changelog to find out. It grows with every shipped capability.
    assert set(rep["areas"]) == {"social", "telephony", "payments", "included"}


def test_every_shipped_capability_is_advertised_in_the_report():
    """New features must be discoverable from onboarding, not only from a release note."""
    with patch.object(provider_readiness, "get_settings", lambda: _settings()):
        rep = provider_readiness.report()
    included = {step["what"] for step in rep["areas"]["included"]["steps"]}
    assert "Missed-call text-back" in included
    for step in rep["areas"]["included"]["steps"]:
        assert step["status"] in ("ready", "action_needed", "unconfigured")
        assert "Studio" in step["detail"] or "switch" in step["detail"].lower()


def test_every_step_has_a_status_and_an_explanation():
    with patch.object(provider_readiness, "get_settings", lambda: _settings()):
        rep = provider_readiness.report()
    for name, area in rep["areas"].items():
        assert area["steps"], name
        for step in area["steps"]:
            assert step["status"] in ("ready", "action_needed", "unconfigured", "code_needed"), step
            assert step["what"], step
            assert step["detail"], step


def test_the_report_never_claims_a_provider_has_accepted_anything():
    """Our config cannot prove a provider's approval, and the report must say so."""
    with patch.object(provider_readiness, "get_settings", lambda: _settings()):
        rep = provider_readiness.report()
    assert "provider" in rep["note"].lower()
    for area in rep["areas"].values():
        assert "verifiable_here" in area, "each area must state what it can actually verify"


# ---------------------------------------------------------------- derived from real config


def test_the_social_service_step_reflects_the_real_configuration():
    with patch.object(provider_readiness, "get_settings", lambda: _settings()):
        off = provider_readiness.report()["areas"]["social"]["steps"][0]
    assert off["status"] == "unconfigured", "a disabled social module must not read as ready"

    with patch.object(provider_readiness, "get_settings",
                      lambda: _settings(social_service_enabled=True)):
        on = provider_readiness.report()["areas"]["social"]["steps"][0]
    assert on["status"] == "ready"


def test_the_telephony_gemini_step_reflects_the_real_configuration():
    with patch.object(provider_readiness, "get_settings", lambda: _settings()):
        step = provider_readiness.report()["areas"]["telephony"]["steps"][1]
    assert step["status"] == "unconfigured"

    with patch.object(provider_readiness, "get_settings",
                      lambda: _settings(phone_receptionist_enabled=True, phone_voice_provider="gemini_live", gemini_api_key="test-key")):
        step = provider_readiness.report()["areas"]["telephony"]["steps"][1]
    assert step["status"] == "ready"


def test_missing_gemini_key_is_not_ready():
    with patch.object(provider_readiness, "get_settings",
                      lambda: _settings(phone_receptionist_enabled=True, phone_voice_provider="gemini_live", gemini_api_key="   ")):
        step = provider_readiness.report()["areas"]["telephony"]["steps"][1]
    assert step["status"] == "unconfigured"


# ---------------------------------------------------------------- actionability


def test_steps_name_the_setting_involved():
    """A step the operator cannot act on is not useful."""
    with patch.object(provider_readiness, "get_settings", lambda: _settings()):
        rep = provider_readiness.report()
    social = rep["areas"]["social"]["steps"][0]
    telephony = rep["areas"]["telephony"]["steps"][1]
    payments = rep["areas"]["payments"]["steps"][2]
    assert social.get("setting"), social
    assert telephony.get("setting"), telephony
    assert payments["status"] == "code_needed", payments


def test_blocking_work_is_listed_with_its_area():
    with patch.object(provider_readiness, "get_settings", lambda: _settings()):
        rep = provider_readiness.report()
    assert rep["needs_human_count"] == len(rep["needs_human"])
    assert rep["needs_human_count"] > 0, "with nothing configured there is work to do"
    for item in rep["needs_human"]:
        assert item["area"] in ("social", "telephony", "payments")
        assert item["what"]


def test_a_fully_configured_environment_still_lists_human_steps():
    """Provider approval is never satisfied by configuration, so it must always be listed."""
    with patch.object(provider_readiness, "get_settings",
                      lambda: _settings(social_service_enabled=True, social_concierge_key="k" * 32,
                                        phone_receptionist_enabled=True, gemini_api_key="k")):
        rep = provider_readiness.report()
    whats = " ".join(i["what"] for i in rep["needs_human"]).lower()
    assert "review" in whats or "approval" in whats, "provider approval must never be assumed done"
    assert rep["needs_human_count"] > 0


def test_payments_distinguishes_existing_checkout_from_unimplemented_reconciliation():
    """The absence of a gateway is deliberate, and the report must not imply a bug."""
    with patch.object(provider_readiness, "get_settings", lambda: _settings()):
        area = provider_readiness.report()["areas"]["payments"]
    assert "existing Stripe" in area["steps"][0]["detail"]
    assert area["steps"][2]["status"] == "code_needed"


def test_mastodon_is_not_a_required_provider():
    assert "mastodon" not in provider_readiness.SOCIAL_PLATFORMS


def test_code_work_is_not_misreported_as_a_dashboard_approval():
    with patch.object(provider_readiness, "get_settings", lambda: _settings()):
        rep = provider_readiness.report()
    assert rep["needs_code"], "unfinished payment integration must remain visible"
    assert all(x not in rep["needs_human"] for x in rep["needs_code"])
    assert rep["needs_code_count"] == len(rep["needs_code"])


def test_existing_stripe_is_not_reported_as_an_account_to_open():
    with patch.object(provider_readiness, "get_settings", lambda: _settings()):
        area = provider_readiness.report()["areas"]["payments"]
    text = " ".join(x["what"] + " " + x["detail"] for x in area["steps"]).lower()
    assert "existing stripe" in text
    assert "open a payment provider account" not in text
    assert "stripe" in area["summary"].lower()


@pytest.mark.parametrize("over", [
    {"phone_receptionist_enabled": False, "gemini_api_key": "k"},
    {"phone_receptionist_enabled": True, "gemini_api_key": ""},
    {"phone_receptionist_enabled": True, "phone_voice_provider": "legacy_twilio_tts", "gemini_api_key": "k"},
])
def test_incomplete_gemini_telephony_does_not_read_as_ready(over):
    with patch.object(provider_readiness, "get_settings", lambda: _settings(**over)):
        step = provider_readiness.report()["areas"]["telephony"]["steps"][1]
    assert step["status"] == "unconfigured"
