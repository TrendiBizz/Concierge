"""The website's enquiry forms capture the enquiry instead of opening a mail draft.

/contact and /concierge-start used to build a mailto: link and say "nothing has been sent", so a
visitor with no mail app configured lost their enquiry silently (site audit 2026-11-16). These
checks pin the server side (stored first, emailed second, spam refused) and the page side (the forms
post, keep the email draft as the fallback, and carry a honeypot).
"""

import asyncio
import pathlib

import pytest

from app import flood_guard, main, site_enquiry

ROOT = pathlib.Path(__file__).resolve().parents[2]
SITE = ROOT / "website"


class FakePool:
    def __init__(self, tenant=True):
        self.inserts = []
        self.tenant = tenant

    async def fetchrow(self, sql, *args):
        if sql.startswith("INSERT INTO site_enquiries"):
            self.inserts.append(args)
            return {"id": "11111111-1111-1111-1111-111111111111"}
        if "FROM tenants" in sql:
            return {"id": "t-1", "to_addr": "admin@trendibizz.com"} if self.tenant else None
        raise AssertionError(sql)


@pytest.fixture
def fake(monkeypatch):
    pool = FakePool()
    sent = []

    async def enqueue(*args, **kwargs):
        sent.append((args, kwargs))

    monkeypatch.setattr(site_enquiry.db, "pool", lambda: pool)
    monkeypatch.setattr(site_enquiry.outbox, "enqueue", enqueue)
    monkeypatch.setattr(flood_guard, "_windows", flood_guard._windows.__class__(flood_guard._windows.default_factory))
    pool.sent = sent
    return pool


def run(coro):
    return asyncio.run(coro)


def good(**over):
    base = dict(kind="seo", email="Visitor@Example.com", name="Vee", website="example.com",
                message="best plumber in Nelson", ip="203.0.113.9", user_agent="pytest")
    base.update(over)
    return base


def test_an_enquiry_is_stored_and_the_operator_is_emailed(fake):
    result = run(site_enquiry.submit(**good()))
    assert result["ok"] and result["id"]
    row = fake.inserts[0]
    assert row[0] == "seo" and row[2] == "visitor@example.com"
    assert row[3] == "https://example.com", "a bare domain must be stored as an https address"
    (args, kwargs), = fake.sent
    assert args[1:4] == ("owner_alert", "email", "admin@trendibizz.com")
    assert "visitor@example.com" in args[4] and "best plumber" in args[4]
    assert kwargs["dedupe_key"].startswith("site-enquiry:")


