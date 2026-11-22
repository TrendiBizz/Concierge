import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from . import flood_guard
from .config import get_settings


class EmailNotConfigured(RuntimeError):
    pass


class EmailRateLimited(RuntimeError):
    pass


def _send_sync(to_addr: str, subject: str, body: str, headers: dict | None = None,
               from_name: str | None = None, html: str | None = None,
               from_addr: str | None = None, dkim: dict | None = None) -> None:
    s = get_settings()
    msg = EmailMessage()
    sender = from_addr or s.smtp_from
    msg["From"] = formataddr((from_name, sender)) if from_name else sender
    msg["To"] = to_addr
    msg["Subject"] = subject
    # RFC 3834 marker plus our own: lets the inbound side recognise mail we sent ourselves.
    msg["Auto-Submitted"] = "auto-generated"
    msg["X-Concierge-Mail"] = "1"
    for name, value in (headers or {}).items():
        msg[name] = value
    msg.set_content(body)
    if html:
        # A plain-text part is mandatory: it is what a text-only client shows and what a spam
        # filter expects to find alongside the HTML.
        msg.add_alternative(html, subtype="html")
    if dkim and dkim.get("domain") and dkim.get("selector") and dkim.get("private_key_pem"):
        from . import email_domain
        msg["DKIM-Signature"] = email_domain.dkim_sign_header(
            msg, domain=dkim["domain"], selector=dkim["selector"], private_key_pem=dkim["private_key_pem"],
        )

    if s.smtp_security == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20)
    else:
        server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20)
    try:
        if s.smtp_security == "starttls":
            server.starttls()
        if s.smtp_user:
            server.login(s.smtp_user, s.smtp_password)
        # Envelope sender stays the authenticated SMTP account (the relay refuses others); the
        # tenant's own address is the visible From, which is what DMARC alignment is judged on.
        if from_addr:
            server.send_message(msg, from_addr=s.smtp_from)
        else:
            server.send_message(msg)
    finally:
        try:
            server.quit()
        except smtplib.SMTPException:
            pass


async def send_email(to_addr: str, subject: str, body: str, headers: dict | None = None,
                     from_name: str | None = None, html: str | None = None,
                     from_addr: str | None = None, dkim: dict | None = None) -> None:
    if not get_settings().email_configured:
        raise EmailNotConfigured("SMTP_HOST / SMTP_FROM are not configured")
    # Last resort for anything that bypasses the outbox: the same address, and the whole process.
    if not flood_guard.memory_allow("email:recipient", (to_addr or "").lower(), 10, 600):
        raise EmailRateLimited("Too many emails to this address in 10 minutes")
    if not flood_guard.memory_allow("email:all", "all", 200, 3600):
        raise EmailRateLimited("Too many emails in the last hour")
    await asyncio.to_thread(_send_sync, to_addr, subject, body, headers, from_name, html, from_addr, dkim)
