"""Delivery status notifications must be parsed, or a dead address is retried forever."""
from app import bounces

DSN_HARD = b"""From: Mail Delivery System <MAILER-DAEMON@example.net>
To: reply-abc@trendibizz.com
Subject: Undelivered Mail Returned to Sender
Message-ID: <dsn-1@example.net>
MIME-Version: 1.0
Content-Type: multipart/report; report-type=delivery-status;
	boundary="BOUNDARY-1"

--BOUNDARY-1
Content-Type: text/plain; charset=us-ascii

Your message could not be delivered.

--BOUNDARY-1
Content-Type: message/delivery-status

Reporting-MTA: dns; mx.example.net

Final-Recipient: rfc822; dead@example.com
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown

--BOUNDARY-1
Content-Type: message/rfc822

From: Pukeko <admin@trendibizz.com>
To: <dead@example.com>
Subject: Your enquiry
Message-ID: <outbox-42.abc@trendibizz.com>

Hello
--BOUNDARY-1--
"""


def test_hard_bounce_is_parsed_with_its_original_message_id():
    parsed = bounces.parse(DSN_HARD)
    assert parsed is not None
    assert parsed["address"] == "dead@example.com"
    assert parsed["status"] == "5.1.1"
    assert parsed["action"] == "failed"
    assert parsed["hard"] is True
    assert parsed["original_message_id"] == "<outbox-42.abc@trendibizz.com>"


def test_transient_delay_is_not_a_hard_bounce():
    parsed = bounces.parse(DSN_HARD.replace(b"Status: 5.1.1", b"Status: 4.2.2")
                           .replace(b"Action: failed", b"Action: delayed")
                           .replace(b"550 5.1.1 User unknown", b"450 mailbox full"))
    assert parsed is not None
    assert parsed["hard"] is False


def test_no_route_is_treated_as_permanent():
    parsed = bounces.parse(DSN_HARD.replace(b"Status: 5.1.1", b"Status: 4.4.1")
                           .replace(b"550 5.1.1 User unknown", b"no route to host"))
    assert parsed is not None
    assert parsed["hard"] is True


def test_ordinary_mail_is_not_a_delivery_report():
    assert bounces.parse(b"Subject: Hello\r\n\r\nHi there\r\n") is None


def test_malformed_input_never_raises():
    assert bounces.parse(b"\xff\xfe garbage") is None
    assert bounces.parse(b"") is None


def test_bounce_detection_uses_sender_and_content_type():
    assert bounces.looks_like_bounce("MAILER-DAEMON@example.net", "", "")
    assert bounces.looks_like_bounce("bounces-123@example.net", "", "")
    assert bounces.looks_like_bounce("someone@example.com", "Undelivered Mail", "")
    assert not bounces.looks_like_bounce("conrad@pukekoconstruction.co.nz",
                                         "Re: quote for deck", "text/plain")
