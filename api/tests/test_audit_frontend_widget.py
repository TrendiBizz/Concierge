"""Behavioral regression tests for Audit PR 4: chat/poll rate limit, viewer RBAC, owner.html & widget.js."""
import asyncio
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import chat_inbox, main as app_main
from app.routers import crm, owner_portal


def _fake_request(ip: str = "203.0.113.10") -> Request:
    scope = {"type": "http", "method": "GET", "path": "/api/v1/chat/poll", "headers": [], "client": (ip, 12345)}
    return Request(scope)


def test_chat_poll_uses_dedicated_rate_limiter_not_chat_session_limiter(monkeypatch):
    """Polling /api/v1/chat/poll must not burn the 24h LLM chat session_limiter or ip_limiter."""
    class Pool:
        async def fetch(self, sql, *args):
            return []

        async def fetchval(self, sql, *args):
            return False

    monkeypatch.setattr(chat_inbox.db, "pool", lambda: Pool())
    monkeypatch.setattr(app_main, "_tenant_for", AsyncMock(return_value={"id": uuid.uuid4(), "slug": "demo"}))

    sid = "sess-" + uuid.uuid4().hex[:12]
    ip = "198.51.100.77"
    before_session = len(app_main.session_limiter._hits.get(sid, []))
    before_ip = len(app_main.ip_limiter._hits.get(ip, []))

    for _ in range(15):
        res = asyncio.run(chat_inbox.poll(_fake_request(ip), "pk_test", sid, 0))
        assert res == {"messages": [], "human": False}

    # Neither chat session_limiter nor chat ip_limiter was touched
    assert len(app_main.session_limiter._hits.get(sid, [])) == before_session
    assert len(app_main.ip_limiter._hits.get(ip, [])) == before_ip
    # Dedicated poll limiters were used
    assert len(app_main.poll_session_limiter._hits.get(sid, [])) == 15


def test_viewer_cannot_takeover_contact_lead_or_request_install():
    """viewer role receives 403 on contact takeover, lead takeover, and install request."""
    viewer = {"id": uuid.uuid4(), "tenant_id": uuid.uuid4(), "role": "viewer", "email": "v@example.com"}

    with pytest.raises(HTTPException) as exc1:
        asyncio.run(crm.owner_contact_takeover("phone:+6421000000", crm.ContactTakeover(paused=True, reason="test"), viewer))
    assert exc1.value.status_code == 403

    with pytest.raises(HTTPException) as exc2:
        asyncio.run(crm.owner_lead_takeover(str(uuid.uuid4()), crm.CaseTakeoverRequest(paused=True), viewer))
    assert exc2.value.status_code == 403

    with pytest.raises(HTTPException) as exc3:
        asyncio.run(owner_portal.owner_install_request(owner_portal.InstallRequest(website="https://example.com"), viewer))
    assert exc3.value.status_code == 403


def test_owner_html_defines_defang_and_team_row_class():
    root = Path(__file__).resolve().parents[1]
    html = (root / "static" / "owner.html").read_text(encoding="utf-8")
    assert "function defang(" in html
    assert 'node("div","","team-row")' in html
    assert 'node("div","team-row")' not in html


def test_widget_js_persists_last_owner_id_and_backs_off_on_429():
    root = Path(__file__).resolve().parents[1]
    js = (root / "static" / "widget.js").read_text(encoding="utf-8")
    assert "cc_last_owner_" in js
    assert "res.status === 429" in js
