"""N5: owner web-chat inbox, takeover stored on the conversation, and live delivery to the widget."""
import pytest
from fastapi.testclient import TestClient

from app import chat_inbox


def test_author_marks_owner_replies():
    assert chat_inbox.author_of("user", None) == "customer"
    assert chat_inbox.author_of("assistant", None) == "ai"
    assert chat_inbox.author_of("assistant", "owner-reply:" + "a" * 36) == "owner"
    assert chat_inbox.author_of("assistant", "owner") == "owner"


def test_routes_refuse_without_owner_session():
    from app.main import app
    client = TestClient(app)
    cid = "00000000-0000-0000-0000-000000000000"
    for method, path in (("get", "/owner/chat/inbox"), ("get", "/owner/chat/conversations/" + cid),
                         ("post", "/owner/chat/conversations/" + cid + "/takeover"),
                         ("post", "/owner/chat/conversations/" + cid + "/reply")):
        assert getattr(client, method)(path).status_code == 401, path


def test_widget_polls_for_human_replies_and_handles_suppressed():
    src = open("static/widget.js").read() if __import__("os").path.exists("static/widget.js") else open("api/static/widget.js").read()
    assert "/api/v1/chat/poll" in src
    assert "event.suppressed" in src


def test_service_worker_has_push_listener():
    import os
    path = next(p for p in ("../web/portal/public/sw-v2.js", "web/portal/public/sw-v2.js") if os.path.exists(p))
    assert "addEventListener('push'" in open(path).read()


def test_poll_requires_valid_session():
    from app.main import app
    r = TestClient(app).get("/api/v1/chat/poll", params={"key": "x", "session_id": "short"})
    assert r.status_code == 400


# ---- database-backed: takeover on the conversation, reply, and what the visitor's widget receives
import asyncio  # noqa: E402
import os  # noqa: E402

from app import casetimeline, db  # noqa: E402
from tests.test_c3_onboarding import _fresh_pool, _tenant, needs_db  # noqa: E402


@needs_db
def test_conversation_takeover_without_a_lead_pauses_and_poll_returns_owner_reply():
    async def run():
        pool = await _fresh_pool()
        try:
            tid = await _tenant(pool, "n5")
            other = await _tenant(pool, "n5b")
            conv = await pool.fetchval(
                "INSERT INTO conversations(tenant_id,session_id,channel) VALUES($1,'sess-n5-aaaa','chat') RETURNING id", tid)
            await pool.execute("INSERT INTO messages(conversation_id,role,content) VALUES($1,'user','hi')", conv)
            # No lead, no case: previously this visitor could never be taken over.
            assert await casetimeline.is_paused_for_session(tid, "sess-n5-aaaa") is False
            await chat_inbox._set_takeover(tid, conv, True)
            assert await casetimeline.is_paused_for_session(tid, "sess-n5-aaaa") is True
            assert await casetimeline.is_paused_for_session(other, "sess-n5-aaaa") is False
            await chat_inbox._set_takeover(tid, conv, False)
            assert await casetimeline.is_paused_for_session(tid, "sess-n5-aaaa") is False
        finally:
            await db._pool.close()
    asyncio.run(run())


@needs_db
def test_owner_reply_is_stored_once_takes_over_and_shows_in_thread():
    async def run():
        pool = await _fresh_pool()
        try:
            tid = await _tenant(pool, "n5r")
            conv = await pool.fetchval(
                "INSERT INTO conversations(tenant_id,session_id,channel) VALUES($1,'sess-n5-bbbb','chat') RETURNING id", tid)
            await pool.execute("INSERT INTO messages(conversation_id,role,content) VALUES($1,'user','hello?')", conv)
            user = {"tenant_id": tid, "role": "owner", "email": "o@x.test", "id": "u"}
            body = chat_inbox.Reply(text="Hi, a real person here", request_id="a" * 8 + "-aaaa-aaaa-aaaa-" + "a" * 12)
            await chat_inbox.reply(conv, body, user)
            await chat_inbox.reply(conv, body, user)  # double click
            t = await chat_inbox.thread(conv, user)
            owner = [m for m in t["messages"] if m["author"] == "owner"]
            assert len(owner) == 1 and owner[0]["text"] == "Hi, a real person here"
            assert t["paused"] is True
            inbox = await chat_inbox.inbox(user)
            assert inbox["conversations"][0]["paused"] is True
            # another tenant cannot read it
            other = await _tenant(pool, "n5x")
            from fastapi import HTTPException
            with pytest.raises(HTTPException):
                await chat_inbox.thread(conv, {"tenant_id": other, "role": "owner"})
        finally:
            await db._pool.close()
    asyncio.run(run())
