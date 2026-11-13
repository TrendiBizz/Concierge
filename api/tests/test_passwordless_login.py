"""Signing in must be one click, with no password to invent.

The customer's first contact was a form demanding a 12-character password typed twice, and the
sign-in page asked for a "Business ID" they had never been shown. These tests pin the replacement:
the invite link signs you in by itself, a returning customer asks for a fresh link, and no
password can ever match an account that was opened by link.
"""
import asyncio

import pytest

from app import main, owner_auth

INVITATION = {
    "id": "inv-1", "tenant_id": "t1", "email": "conrad@pukekoconstruction.co.nz",
    "role": "owner", "purpose": "invite", "tenant_slug": "pukeko-construction",
    "used_at": None, "expires_at": None,
}


class _Conn:
    def __init__(self, invitation=INVITATION, existing=None):
        self.invitation = invitation
        self.existing = existing
        self.writes = []

    async def fetchrow(self, sql, *args):
        if "FROM tenant_invites" in sql:
            return self.invitation
        if "FROM tenant_users" in sql:
            return self.existing
        return None

    async def fetchval(self, sql, *args):
        self.writes.append((sql, args))
        return "user-1"

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"

    def transaction(self):
        return _Ctx(self)


class _Ctx:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Ctx(self.conn)


def _with_pool(monkeypatch, conn):
    monkeypatch.setattr(owner_auth.db, "pool", lambda: _Pool(conn))


# -- the link signs you in -------------------------------------------------


def test_one_link_opens_the_account_without_any_password(monkeypatch):
    conn = _Conn()
    _with_pool(monkeypatch, conn)

    result = asyncio.run(owner_auth.accept_invite("tok_" + "x" * 40))

    assert result["slug"] == "pukeko-construction"
    assert result["email"] == "conrad@pukekoconstruction.co.nz"
    assert result["role"] == "owner"
    assert len(result["access_token"]) > 20
    assert result["expires_in"] == owner_auth.SESSION_DAYS * 86400
    sql, args = next((s, a) for s, a in conn.writes if "INSERT INTO tenant_users" in s)
    assert args[-1] == owner_auth.NO_PASSWORD, "an account opened by link must have no usable password"
    assert any("INSERT INTO tenant_sessions" in s for s, _ in conn.writes)


def test_the_link_is_spent_once_it_is_used(monkeypatch):
    conn = _Conn()
    _with_pool(monkeypatch, conn)
    asyncio.run(owner_auth.accept_invite("tok_" + "x" * 40))
    assert any("UPDATE tenant_invites SET used_at" in s for s, _ in conn.writes)


def test_an_unknown_or_expired_link_is_a_readable_refusal(monkeypatch):
    _with_pool(monkeypatch, _Conn(invitation=None))
    with pytest.raises(ValueError):
        asyncio.run(owner_auth.accept_invite("tok_" + "x" * 40))


def test_a_recovery_link_is_refused_when_the_account_is_gone(monkeypatch):
    _with_pool(monkeypatch, _Conn(invitation={**INVITATION, "purpose": "recovery"}, existing=None))
    with pytest.raises(ValueError):
        asyncio.run(owner_auth.accept_invite("tok_" + "x" * 40))


def test_no_password_can_ever_match_a_link_opened_account():
    # The column is NOT NULL, so a marker is stored; verify_password must reject everything.
    for attempt in ("", "no-password", "x" * 12, "correct horse battery"):
        assert owner_auth.verify_password(attempt, owner_auth.NO_PASSWORD) is False


# -- asking for a fresh link -----------------------------------------------


def test_asking_for_a_link_never_reveals_whether_the_account_exists(monkeypatch):
    async def no_accounts(email):
        return []

    sent = []

    async def send(*a, **k):
        sent.append(a)

    monkeypatch.setattr(main.owner_auth, "account_emails", no_accounts)
    monkeypatch.setattr(main.mailer, "send_email", send)
    async def allow(ip, slug, email):
        return True

    monkeypatch.setattr(main.owner_auth, "allow_login_attempt", allow)


    result = asyncio.run(main.owner_email_link(main.OwnerEmailLink(email="nobody@example.com"), _Request()))
    assert result == {"ok": True}
    assert sent == []


def test_a_known_address_gets_a_one_click_link_by_email(monkeypatch):
    accounts = [{"tenant_id": "t1", "email": "conrad@pukekoconstruction.co.nz",
                 "role": "owner", "slug": "pukeko-construction", "name": "Pukeko Construction"}]
    sent = []

    async def allow(ip, slug, email):
        return True

    async def accounts_for(email):
        return accounts

    async def make_invite(tenant_id, email, role, purpose="invite"):
        assert purpose == "recovery"
        return "tok_" + "y" * 40

    async def send(to_addr, subject, body, headers=None, from_name=None):
        sent.append({"to": to_addr, "subject": subject, "body": body})

    monkeypatch.setattr(main.owner_auth, "allow_login_attempt", allow)
    monkeypatch.setattr(main.owner_auth, "account_emails", accounts_for)
    monkeypatch.setattr(main.owner_auth, "make_invite", make_invite)
    monkeypatch.setattr(main.owner_auth, "invitation_link",
                        lambda token: "https://concierge.trendibizz.com/studio#invite=" + token)
    monkeypatch.setattr(main.mailer, "send_email", send)

    asyncio.run(main.owner_email_link(main.OwnerEmailLink(email="Conrad@PukekoConstruction.co.nz"), _Request()))
    assert len(sent) == 1
    assert "#invite=tok_" in sent[0]["body"]
    assert "no password" in sent[0]["body"].lower()


def test_a_spent_link_answers_with_a_plain_sentence(monkeypatch):
    async def refuse(token):
        raise ValueError("Invalid or expired link")

    monkeypatch.setattr(main.owner_auth, "accept_invite", refuse)
    with pytest.raises(Exception) as caught:
        asyncio.run(main.owner_accept_invite(main.OwnerLinkAccept(token="tok_" + "x" * 40)))
    assert "expired" in str(caught.value).lower() or "used" in str(caught.value).lower()


# -- the invitation email says there is nothing to create ------------------


def test_the_invitation_email_no_longer_asks_for_a_password(monkeypatch):
    sent = []

    async def require_tenant(slug):
        return {"id": "t1", "slug": slug, "name": "Pukeko Construction"}

    async def make_invite(tenant_id, email, role, purpose="invite"):
        return "tok_" + "x" * 40

    async def send(to_addr, subject, body, headers=None, from_name=None):
        sent.append(body)

    monkeypatch.setattr(main, "_require_tenant", require_tenant)
    monkeypatch.setattr(main.owner_auth, "make_invite", make_invite)
    monkeypatch.setattr(main.owner_auth, "invitation_link",
                        lambda token: "https://concierge.trendibizz.com/studio#invite=" + token)
    monkeypatch.setattr(main.mailer, "send_email", send)

    asyncio.run(main.admin_invite_owner("pukeko-construction",
                                        main.OwnerInvite(email="conrad@pukekoconstruction.co.nz",
                                                         role="owner", send_email=True)))
    assert "password" in sent[0].lower()
    assert "no password to create" in sent[0]
    assert "choose your password" not in sent[0]


class _Request:
    """Enough of a Starlette Request for the IP used by the throttle."""

    class client:  # noqa: N801 - mirrors Starlette's attribute
        host = "203.0.113.7"
