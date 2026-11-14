from app import inbound_readiness

GOOD = {
    "api_enabled": True,
    "owner_accounts": 1,
    "consent_authorized": True,
    "reply_address": "reply-abc@trendibizz.com",
    "mailbox_enabled": True,
    "worker_rule": "enabled",
    "sidecar_ok": True,
    "rejected_24h": 0,
}


def test_full_chain_is_ok():
    result = inbound_readiness.evaluate(dict(GOOD))
    assert result["ok"] is True
    assert result["blocked"] == []
    assert all(result["checks"][name]["ok"] for name in inbound_readiness.ORDER)


def test_missing_consent_blocks_and_names_the_fix():
    # The 2026-11-12 incident: everything else looked connected.
    facts = dict(GOOD, consent_authorized=False)
    result = inbound_readiness.evaluate(facts)
    assert result["ok"] is False
    assert [b["check"] for b in result["blocked"]] == ["consent"]
    assert "Permissions" in result["blocked"][0]["message"]


def test_no_owner_account_blocks():
    result = inbound_readiness.evaluate(dict(GOOD, owner_accounts=0))
    assert result["ok"] is False
    assert "owner_account" in [b["check"] for b in result["blocked"]]


def test_missing_reply_address_or_rule_blocks():
    assert inbound_readiness.evaluate(dict(GOOD, reply_address=""))["ok"] is False
    assert inbound_readiness.evaluate(dict(GOOD, worker_rule="missing"))["ok"] is False


def test_unknown_cloudflare_state_is_not_a_failure():
    # If the token is absent we cannot ask Cloudflare; do not cry wolf.
    result = inbound_readiness.evaluate(dict(GOOD, worker_rule="unknown"))
    assert result["ok"] is not False


def test_sidecar_down_is_blocked_but_reported_separately():
    result = inbound_readiness.evaluate(dict(GOOD, sidecar_ok=False))
    assert result["ok"] is False
    assert result["checks"]["sidecar"]["detail"] == "unreachable"


def test_rejections_are_surfaced_as_warnings():
    result = inbound_readiness.evaluate(dict(GOOD, rejected_24h=3))
    assert result["ok"] is True
    assert result["warnings"][0]["check"] == "rejections"


def test_garbage_input_does_not_raise():
    result = inbound_readiness.evaluate({})
    assert result["ok"] is False
    assert len(result["blocked"]) >= 1


def test_a_failing_test_tenant_is_reported_but_does_not_fail_the_chain():
    """A fictitious business cannot complete the chain — no real owner grants consent.

    On 2026-11-15 the hourly health check mailed "trendi-fictitious: consent" (counts fail=1)
    while every real tenant was green. That alert talked over the ones that mattered.
    """
    tenants = [
        {"slug": "acme", "ok": True},
        {"slug": "trendi-fictitious", "ok": False, "is_test": True,
         "blocked": [{"check": "consent"}]},
    ]
    summary = inbound_readiness.summarise(tenants)
    assert summary["ok"] is True
    assert [t["slug"] for t in summary["test_broken"]] == ["trendi-fictitious"]
    assert summary["live_broken"] == []


def test_a_failing_real_tenant_still_fails_the_chain():
    tenants = [
        {"slug": "acme", "ok": False, "blocked": [{"check": "consent"}]},
        {"slug": "trendi-fictitious", "ok": False, "is_test": True},
    ]
    summary = inbound_readiness.summarise(tenants)
    assert summary["ok"] is False
    assert [t["slug"] for t in summary["live_broken"]] == ["acme"]
    assert summary["test_broken"] == [{"slug": "trendi-fictitious", "ok": False, "is_test": True}]


def test_all_green_tenants_summarise_as_ok():
    summary = inbound_readiness.summarise([{"slug": "a", "ok": True}, {"slug": "b", "ok": True}])
    assert summary == {"ok": True, "green": 2, "live_broken": [], "test_broken": []}
