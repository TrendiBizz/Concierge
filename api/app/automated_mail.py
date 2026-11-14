"""Is this email from a robot rather than a person?

Why this exists: on 2026-11-15 at 10:05 NZDT a Stripe marketing email ("Reach more customers with
your payment link", from notifications@stripe.com) became an "Email enquiry" lead, a follow-up task
and an owner alert by email and text. The older checks only took the auto-reply away from robots;
the lead and the alert still happened. A message that is automated now gets no lead, no
acknowledgement, no secretary job and no owner alert. It is still stored (as a discarded draft) so
nothing is lost without trace.

``classify()`` returns the first reason it finds, or None for mail that looks like a person wrote it.
"""
from email.message import Message
from email.parser import BytesHeaderParser
from email.utils import parseaddr

AUTOMATED_PRECEDENCE = {"bulk", "junk", "list", "auto_reply"}

# Local parts that only machines use. Matched exactly or followed by a separator
# ("notifications+abc", "no-reply-billing"), so "alerton@" or "bouncer@" stay people.
AUTOMATED_LOCALPARTS = (
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply", "do_not_reply",
    "notifications", "notification", "notify", "mailer-daemon", "postmaster",
    "bounce", "bounces", "alerts", "alert",
)
_SEPARATORS = "+-_."

# Platforms that never send a customer enquiry. Subdomains count (bounce.stripe.com), lookalikes do
# not: gmail.com is a customer, google.com is a robot.
AUTOMATED_DOMAINS = (
    "stripe.com", "google.com", "cloudflare.com", "github.com", "brevo.com", "sendinblue.com",
    "facebookmail.com", "linkedin.com", "mailchimp.com", "mcsv.net", "intuit.com", "xero.com",
    "digitalocean.com", "heygen.com", "calendly.com", "zoom.us", "atlassian.net",
)

AUTOMATED_SUBJECTS = ("automatic reply", "auto:", "auto-reply", "autoreply", "out of office",
                      "undeliverable", "delivery status notification", "mail delivery",
                      "returned mail")


def _address(value: str) -> tuple[str, str]:
    addr = (parseaddr(value or "")[1] or (value or "")).strip().lower()
    if "@" not in addr:
        return addr, ""
    local, _, domain = addr.rpartition("@")
    return local, domain.rstrip(".")


def localpart_reason(sender: str) -> str | None:
    local, _ = _address(sender)
    if not local:
        return None
    for p in AUTOMATED_LOCALPARTS:
        if local == p or (local.startswith(p) and local[len(p)] in _SEPARATORS):
            return "localpart:" + p
    return None


def domain_reason(sender: str) -> str | None:
    _, domain = _address(sender)
    if not domain:
        return None
    for d in AUTOMATED_DOMAINS:
        if domain == d or domain.endswith("." + d):
            return "domain:" + d
    return None


def subject_reason(subject: str) -> str | None:
    return "subject" if (subject or "").strip().lower().startswith(AUTOMATED_SUBJECTS) else None


def _headers(raw: bytes | None) -> Message | None:
    if not raw:
        return None
    try:
        return BytesHeaderParser().parsebytes(raw[:65536])
    except Exception:  # noqa: BLE001 - an unparsable message is simply not marked
        return None


def header_reason(raw: bytes | None) -> str | None:
    """RFC 3834 and mailing-list markers: Auto-Submitted other than "no", Precedence
    bulk/junk/list/auto_reply, X-Auto-Response-Suppress, List-Id or List-Unsubscribe."""
    headers = _headers(raw)
    if headers is None:
        return None
    auto = str(headers.get("Auto-Submitted") or "").strip().lower()
    if auto and not auto.startswith("no"):
        return "header:auto-submitted"
    if str(headers.get("Precedence") or "").strip().lower() in AUTOMATED_PRECEDENCE:
        return "header:precedence"
    for name in ("List-Unsubscribe", "List-Id", "X-Auto-Response-Suppress"):
        if headers.get(name) is not None:
            return "header:" + name.lower()
    return None


def classify(sender: str, subject: str = "", raw: bytes | None = None,
             envelope_from: str | None = None) -> str | None:
    """The reason this message is automated, or None when a person plausibly wrote it.

    The header From (``sender``) is checked for robot local parts and platform domains. The
    envelope sender is checked for platform domains only: Stripe's bounce address
    (…@bounce.stripe.com) is a robot, while a person's envelope local part tells us nothing.
    """
    headers = _headers(raw)
    from_header = str(headers.get("From") or "") if headers is not None else ""
    for check in (
        header_reason(raw),
        localpart_reason(sender),
        localpart_reason(from_header) if from_header else None,
        domain_reason(sender),
        domain_reason(from_header) if from_header else None,
        domain_reason(envelope_from or ""),
        subject_reason(subject),
    ):
        if check:
            return check
    return None
