"""Acknowledgement of inbound email: opt-in, verified senders only, never to robots, once a day."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import inbound_email

ON = {"id": 1, "name": "Trendi", "inbound_ack": True}
GOOD = {"aligned": "yes", "dkim": "pass", "dmarc": "pass"}


def _decide(**kw):
    args = dict(tenant=ON, sender="Jo <jo@example.test>", subject="Help", risk="low", flags=[], auth=GOOD)
    args.update(kw)
    return inbound_email.ack_decision(**args)


def test_off_by_default():
    assert _decide(tenant={"id": 1}) == "off"
    assert _decide(tenant={"id": 1, "inbound_ack": False}) == "off"


def test_a_verified_ordinary_sender_is_acknowledged():
    assert _decide() is None


def test_unverified_senders_are_never_acknowledged_so_no_backscatter():
    assert _decide(auth={}) == "sender_not_verified"
    assert _decide(auth=None) == "sender_not_verified"
    assert _decide(auth={"aligned": "no", "dkim": "pass", "dmarc": "none"}) == "sender_not_verified"
    assert _decide(auth={"dmarc": "fail"}) == "sender_not_verified"


def test_dmarc_pass_alone_is_enough():
    assert _decide(auth={"dmarc": "pass"}) is None


def test_robots_lists_and_risky_mail_get_nothing():
    assert _decide(risk="high") == "high_risk"
    assert _decide(flags=["automated_sender"]) == "automated_headers"
    assert _decide(sender="noreply@shop.test") == "automated_address"
    assert _decide(sender="Mail Delivery <MAILER-DAEMON@x.test>") == "automated_address"
    assert _decide(subject="Automatic reply: holiday") == "automated_address"
    assert _decide(sender="nobody") == "no_address"


def test_message_has_a_reference_and_the_published_promise():
    subject, body = inbound_email.ack_message(ON, 42, "Help")
    assert "T-42" in subject and "T-42" in body
    assert "one business day" in body and "Trendi" in body
    assert "no need to reply" in body


def test_custom_text_replaces_the_default_paragraph():
    _, body = inbound_email.ack_message({**ON, "inbound_ack_text": "We are on it."}, 7, "x")
    assert "We are on it." in body and "one business day" not in body and "T-7" in body


def _pool(recent=None):
    return SimpleNamespace(fetchval=AsyncMock(return_value=recent), execute=AsyncMock())


def test_it_is_queued_once_and_not_again_within_a_day(monkeypatch):
    pool = _pool(recent=None)
    monkeypatch.setattr(inbound_email.db, "pool", lambda: pool)
    draft = {"id": 5, "sender": "jo@example.test"}
    assert asyncio.run(inbound_email.queue_ack(ON, draft, "Help", "k1")) == "queued"
    sql, *args = pool.execute.call_args.args
    assert "'inbound_ack'" in sql and "ON CONFLICT(dedupe_key)" in sql and args[-1] == "ack:k1"
    pool = _pool(recent=1)
    monkeypatch.setattr(inbound_email.db, "pool", lambda: pool)
    assert asyncio.run(inbound_email.queue_ack(ON, draft, "Help", "k2")) == "already_acknowledged"
    pool.execute.assert_not_called()


def test_a_database_error_never_breaks_ingestion(monkeypatch):
    pool = SimpleNamespace(fetchval=AsyncMock(side_effect=RuntimeError("down")), execute=AsyncMock())
    monkeypatch.setattr(inbound_email.db, "pool", lambda: pool)
    assert asyncio.run(inbound_email.queue_ack(ON, {"id": 1, "sender": "a@b.test"}, "x", "k")) == "error"
