"""Integration and C4 regression tests from the roadmap combine pass."""

from __future__ import annotations

import asyncio
import datetime
import inspect
from pathlib import Path

from app import device_sms, platform_billing

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_caddyfile_routes_chat_poll_and_n6_public_api():
    caddyfile = (REPO_ROOT / "scripts/vps/Caddyfile").read_text(encoding="utf-8")
    assert "/api/v1/chat/poll" in caddyfile, "N5 widget polling route must be exposed on chat host"
    for route in (
        "/api/v1/contacts",
        "/api/v1/enquiries",
        "/api/v1/appointments",
        "/api/v1/events",
        "/integrations/*/callback",
    ):
        assert route in caddyfile, f"N6 public route {route} missing from Caddyfile"


def test_reload_gateway_script_reloads_gracefully_and_restarts_only_when_admin_is_off():
    """2026-11-24: the Caddyfile now enables a loopback-only admin API, so a Caddyfile change goes live with a
    graceful `caddy reload` (no restart). The restart is kept ONLY as the one-time fallback for a gateway that was
    started while the config still said `admin off` (a reload cannot work there), and `caddy reload` must never be
    attempted without first probing that the admin API answers."""
    script = (REPO_ROOT / "scripts/vps/reload-gateway.sh").read_text(encoding="utf-8")
    assert "caddy validate --config /tmp/Caddyfile.new" in script
    probe = script.index("localhost:2019/config/")
    reload_at = script.index("caddy reload --config")
    restart_at = script.index('podman restart \\"')
    assert script.index("caddy validate --config") < probe < reload_at < restart_at
    assert "else" in script[reload_at:restart_at], "the restart sits in the admin-off branch only"
    caddyfile = (REPO_ROOT / "scripts/vps/Caddyfile").read_text(encoding="utf-8")
    assert "admin localhost:2019" in caddyfile and "admin off" not in caddyfile.split(":8080 {")[0]


def test_healthcheck_sms_inbound_counts_existing_inbound_table():
    hc = (REPO_ROOT / "scripts/vps/healthcheck.py").read_text(encoding="utf-8")
    assert "device_sms_inbound" in hc
    assert "NOT EXISTS (SELECT 1 FROM device_sms_inbound" in hc


def test_device_sms_inbound_stamps_verified_before_reply():
    src = inspect.getsource(device_sms.inbound)
    stamp_pos = src.index("inbound_verified_at=now()")
    reply_pos = src.index("_sms_reply")
    assert stamp_pos < reply_pos, "inbound_verified_at must be recorded before AI reply generation"


def test_c4_invoice_uses_legal_entity_and_zero_rates_usd_exports():
    usd_html = platform_billing.invoice_html({
        "number": "TRB-0099",
        "customer_email": "buyer@us-biz.example",
        "customer_name": "Buyer",
        "business_name": "US Co",
        "currency": "USD",
        "amount_cents": 19_900,
        "gst_cents": 0,
        "description": "Concierge — monthly",
        "issued_on": datetime.date(2026, 11, 21),
        "paid_at": datetime.datetime(2026, 11, 21, 9, 0),
    })
    assert "TRENDI LIMITED" in usd_html
    assert "Trendi Bizz Limited" not in usd_html
    assert "GST (0% — zero-rated export)" in usd_html
    assert "199.00 USD" in usd_html


def test_c4_issue_applies_gst_only_for_nzd(monkeypatch):
    captured = {}

    class FakePool:
        async def fetchval(self, sql, *args):
            return 42

        async def fetchrow(self, sql, *args):
            if "INSERT INTO platform_invoices" in sql:
                captured["gst_cents"] = args[6]
                captured["currency"] = args[7]
                return {"number": args[0], "gst_cents": args[6], "currency": args[7]}
            return None

    monkeypatch.setattr(platform_billing.db, "pool", lambda: FakePool())

    async def _run():
        await platform_billing.issue(
            email="us@example.com", name="US", business="US Co",
            plan="monthly", amount_cents=25_000, currency="USD",
        )
        assert captured == {"gst_cents": 0, "currency": "USD"}

        await platform_billing.issue(
            email="nz@example.co.nz", name="NZ", business="NZ Co",
            plan="monthly", amount_cents=115_000, currency="NZD",
        )
        assert captured == {"gst_cents": 15_000, "currency": "NZD"}

    asyncio.run(_run())


def test_c4_website_claims_aligned_and_draft_marked():
    draft = (REPO_ROOT / "docs/legal/CONCIERGE_TOS_DPA_DRAFT.md").read_text(encoding="utf-8")
    assert "DRAFT - NEEDS LEGAL REVIEW" in draft

    privacy = (REPO_ROOT / "website/privacy.html").read_text(encoding="utf-8")
    assert "DigitalOcean" in privacy and "30 days" in privacy

    pricing = (REPO_ROOT / "website/pricing.html").read_text(encoding="utf-8")
    assert "Manage Concierge billing in Studio" in pricing

    for page in ("website/index.html", "website/concierge.html"):
        text = (REPO_ROOT / page).read_text(encoding="utf-8")
        assert "email is live" not in text
