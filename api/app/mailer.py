import asyncio
import smtplib
from email.message import EmailMessage

from .config import get_settings


class EmailNotConfigured(RuntimeError):
    pass


def _send_sync(to_addr: str, subject: str, body: str, headers: dict | None = None) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to_addr
    msg["Subject"] = subject
    for name, value in (headers or {}).items():
        msg[name] = value
    msg.set_content(body)

    if s.smtp_security == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20)
    else:
        server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20)
    try:
        if s.smtp_security == "starttls":
            server.starttls()
        if s.smtp_user:
            server.login(s.smtp_user, s.smtp_password)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except smtplib.SMTPException:
            pass


async def send_email(to_addr: str, subject: str, body: str, headers: dict | None = None) -> None:
    if not get_settings().email_configured:
        raise EmailNotConfigured("SMTP_HOST / SMTP_FROM are not configured")
    await asyncio.to_thread(_send_sync, to_addr, subject, body, headers)
