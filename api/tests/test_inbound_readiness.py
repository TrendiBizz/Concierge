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
