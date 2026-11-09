"""Signed unsubscribe links for campaign emails.

A token carries the tenant and the contact, signed with UNSUBSCRIBE_SECRET (falls back to ADMIN_TOKEN).
No database lookup is needed to verify one, and a token cannot be forged or edited to unsubscribe
somebody else. Without a secret, links cannot be made and email campaigns refuse to send.
"""

import base64
import hashlib
import hmac

from .config import get_settings


def _secret() -> bytes:
    s = get_settings()
    return (s.unsubscribe_secret or s.admin_token or "").encode()


def available() -> bool:
    return bool(_secret())


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]


def make_token(tenant_id, contact: str) -> str:
    if not available():
        raise RuntimeError("UNSUBSCRIBE_SECRET (or ADMIN_TOKEN) is not set")
    payload = base64.urlsafe_b64encode(f"{tenant_id}|{contact}".encode()).decode().rstrip("=")
    return f"{payload}.{_sign(payload)}"


def read_token(token: str) -> tuple[str, str] | None:
    """Return (tenant_id, contact) for a valid token, otherwise None."""
    if not available() or not token:
        return None
    payload, _, signature = token.partition(".")
    if not payload or not hmac.compare_digest(_sign(payload), signature):
        return None
    try:
        raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    tenant_id, sep, contact = raw.partition("|")
    return (tenant_id, contact) if sep and tenant_id and contact else None


def url_for(tenant_id, contact: str) -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/api/v1/unsubscribe/{make_token(tenant_id, contact)}"
