"""Robot mail must never become a lead, an alert or an auto-reply.

15 Nov 2026, 10:05 NZDT: Stripe's "Reach more customers with your payment link" (from
notifications@stripe.com) became an "Email enquiry for Trendi Concierge" lead, a follow-up task and
an owner alert by email and text.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import automated_mail, cloudflare_inbound, inbound_email

STRIPE_RAW = (
    b"From: Stripe <notifications@stripe.com>\r\n"
    b"To: admin@trendibizz.com\r\n"
    b"Subject: Reach more customers with your payment link\r\n"
    b"List-Unsubscribe: <https://stripe.com/unsubscribe?x=1>\r\n"
    b"\r\nAdd a buy button to your site.\r\n")
PERSON_RAW = (
    b"From: Marcus Whitcombe <marcus@harbourjoinery.example.nz>\r\n"
    b"To: admin@trendibizz.com\r\nSubject: Quote for kitchen joinery\r\n\r\nHi, quote please.\r\n")


def test_stripe_marketing_email_is_automated_for_every_reason():
    assert automated_mail.classify("notifications@stripe.com", "Reach more customers", STRIPE_RAW)
    # Without the raw message (an older Worker) the address alone is enough.
    assert automated_mail.classify("notifications@stripe.com") == "localpart:notifications"
    assert automated_mail.classify("billing@stripe.com") == "domain:stripe.com"
    assert automated_mail.classify(
        "someone@example.test",
        envelope_from="010101a1-0000@bounce.stripe.com") == "domain:stripe.com"


def test_a_normal_enquiry_is_not_automated():
    assert automated_mail.classify(
        "marcus@harbourjoinery.example.nz", "Quote for kitchen joinery", PERSON_RAW,
        envelope_from="marcus@harbourjoinery.example.nz") is None
    # Lookalikes and consumer mail are people.
    for sender in ("jo@gmail.com", "alerton@plumbing.example.nz", "bouncer@club.example",
                   "sam@notstripe.com", "anna@googlemail.com", "kim@stripe.com.evil.example"):
        assert automated_mail.classify(sender, "Booking") is None, sender


@pytest.mark.parametrize("header", [
    "Auto-Submitted: auto-generated", "Precedence: bulk", "Precedence: list", "Precedence: junk",
    "List-Unsubscribe: <mailto:u@x.test>", "List-Id: <news.x.test>",
])
def test_header_markers(header):
    raw = ("From: a@example.test\r\n" + header + "\r\nSubject: hi\r\n\r\nbody").encode()
    assert automated_mail.header_reason(raw)
    assert cloudflare_inbound.has_automated_headers(raw)


def test_auto_submitted_no_is_a_person():
    raw = b"From: a@example.test\r\nAuto-Submitted: no\r\n\r\nbody"
    assert automated_mail.header_reason(raw) is None


@pytest.mark.parametrize("sender", [
    "no-reply@shop.test", "noreply@shop.test", "notifications@github.com", "alerts@bank.test",
    "MAILER-DAEMON@mx.test", "postmaster@mx.test", "bounce@list.test", "notifications+x@acme.test",
    "x@accounts.google.com", "y@cloudflare.com", "z@brevo.com",
])
def test_robot_senders(sender):
    assert automated_mail.classify(sender, "Hello")


def _wire(monkeypatch):
    calls = SimpleNamespace(capture=AsyncMock(), audit=AsyncMock(), execute=AsyncMock(),
                            convo=AsyncMock(return_value="c1"))
    async def create(tenant_id, sender, subject, body, reply, key, **kw):
        return {"id": 7, "sender": sender, "status": kw.get("status", "draft")}
    monkeypatch.setattr(inbound_email.email_drafts, "create", create)
    monkeypatch.setattr(inbound_email.enquiries, "capture", calls.capture)
    monkeypatch.setattr(inbound_email.inbound_policy, "audit", calls.audit)
    monkeypatch.setattr(inbound_email.convo, "get_or_create", calls.convo)
    monkeypatch.setattr(inbound_email.tenants, "get_by_id",
                        AsyncMock(return_value={"id": 1, "name": "Trendi Concierge",
                                                "inbound_ack": True, "email_auto_reply": True}))
    monkeypatch.setattr(inbound_email.db, "pool",
                        lambda: SimpleNamespace(execute=calls.execute, fetchval=AsyncMock(return_value=None)))
    return calls


def _ingest(sender, subject, body, flags=None, envelope_from=None):
    return asyncio.run(inbound_email.ingest_verified(
        1, "cloudflare", "msg-1@x.test", sender, "admin@trendibizz.com", subject, body,
        auth={"aligned": "yes", "dmarc": "pass"}, risk="low", flags=flags or [],
        envelope_from=envelope_from))


def test_stripe_email_makes_no_lead_no_alert_no_reply(monkeypatch):
    calls = _wire(monkeypatch)
    draft = _ingest("notifications@stripe.com", "Reach more customers with your payment link",
                    "Add a buy button to your site.",
                    envelope_from="010101a1@bounce.stripe.com")
    assert draft["status"] == "discarded"
    calls.capture.assert_not_awaited()          # no lead, no owner alert
    calls.execute.assert_not_awaited()          # no acknowledgement, no secretary job
    action = calls.audit.await_args.args[2]
    assert action == "received_automated"


def test_header_flag_from_the_worker_also_stops_the_lead(monkeypatch):
    calls = _wire(monkeypatch)
    _ingest("news@shop.example", "Weekly deals", "Deals inside", flags=["automated_sender"])
    calls.capture.assert_not_awaited()


def test_a_normal_enquiry_still_becomes_a_lead(monkeypatch):
    calls = _wire(monkeypatch)
    monkeypatch.setattr(inbound_email, "queue_ack", AsyncMock(return_value="queued"))
    draft = _ingest("marcus@harbourjoinery.example.nz", "Quote for kitchen joinery",
                    "Hi, quote please.\n\nKind regards,\nMarcus Whitcombe\nHarbour Joinery")
    assert draft["status"] == "draft"
    calls.capture.assert_awaited_once()
    assert calls.audit.await_args.args[2] == "received"


def test_an_ahrefs_crawl_report_is_automated_even_without_list_headers():
    """15 Nov 13:14: "Page has links to redirect [New]: 39 URLs" from sa@ahrefs.com became an
    enquiry and an owner alert. It carries no List-Id, so the header checks never fired."""
    from app.automated_mail import classify
    # the local part catches it first ("sa"), the domain is the backstop: either way it is a robot
    reason = classify("sa@ahrefs.com", "Page has links to redirect [New]: 39 URLs")
    assert reason in ("localpart:sa", "domain:ahrefs.com"), reason
    assert classify("reports@semrush.com", "Site audit ready") is not None
    assert classify("someone@ahrefs.com", "Question about pricing") == "domain:ahrefs.com"  # domain alone


def test_a_person_called_sam_is_still_a_person():
    from app.automated_mail import classify
    assert classify("sam@smallbuilders.co.nz", "Can you quote a fence?") is None
    assert classify("sarah@ahrefsclient.co.nz", "Quote please") is None


def test_list_unsubscribe_alone_marks_bulk_mail():
    from app.automated_mail import classify
    raw = (b"From: Team <hello@some-saas.example>\r\n"
           b"Subject: Your monthly summary\r\n"
           b"List-Unsubscribe: <https://some-saas.example/u>\r\n\r\nBody\r\n")
    assert classify("hello@some-saas.example", "Your monthly summary", raw=raw).startswith("header:")
