"""Risk assessment for untrusted inbound email.

Pure functions only: no I/O, no model calls, no tool access. The result is shown
to the business owner and decides whether a draft is quarantined. It never
authorises an action — the owner still reviews and approves every reply.
"""
import re
from urllib.parse import urlparse

URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
MAX_LINKS = 5
MAX_BYTES = 30000
_RANK = {"low": 0, "medium": 1, "high": 2}


def _max(a: str, b: str) -> str:
    return a if _RANK.get(a, 0) >= _RANK.get(b, 0) else b


def links(text: str) -> list[str]:
    """URLs in the message, for defanged display. Never fetched or rendered."""
    return [u.rstrip(".,;:!?)\"'") for u in URL.findall(text or "")][:20]


def _domain(address: str) -> str:
    value = (address or "").strip().lower()
    if "@" not in value:
        return ""
    return value.rsplit("@", 1)[1].strip(" .")


def _auth_value(auth: dict, key: str) -> str:
    value = auth.get(key) if isinstance(auth, dict) else ""
    return (value or "").strip().lower() if isinstance(value, str) else ""


def assess(auth: dict | None, sender: str, reply_to: str | None,
           subject: str, text: str, size: int | None = None,
           has_attachments: bool = False) -> dict:
    """Classify an inbound message. Never raises on attacker-controlled input."""
    auth = auth if isinstance(auth, dict) else {}
    spf = _auth_value(auth, "spf")
    dkim = _auth_value(auth, "dkim")
    dmarc = _auth_value(auth, "dmarc")
    flags: list[str] = []
    risk = "low"
    # Header hints are advisory. Only the Rust sidecar's cryptographic verdict
    # (verified_by) may lower the risk; otherwise a forged header could do it.
    verified = _auth_value(auth, "verified_by") == "email-auth"
    if _auth_value(auth, "verification_failed") == "yes":
        # The raw message arrived but the sidecar could not verify it (down,
        # timeout, oversized). Header hints are all we have, so stay medium and
        # say so explicitly rather than reporting a plain "sender unverified".
        flags.append("verification_unavailable")

    if verified:
        aligned = _auth_value(auth, "aligned") in ("yes", "true", "1")
        if dmarc == "fail":
            flags.append("dmarc_fail")
            risk = "high"
        elif dmarc == "pass" or aligned:
            # A passing signature aligned with From authenticates the sender even
            # when the domain publishes no DMARC record (dmarc=none), which is the
            # normal case for small-business mail. Reporting that as
            # unverified_sender was the bug: dkim=pass + dmarc=none came back
            # medium with a "sender not verified" label.
            risk = "low"
        elif dkim == "pass":
            # Signature verified but its d= domain is not the From domain: the
            # message really did travel through that signer, but nothing
            # authenticates the From address itself.
            flags.append("dkim_unaligned")
            risk = "medium"
        else:
            flags.append("unverified_sender")
            risk = "medium"
        if spf == "fail" or dkim == "fail":
            flags.append("auth_fail")
    else:
        flags.append("unverified_sender")
        risk = "medium"
        if dmarc == "fail":
            flags.append("dmarc_fail")
            risk = "high"
        elif spf == "fail" or dkim == "fail":
            flags.append("auth_fail")

    reply_domain = _domain(reply_to or "")
    sender_domain = _domain(sender)
    if reply_domain and sender_domain and reply_domain != sender_domain:
        flags.append("reply_to_mismatch")
        risk = _max(risk, "medium")

    if has_attachments:
        flags.append("attachments_not_stored")
    if size is not None and size > MAX_BYTES:
        flags.append("oversized")
        risk = "high"

    found = links(text)
    if len(found) > MAX_LINKS:
        flags.append("many_links")
        risk = _max(risk, "medium")
    for link in found:
        try:
            host = urlparse(link).hostname or ""
        except ValueError:
            host = ""
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.startswith("192.168.") or host.startswith("10."):
            flags.append("local_link")
            risk = "high"
            break

    return {"risk": risk, "flags": flags, "link_count": len(found), "links": found[:10]}


def sender_allowed(tenant_id: str, sender: str) -> bool:
    """Placeholder for a future allow/block list; currently permissive."""
    return True
