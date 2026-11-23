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
    assert summary == {"ok": True, "green": 2, "live_broken": [], "test_broken": [],
                       "onboarding": []}


def test_a_brand_new_tenant_is_onboarding_not_a_broken_chain():
    """Measured 2026-11-16: a tenant created to test the product had no owner account yet (the
    invitation was still in the inbox) and no consent, so the hourly check mailed a failure from
    the moment it existed. Onboarding is not a fault; the grace window is what makes it temporary."""
    tenants = [
        {"slug": "acme", "ok": True},
        {"slug": "trendibizz", "ok": False, "is_new": True,
         "blocked": [{"check": "owner_account"}, {"check": "consent"}]},
    ]
    summary = inbound_readiness.summarise(tenants)
    assert summary["ok"] is True, "a new tenant's missing owner account is not an outage"
    assert [t["slug"] for t in summary["onboarding"]] == ["trendibizz"]
    assert summary["live_broken"] == []


def test_the_grace_ends_and_the_same_tenant_becomes_a_real_failure():
    tenants = [{"slug": "trendibizz", "ok": False, "is_new": False,
                "blocked": [{"check": "owner_account"}]}]
    summary = inbound_readiness.summarise(tenants)
    assert summary["ok"] is False
    assert [t["slug"] for t in summary["live_broken"]] == ["trendibizz"]


def test_onboarding_never_masks_a_test_tenant_or_a_real_one():
    tenants = [
        {"slug": "real", "ok": False, "blocked": [{"check": "consent"}]},
        {"slug": "fictitious", "ok": False, "is_test": True},
        {"slug": "new", "ok": False, "is_new": True},
    ]
    summary = inbound_readiness.summarise(tenants)
    assert summary["ok"] is False
    assert [t["slug"] for t in summary["live_broken"]] == ["real"]
    assert [t["slug"] for t in summary["test_broken"]] == ["fictitious"]
    assert [t["slug"] for t in summary["onboarding"]] == ["new"]


# --- check_all runs concurrently and probes Cloudflare / sidecar once (2026-11-24) --------------
import asyncio
import time


class _Pool:
    async def fetch(self, *_a, **_k):
        return [{"id": i, "slug": f"t{i}", "is_test": False} for i in range(8)]


def _patch_all(monkeypatch, delay, calls):
    async def fake_check(tenant_id, *, cf_rules=None, sidecar=None):
        calls["cf_rules"].append(cf_rules)
        await asyncio.sleep(delay)
        return {"slug": f"t{tenant_id}", "ok": True, "is_test": False, "is_new": False}

    async def fake_cf(_s):
        calls["cf"] += 1
        await asyncio.sleep(delay)
        return []

    async def fake_sidecar(_s):
        calls["sidecar"] += 1
        return True

    monkeypatch.setattr(inbound_readiness.db, "pool", lambda: _Pool())
    monkeypatch.setattr(inbound_readiness, "check", fake_check)
    monkeypatch.setattr(inbound_readiness, "_cloudflare_rules", fake_cf)
    monkeypatch.setattr(inbound_readiness, "_sidecar_ok", fake_sidecar)


def test_check_all_runs_tenants_concurrently_and_probes_once(monkeypatch):
    calls = {"cf": 0, "sidecar": 0, "cf_rules": []}
    _patch_all(monkeypatch, 0.5, calls)
    start = time.monotonic()
    out = asyncio.run(inbound_readiness.check_all())
    elapsed = time.monotonic() - start
    # sequential would be 8 x 0.5 s + the probe = 4.5 s; concurrent is about 1.0 s
    assert elapsed < 2.0, elapsed
    assert calls["cf"] == 1 and calls["sidecar"] == 1
    assert [t["slug"] for t in out["tenants"]] == [f"t{i}" for i in range(8)]  # order kept
    assert out["ok"] is True and set(out) == {
        "ok", "test_tenants_failing", "onboarding", "checked_at", "tenants"}


def test_one_stuck_tenant_is_bounded_and_reported_not_fatal(monkeypatch):
    calls = {"cf": 0, "sidecar": 0, "cf_rules": []}
    _patch_all(monkeypatch, 0, calls)

    async def stuck_for_t3(tenant_id, **_k):
        if tenant_id == 3:
            await asyncio.sleep(60)
        return {"slug": f"t{tenant_id}", "ok": True, "is_test": False, "is_new": False}

    monkeypatch.setattr(inbound_readiness, "check", stuck_for_t3)
    monkeypatch.setattr(inbound_readiness, "PER_TENANT_TIMEOUT", 0.2)
    start = time.monotonic()
    out = asyncio.run(inbound_readiness.check_all())
    assert time.monotonic() - start < 2.0
    bad = [t for t in out["tenants"] if not t["ok"]]
    assert [t["slug"] for t in bad] == ["t3"]
    assert bad[0]["blocked"][0]["check"] == "inspection"
    assert out["ok"] is False


def test_worker_rule_from_shared_rules_matches_old_behaviour():
    rules = [{"matchers": [{"value": "a@x"}], "enabled": True, "actions": [{"type": "worker"}]},
             {"matchers": [{"value": "b@x"}], "enabled": False, "actions": [{"type": "worker"}]}]
    f = inbound_readiness._worker_rule_from
    assert f(rules, "a@x") == "enabled"
    assert f(rules, "b@x") == "missing"
    assert f(rules, "c@x") == "missing"
    assert f(None, "a@x") == "unknown"