def test_the_enquiry_survives_a_mail_failure(fake, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("smtp down")
    monkeypatch.setattr(site_enquiry.outbox, "enqueue", boom)
    assert run(site_enquiry.submit(**good()))["ok"], "a mail fault must not lose or fail the enquiry"
    assert len(fake.inserts) == 1


def test_a_missing_alert_tenant_does_not_lose_the_enquiry(fake):
    fake.tenant = False
    assert run(site_enquiry.submit(**good(ip="198.51.100.7")))["ok"]
    assert len(fake.inserts) == 1 and fake.sent == []


def test_the_honeypot_stores_nothing(fake):
    assert run(site_enquiry.submit(**good(trap="http://spam.example")))["id"] is None
    assert fake.inserts == [] and fake.sent == []


@pytest.mark.parametrize("email", ["", "not-an-address", "a@b", "x" * 400 + "@example.com"])
def test_an_unusable_address_is_refused(fake, email):
    with pytest.raises(site_enquiry.Refused):
        run(site_enquiry.submit(**good(email=email)))
    assert fake.inserts == []


def test_a_nonsense_website_is_refused(fake):
    with pytest.raises(site_enquiry.Refused):
        run(site_enquiry.submit(**good(website="not a url")))


def test_security_review_kind_is_accepted(fake):
    out = run(site_enquiry.submit(**good(kind="security")))
    assert out["ok"] and fake.inserts[-1][0] == "security"


def test_unknown_kinds_are_refused(fake):
    with pytest.raises(site_enquiry.Refused):
        run(site_enquiry.submit(**good(kind="admin")))


def test_one_address_cannot_flood_the_form(fake):
    for _ in range(site_enquiry.PER_IP_PER_HOUR):
        run(site_enquiry.submit(**good(ip="192.0.2.50")))
    with pytest.raises(site_enquiry.Refused) as refused:
        run(site_enquiry.submit(**good(ip="192.0.2.50")))
    assert refused.value.status == 429
    run(site_enquiry.submit(**good(ip="192.0.2.51")))  # someone else is unaffected


def test_control_characters_and_overlong_text_are_trimmed(fake):
    run(site_enquiry.submit(**good(name="Vee\x00\r\nBcc: x@y.z", message="a" * 9000)))
    row = fake.inserts[0]
    assert "\x00" not in row[1] and "\n" not in row[1], "a name must never carry a header break"
    assert len(row[4]) == 4000


def test_the_route_turns_a_refusal_into_the_right_status(monkeypatch):
    class Req:
        headers = {"x-forwarded-for": "203.0.113.5, 10.0.0.1", "user-agent": "t"}
        client = None

    async def refuse(**kwargs):
        assert kwargs["ip"] == "203.0.113.5", "the visitor's address is the first forwarded one"
        raise site_enquiry.Refused("Too many", 429)

    monkeypatch.setattr(main.site_enquiry, "submit", refuse)
    body = main.SiteEnquiry(kind="seo", email="a@example.com")
    with pytest.raises(main.HTTPException) as err:
        run(main.website_enquiry(body, Req()))
    assert err.value.status_code == 429


# ----------------------------------------------------------------------------------- the pages

def test_the_forms_post_to_the_endpoint_and_keep_the_draft_as_fallback():
    for name in ("main.js", "concierge-start.js"):
        js = (SITE / name).read_text(encoding="utf-8")
        assert 'fetch("/api/enquiry"' in js, f"{name} no longer posts the enquiry"
        assert "wireFallbacks(draft)" in js or "showDraft(" in js, f"{name} lost the mail fallback"
        assert "trap" in js
    # the connect-src CSP allows same-origin posts only, which is what this is
    assert "connect-src 'self'" in (SITE / "_headers").read_text()


def test_the_forms_collect_an_email_and_carry_the_honeypot():
    for name in ("contact.html", "seo.html", "concierge-start.html"):
        html = (SITE / name).read_text(encoding="utf-8")
        assert 'name="email"' in html, f"{name} has nothing to reply to"
        assert 'name="trap"' in html and 'tabindex="-1"' in html, f"{name} has no honeypot"
        assert "Open email draft" not in html or name == "concierge-start.html"
    assert ".trap" in (SITE / "layout.css").read_text()


def test_the_gateway_routes_the_post_to_the_api_before_the_static_site():
    caddy = (ROOT / "scripts" / "vps" / "Caddyfile").read_text()
    assert "path /api/enquiry" in caddy
    assert caddy.index("handle @enquiry") < caddy.index("handle @website")


def test_a_schema_error_list_is_never_shown_as_text():
    """FastAPI answers 422 with detail as a LIST; showing it raw printed "[object Object]" to the visitor."""
    start = (SITE / "concierge-start.js").read_text(encoding="utf-8")
    assert 'typeof res.data.detail === "string"' in start
    main_js = (SITE / "main.js").read_text(encoding="utf-8")
    assert 'typeof res.data.detail === "string"' in main_js
    assert "(res.data && res.data.detail) ||" not in main_js + start


# --- Owner-alert emails must never show internal bookkeeping (dedupe keys, row ids) -------------
# 2026-11-26: the explainer video once showed a "Dedupe key" line; this pins the real email.
_INTERNAL = ("dedupe", "site-enquiry:", "enq:", "issue:", "outbox")
_ALLOWED_PREFIXES = ("A website enquiry came in", "Name:", "Email:", "Website:", "Plan:", "Wants:",
                     "Referral code:", "Reply to ", "best plumber", "(no message)")


def test_the_operator_email_shows_no_internal_ids_or_stray_lines(fake):
    result = run(site_enquiry.submit(**good()))
    (args, kwargs), = fake.sent
    body, subject = args[4], kwargs["subject"]
    assert kwargs["dedupe_key"].startswith("site-enquiry:")
    for text in (body, subject):
        low = text.lower()
        assert not any(w in low for w in _INTERNAL), text
        assert kwargs["dedupe_key"] not in text
        assert str(result["id"]) not in text.replace("203.0.113.9", ""), "no row id in the email"
    stray = [ln for ln in body.splitlines() if ln.strip() and not ln.startswith(_ALLOWED_PREFIXES)]
    assert stray == [], f"unexpected lines in the operator email: {stray}"


def test_the_enquiry_alert_to_an_owner_shows_no_dedupe_key():
    from app import enquiry_alerts
    tenant = {"id": "t-1", "name": "Acme Plumbing", "timezone": "Pacific/Auckland"}
    contact = {"name": "Vee", "email": "v@example.com", "phone": "+6421000000"}
    for channel in ("email", "sms", "voice", "chat", "whatsapp"):
        body = enquiry_alerts.render(tenant, channel, contact, "need a plumber")
        subject = enquiry_alerts.subject_for(tenant, channel, "Vee", "need a plumber")
        for text in (body, subject):
            assert not any(w in text.lower() for w in _INTERNAL), (channel, text)
            assert "t-1:" not in text, (channel, text)
