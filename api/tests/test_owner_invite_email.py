"""Opt-in invitation email and the owner channel-health endpoint."""
import asyncio
import logging

from app import main

TOKEN = "tok_" + "x" * 40
LINK = "https://concierge.trendibizz.com/studio#invite=" + TOKEN


def _setup(monkeypatch, send):
    async def require_tenant(slug):
        return {"id": "t1", "slug": slug, "name": "Pukeko Construction"}

    async def make_invite(tenant_id, email, role, purpose="invite"):
        return TOKEN

    monkeypatch.setattr(main, "_require_tenant", require_tenant)
    monkeypatch.setattr(main.owner_auth, "make_invite", make_invite)
    monkeypatch.setattr(main.owner_auth, "invitation_link", lambda token: "https://concierge.trendibizz.com/studio#invite=" + token)
    monkeypatch.setattr(main.mailer, "send_email", send)


def _invite(**over):
    body = main.OwnerInvite(email="Conrad@PukekoConstruction.co.nz", role="owner", **over)
    return asyncio.run(main.admin_invite_owner("pukeko-construction", body))


def test_invite_is_not_emailed_unless_asked(monkeypatch):
    sent = []

    async def send(*a, **k):
        sent.append(a)

    _setup(monkeypatch, send)
    result = _invite()
    assert sent == []
    assert result["emailed"] is False
    assert result["invitation_url"] == LINK
    assert result["invitation_token"] == TOKEN


def test_invite_email_is_sent_to_the_invitee_when_requested(monkeypatch):
    sent = []

    async def send(to_addr, subject, body, headers=None, from_name=None):
        sent.append({"to": to_addr, "subject": subject, "body": body, "from_name": from_name})

    _setup(monkeypatch, send)
    result = _invite(send_email=True)
    assert result["emailed"] is True and result["email_error"] == ""
    assert len(sent) == 1
    message = sent[0]
    assert message["to"] == "conrad@pukekoconstruction.co.nz"  # cleaned/lower-cased
    assert LINK in message["body"]
    assert "Pukeko Construction" in message["subject"]
    assert "once" in message["body"] and "24 hours" in message["body"]
    assert message["from_name"] == "Trendi Concierge"


def test_failed_send_never_loses_the_invitation_or_leaks_the_token(monkeypatch, caplog):
    async def send(*a, **k):
        raise RuntimeError("smtp down " + TOKEN)  # even if an error message carried the token

    _setup(monkeypatch, send)
    with caplog.at_level(logging.INFO):
        result = _invite(send_email=True)
    assert result["emailed"] is False
    assert result["email_error"] == "RuntimeError"
    assert result["invitation_url"] == LINK  # operator can still hand it over
    assert TOKEN not in caplog.text


def test_channel_health_endpoint_reports_for_the_callers_business(monkeypatch):
    seen = []

    async def report(tenant_id):
        seen.append(tenant_id)
        return {"email": {"ok": True}, "sms": {"ok": False}, "voice": {"ok": False}, "all_ok": False}

    monkeypatch.setattr(main.channel_health, "channel_report", report)
    user = {"tenant_id": "t-pukeko", "slug": "pukeko-construction", "role": "viewer", "email": "x@y.z"}
    result = asyncio.run(main.owner_channel_health(user))
    assert seen == ["t-pukeko"]
    assert result["all_ok"] is False
