"""N10: RFC threading, attachment metadata and the per-tenant sending address."""
import asyncio
import smtplib
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import email_threading as et, mailer, outbox
from tests.test_email_reply_to import _patch, _row


def _raw(**extra) -> bytes:
    m = EmailMessage()
    m["From"] = "c@example.com"
    m["To"] = "reply-abc@trendibizz.com"
    m["Subject"] = "Quote"
    m["Message-ID"] = "<a1@example.com>"
    for k, v in extra.items():
        m[k.replace("_", "-")] = v
    m.set_content("see attached")
    m.add_attachment(b"x" * 3000, maintype="application", subtype="pdf", filename="../../plan.pdf")
    m.add_attachment(b"y" * 10, maintype="image", subtype="png", filename="a\x00b.png")
    return m.as_bytes()


def test_parse_headers_and_attachment_metadata():
    p = et.parse(_raw(In_Reply_To="<p@x>", References="<r@x> <p@x>"))
    assert p["message_id"] == "<a1@example.com>" and p["in_reply_to"] == "<p@x>"
    assert p["references"] == ["<r@x>", "<p@x>"]
    assert [a["filename"] for a in p["attachments"]] == ["plan.pdf", "ab.png"]
    assert p["attachments"][0] == {"filename": "plan.pdf", "content_type": "application/pdf", "size": 3000}


def test_parse_garbage_never_raises():
    assert et.parse(None)["attachments"] == [] and et.parse(b"\xff\x00")["message_id"] == ""


def test_thread_key_separates_subjects_and_joins_replies():
    a = et.thread_key("C <c@example.com>", "Quote for deck")
    assert a == et.thread_key("c@example.com", "RE: Re: quote for  deck")
    assert a != et.thread_key("c@example.com", "Different job")
    r = et.thread_key("c@example.com", "anything", "<p@x>", ["<root@x>", "<p@x>"])
    assert r == et.thread_key("c@example.com", "other", "<q@x>", ["<root@x>"]) != a


def test_reply_headers_chain_and_reject_junk():
    h = et.reply_headers("<p@x>", ["<r@x>"])
    assert h == {"In-Reply-To": "<p@x>", "References": "<r@x> <p@x>"}
    assert et.reply_headers("bad header\r\nBcc: x", []) == {} and et.reply_headers("", None) == {}


def test_attachment_notice_lists_files():
    assert "plan.pdf" in et.attachment_notice([{"filename": "plan.pdf", "content_type": "application/pdf", "size": 3000}])
    assert et.attachment_notice([]) == ""


def test_sender_address_needs_verification_and_valid_syntax():
    t = {"send_from_address": "hello@acme.co.nz", "send_from_verified": True}
    assert et.sender_address(t, "d@t.com") == "hello@acme.co.nz"
    assert et.sender_address({**t, "send_from_verified": False}, "d@t.com") == "d@t.com"
    assert et.sender_address({**t, "send_from_address": "a@b.c\r\nBcc:x"}, "d@t.com") == "d@t.com"


def test_outbox_threads_approved_reply_and_uses_verified_from(monkeypatch):
    finish, sent = _patch(monkeypatch, tenant_extra={"send_from_address": "hi@acme.co.nz", "send_from_verified": True})
    pool = SimpleNamespace(
        execute=AsyncMock(return_value="UPDATE 1"), fetchval=AsyncMock(return_value=None),
        fetchrow=AsyncMock(return_value={"message_id_hdr": "<a1@example.com>", "references_hdr": '["<r@x>"]'}))
    monkeypatch.setattr(outbox.db, "pool", lambda: pool)
    captured = {}
    async def capture(to, subject, body, headers=None, from_name=None, html=None, from_addr=None):
        captured.update(headers=headers, from_addr=from_addr)
    monkeypatch.setattr(outbox.mailer, "send_email", capture)
    row = {**_row("approved_reply"), "dedupe_key": "approved-email-draft:5"}
    asyncio.run(outbox._deliver(row))
    assert captured["headers"]["In-Reply-To"] == "<a1@example.com>"
    assert captured["headers"]["References"] == "<r@x> <a1@example.com>"
    assert captured["from_addr"] == "hi@acme.co.nz"


def test_unverified_tenant_keeps_platform_from(monkeypatch):
    finish, sent = _patch(monkeypatch, tenant_extra={"send_from_address": "hi@acme.co.nz"})
    asyncio.run(outbox._deliver(_row("approved_reply")))
    assert "In-Reply-To" not in sent["headers"]  # no stored parent -> no threading headers


def test_mailer_from_header_and_envelope(monkeypatch):
    s = SimpleNamespace(smtp_from="admin@trendibizz.com", smtp_security="none", smtp_host="h", smtp_port=25,
                        smtp_user="", smtp_password="")
    monkeypatch.setattr(mailer, "get_settings", lambda: s)
    seen = {}
    class Fake:
        def __init__(self, *a, **k): pass
        def send_message(self, msg, from_addr=None): seen.update(msg=msg, env=from_addr)
        def quit(self): pass
    monkeypatch.setattr(smtplib, "SMTP", Fake)
    mailer._send_sync("c@example.com", "S", "b", from_name="Acme", from_addr="hi@acme.co.nz")
    assert seen["msg"]["From"] == "Acme <hi@acme.co.nz>" and seen["env"] == "admin@trendibizz.com"
