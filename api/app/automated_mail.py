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
import re

AUTOMATED_PRECEDENCE = {"bulk", "junk", "list", "auto_reply"}

# Local parts that only machines use. Matched exactly or followed by a separator
# ("notifications+abc", "no-reply-billing"), so "alerton@" or "bouncer@" stay people.
AUTOMATED_LOCALPARTS = (
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply", "do_not_reply",
    "notifications", "notification", "notify", "mailer-daemon", "postmaster",
    "bounce", "bounces", "alerts", "alert",
    # SEO, monitoring and billing digests. Ahrefs signs its crawl reports "sa@ahrefs.com" and puts
    # no List-Id on them, so on 2026-11-15 a crawl report became an enquiry and an owner alert.
    "sa", "news", "newsletter", "digest", "updates", "promo", "promotions", "marketing",
    "reports", "report", "seo",
)
_SEPARATORS = "+-_."

# Platforms that never send a customer enquiry. Subdomains count (bounce.stripe.com), lookalikes do
# not: gmail.com is a customer, google.com is a robot.
AUTOMATED_DOMAINS = (
    "stripe.com", "google.com", "cloudflare.com", "github.com", "brevo.com", "sendinblue.com",
    "facebookmail.com", "linkedin.com", "mailchimp.com", "mcsv.net", "intuit.com", "xero.com",
    "digitalocean.com", "heygen.com", "calendly.com", "zoom.us", "atlassian.net",
    # Account-security and directory platforms. 15 Nov 15:56 NZDT: a Microsoft verification
    # email from account-security-noreply@accountprotection.microsoft.com became an enquiry
    # and an owner SMS that included the security code. Subdomains count; consumer mailboxes
    # (gmail.com, outlook.com, icloud.com) do not.
    "microsoft.com", "microsoftonline.com", "apple.com", "g2.com",
    # SEO and site-monitoring tools: they report, they never enquire.
    "ahrefs.com", "semrush.com", "moz.com", "majestic.com", "screamingfrog.co.uk",
    "sitebulb.com", "uptimerobot.com", "pingdom.com", "statuspage.io", "sentry.io",
    "datadoghq.com", "newrelic.com",
)

AUTOMATED_SUBJECTS = ("automatic reply", "auto:", "auto-reply", "autoreply", "out of office",
                      "undeliverable", "delivery status notification", "mail delivery",
                      "returned mail",
                      # scheduled reports: "New crawl for Trendibizz", "Site audit: 39 URLs"
                      "new crawl", "site audit", "crawl completed", "your weekly report",
                      "site health")


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
        if local == p:
            return "localpart:" + p
        # Prefix: notifications+abc, no-reply-billing. Suffix: account-security-noreply.
        # "alerton@" and "bouncer@" stay people because the token is not a whole segment.
        if len(local) > len(p) and (
            (local.startswith(p) and local[len(p)] in _SEPARATORS)
            or (local.endswith(p) and local[-len(p) - 1] in _SEPARATORS)
        ):
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


# Strong copy used by account-security mail. Matched as a substring in the subject or body.
VERIFY_PHRASES = (
    "verify your email",
    "security code",
    "verification code",
    "one-time code",
    "one time code",
    "one-time password",
    "email verification",
    "verify your address",
    "your sign-in code",
    "your login code",
)

# Weaker platform login subjects. Not applied to the body: a person can write
# "I can't sign in to my account" and that is still an enquiry.
VERIFY_SUBJECT_PHRASES = (
    "log-in to",
    "log in to",
    "login to",
    "sign in to your",
    "sign-in to",
)


def verification_reason(subject: str = "", body: str = "") -> str | None:
    """Account-security / verify-your-email copy, or None if this looks like a person."""
    subj = (subject or "").strip().lower()
    text_body = (body or "").strip().lower()
    for phrase in VERIFY_PHRASES:
        if phrase in subj:
            return "subject:verify"
        if phrase in text_body:
            return "body:verify"
    for phrase in VERIFY_SUBJECT_PHRASES:
        if phrase in subj:
            return "subject:verify"
    return None


# Cold supplier / bulk-outreach copy. 18 Nov 2026 15:31 NZDT: a Shenzhen hardware factory pitch
# ("TRENDIBIZZ offers travel cases, belt buckles... Do you currently source any of these parts?")
# from a throwaway domain, with no List-Unsubscribe header, became an "Email enquiry" lead and an
# owner alert. Phrases are narrow so a real customer who writes "unsubscribe" is still an enquiry.
SOLICITATION_PHRASES = (
    "no longer wish to receive",
    "do not wish to receive",
    "don't wish to receive",
    "click on the following link: unsubscribe",
    "click here to unsubscribe",
    "reply unsubscribe",
    "do you currently source",
    "are you currently sourcing",
    "we are a manufacturer",
    "we are a factory",
    "factory direct",
    "alibaba.com",
    "made-in-china.com",
)


def solicitation_reason(body: str = "") -> str | None:
    text = (body or "").lower()
    for phrase in SOLICITATION_PHRASES:
        if phrase in text:
            return "body:solicitation"
    return None


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
             envelope_from: str | None = None, body: str = "") -> str | None:
    """The reason this message is automated, or None when a person plausibly wrote it.

    The header From (``sender``) is checked for robot local parts and platform domains. The
    envelope sender is checked for platform domains only: Stripe's bounce address
    (…@bounce.stripe.com) is a robot, while a person's envelope local part tells us nothing.
    Subject and body are also checked for account-security / verify-your-email copy.
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
        verification_reason(subject, body),
        solicitation_reason(body),
    ):
        if check:
            return check
    return None


# 4–8 digit codes next to words like code/verify. Phone numbers are longer, so they stay.
_CODE_AFTER_LABEL = re.compile(
    r"(?i)((?:\b(?:security|verification|one[-\s]time|sign[-\s]?in|login|email)\s+)?"
    r"\b(?:code|otp)\b(?:\s*(?:is|was|:|-))?\s*)(\d{4,8})\b"
)
_CODE_BEFORE_LABEL = re.compile(
    r"(?i)\b(\d{4,8})\b(\s*(?:is\s+your\s+)?"
    r"(?:security\s+|verification\s+|one[-\s]time\s+)?(?:code|otp)\b)"
)
_CODE_TO_VERIFY = re.compile(
    r"(?i)\b(\d{4,8})\b(\s+(?:to\s+)?(?:verify|sign\s+in|log\s+in))"
)


def redact_security_codes(text: str) -> str:
    """Replace 4–8 digit verification codes in owner-alert text. Leaves other numbers alone."""
    if not text:
        return text
    text = _CODE_AFTER_LABEL.sub(r"\1[redacted]", text)
    text = _CODE_BEFORE_LABEL.sub(r"[redacted]\2", text)
    text = _CODE_TO_VERIFY.sub(r"[redacted]\2", text)
    return text
