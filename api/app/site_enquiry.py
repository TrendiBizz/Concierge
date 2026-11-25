"""Enquiries from the public website's forms.

`/contact` and `/concierge-start` used to build a `mailto:` link and say "nothing has been sent".
A visitor with no mail app configured (most phones, any work laptop) lost their enquiry silently.
Now the form posts here: the enquiry is stored first, so it cannot be lost, and the operator is
told by email second, so a mail fault cannot lose it either. The page keeps the old email draft as
the fallback if this endpoint is unreachable.

Spam handling is deliberately small: a hidden field real people never fill, a per-address and a
global hourly cap, hard length limits and an address check. Nothing is sent back to the visitor, so
the form cannot be used to mail a stranger.
"""

from __future__ import annotations

import logging
import re

from . import db, flood_guard, outbox, owner_auth

log = logging.getLogger("concierge.site_enquiry")

KINDS = ("seo", "concierge", "security")
_LABELS = {"concierge": "Concierge setup", "seo": "SEO / AI visibility", "security": "Security review scoping"}
STATUSES = ("new", "contacted", "done", "spam")
PER_IP_PER_HOUR = 5
ALL_PER_HOUR = 60
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_REF = re.compile(r"[^A-Za-z0-9-]")


class Refused(Exception):
    """The enquiry was not stored. `.status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _clean(value: str, limit: int, *, multiline: bool = False) -> str:
    text = _CONTROL.sub("", str(value or "")).strip()
    if not multiline:
        text = " ".join(text.split())
    return text[:limit]


def _website(value: str) -> str:
    text = _clean(value, 300)
    if not text:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*:", text, re.I):
        text = "https://" + text
    host = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text, flags=re.I).split("/")[0]
    if not text.lower().startswith(("http://", "https://")) or "." not in host or " " in text:
        raise Refused("Enter your website address, such as https://example.com.")
    return text


async def submit(*, kind: str, email: str, name: str = "", website: str = "", message: str = "",
                 plan: str = "", channels: list[str] | None = None, referral: str = "",
                 trap: str = "", ip: str = "", user_agent: str = "") -> dict:
    if kind not in KINDS:
        raise Refused("Unknown enquiry type.")
    if trap:
        # A robot filled the hidden field. Answer as if it worked and keep nothing.
        return {"ok": True, "id": None}
    try:
        address = owner_auth.clean_email(email)
    except ValueError:
        raise Refused("Enter an email address we can reply to.") from None
    if not flood_guard.memory_allow("site-enquiry:ip", ip or "unknown", PER_IP_PER_HOUR, 3600) \
            or not flood_guard.memory_allow("site-enquiry:all", "all", ALL_PER_HOUR, 3600):
        raise Refused("Too many enquiries just now. Email admin@trendibizz.com instead.", 429)
    row = await db.pool().fetchrow(
        "INSERT INTO site_enquiries(kind,name,email,website,message,plan,channels,referral,ip,user_agent) "
        "VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id",
        kind, _clean(name, 120), address, _website(website), _clean(message, 4000, multiline=True),
        _clean(plan, 20), _clean(", ".join(channels or []), 300), _REF.sub("", referral or "")[:32].upper(),
        _clean(ip, 64), _clean(user_agent, 300),
    )
    await _tell_the_operator(str(row["id"]), kind, address, name, website, message, plan, channels, referral)
    return {"ok": True, "id": str(row["id"])}


async def _tell_the_operator(enquiry_id, kind, email, name, website, message, plan, channels, referral) -> None:
    """Capture into the trendi-support CRM and email the operator. A failure is logged; the enquiry is already stored."""
    try:
        tenant_row = await db.pool().fetchrow("SELECT * FROM tenants WHERE slug='trendi-support'")
        if tenant_row is None:
            log.warning("site enquiry %s stored but there is no trendi-support tenant to alert", enquiry_id)
            return
        tenant = dict(tenant_row)
        to_addr = (tenant.get("notify_email") or tenant.get("to_addr") or "").strip() or "admin@trendibizz.com"
        lines = [f"A website enquiry came in ({_LABELS.get(kind, kind)}).", "",
                 f"Name:    {_clean(name, 120) or '(not given)'}",
                 f"Email:   {email}",
                 f"Website: {_clean(website, 300) or '(not given)'}"]
        if plan:
            lines.append(f"Plan:    {_clean(plan, 20)}")
        if channels:
            lines.append(f"Wants:   {_clean(', '.join(channels), 300)}")
        if referral:
            lines.append(f"Referral code: {_REF.sub('', referral)[:32].upper()}")
        lines += ["", _clean(message, 4000, multiline=True) or "(no message)", "",
                  f"Reply to {email}. Enquiry {enquiry_id}; also visible in Studio CRM."]
        body_text = "\n".join(lines)
        lead_id = None
        if hasattr(db.pool(), "acquire"):
            try:
                from . import enquiries
                lead = await enquiries.capture(
                    tenant, "chat", f"site-enquiry:{enquiry_id}", body_text,
                    email=email, name=_clean(name, 120), page_url=_clean(website, 300) or None,
                    automated=True,  # operator email below carries the full formatted summary
                )
                lead_id = lead.get("id") if isinstance(lead, dict) else None
            except Exception:
                log.exception("site enquiry %s CRM capture failed", enquiry_id)
        kw = {"subject": f"Website enquiry — {_clean(website or email, 80)}",
              "dedupe_key": f"site-enquiry:{enquiry_id}"}
        if lead_id is not None:
            kw["lead_id"] = lead_id
        await outbox.enqueue(tenant["id"], "owner_alert", "email", to_addr, body_text, **kw)
    except Exception:  # noqa: BLE001 - stored already; the admin list still shows it
        log.exception("site enquiry %s could not be emailed", enquiry_id)


async def list_all(status: str = "") -> list[dict]:
    sql = "SELECT * FROM site_enquiries"
    args = []
    if status in STATUSES:
        sql += " WHERE status=$1"
        args.append(status)
    rows = await db.pool().fetch(sql + " ORDER BY created_at DESC LIMIT 200", *args)
    out = []
    for row in rows:
        item = dict(row)
        item["id"] = str(item["id"])
        item["created_at"] = item["created_at"].isoformat()
        out.append(item)
    return out
