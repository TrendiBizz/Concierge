"""A customer's message must never arrive as a wall of RFC822 headers.

On 13 Nov a health-check alert was emailed to a monitored mailbox. The inbound pipeline treated it as
an enquiry and texted the owner: "Email enquiry for Trendi Concierge" followed by the Received chain,
ARC-Seal, DKIM signatures and base64 blobs. Two faults: the alert mail lacked our own-mail marker, and
raw source was used as the message.
"""

from app.cloudflare_inbound import strip_headers

RAW = (
    "Received: from gx.d.sender-sib.com (77.32.148.24)\r\n"
    " by cloudflare-email.net (cloudflare) id HWa.JV5mgpT4W\r\n"
    " for <admin@trendibizz.com>; Fri, 13 Nov 2026 07:47:51 +0000\r\n"
    "ARC-Seal: i=1; a=rsa-sha256; d=cloudflare-email.net;\r\n"
    "DKIM-Signature: v=1; a=rsa-sha256; b=SSoW4O9DFpyl\r\n"
    "Subject: ALERT: Concierge health check failing (api)\r\n"
    "\r\n"
    "Concierge health check failed on 152.42.239.240.\n\nFailing checks: api\n"
)


def test_a_raw_message_becomes_just_its_body():
    cleaned = strip_headers(RAW)
    assert cleaned.startswith("Concierge health check failed")
    assert "Received:" not in cleaned
    assert "ARC-Seal" not in cleaned
    assert "DKIM-Signature" not in cleaned


def test_an_ordinary_message_is_left_alone():
    text = "Hi, I need a quote for 120 m2 of cladding.\nThanks, Jane"
    assert strip_headers(text) == text


def test_a_message_starting_with_a_colon_ish_line_is_not_mistaken_for_headers():
    text = "Budget: 20k\nTimeline: March"
    assert strip_headers(text) == text, "one header-looking line is not a header block"


def test_empty_and_header_only_input_is_safe():
    assert strip_headers("") == ""
    assert strip_headers("From: a@b.c\r\nSubject: hi\r\n\r\n") == ""
    assert strip_headers("From: a@b.c\r\nSubject: hi\r\n\r\nbody") == "body"
