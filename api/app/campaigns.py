"""Reactivation campaigns: re-engage past leads by email or text, safely.

Rules built into the engine (not left to the operator):
  - Only leads with recorded MARKETING consent are eligible (leads.consent_marketing). The older
    consent_contact flag means "contact me about my enquiry" and is not enough.
  - Contacts who opted out are never messaged. Email carries a signed unsubscribe link and the
    one-click header. Texts end with "Reply STOP to opt out." (STOP handling already exists).
  - The client must have campaigns_enabled switched on. It is off by default.
  - A campaign is a draft first. Sending requires the audience size seen in the preview, so the list
    cannot change between preview and send.
  - Recipient cap per campaign, a cooldown so nobody is messaged twice in a short time, and sends are
    spread over time (per-hour limits) instead of firing at once.
  - Texts still respect quiet hours in the outbox, and a kill switch is checked at delivery time.
"""

import json
import string
from datetime import datetime, timedelta, timezone

from . import casetimeline, db, outbox, sms, unsub
from .config import get_settings
from .contact import contact_key

CHANNELS = ("sms", "email")
LEAD_STATUSES = ("new", "contacted", "booked", "won", "lost")
DEFAULT_STATUSES = ["new", "contacted", "lost"]
PLACEHOLDERS = {"first", "business"}
STOP_LINE = " Reply STOP to opt out."


class CampaignError(ValueError):
    pass


# ---- templates ---------------------------------------------------------------
def validate_template(template: str) -> None:
    if not template.strip():
        raise CampaignError("Message body is empty")
    if len(template) > 600:
        raise CampaignError("Message body is too long (600 characters max)")
    try:
        fields = [f for _, f, _, _ in string.Formatter().parse(template) if f is not None]
    except ValueError as exc:
        raise CampaignError(f"Bad placeholder syntax: {exc}")
    bad = [f for f in fields if f not in PLACEHOLDERS]
    if bad:
        raise CampaignError(f"Unknown placeholder {{{bad[0]}}}. Allowed: {{first}}, {{business}}")


def first_name(name: str) -> str:
    return (name or "").strip().split(" ")[0] or "there"


def render(template: str, lead: dict, tenant: dict) -> str:
    return template.format(first=first_name(lead.get("name") or ""), business=tenant["name"])


def email_footer(tenant: dict, to_addr: str) -> str:
    lines = ["", "--", f"You are receiving this because you contacted {tenant['name']}."]
    if tenant.get("notify_email"):
        lines.append(f"Contact: {tenant['notify_email']}")
    lines.append(f"Unsubscribe: {unsub.url_for(tenant['id'], to_addr)}")
    return "\n".join(lines)


def mask(contact: str) -> str:
    if "@" in contact:
        local, _, domain = contact.partition("@")
        return f"{local[:1]}***@{domain}"
    return f"{contact[:3]}{'*' * max(len(contact) - 6, 1)}{contact[-3:]}"


# ---- scheduling --------------------------------------------------------------
def send_times(start: datetime, count: int, per_hour: int) -> list[datetime]:
    """Spread `count` sends from `start` at no more than `per_hour` per hour."""
    gap = timedelta(seconds=3600 / max(per_hour, 1))
    return [start + gap * i for i in range(count)]


# ---- create ------------------------------------------------------------------
def clean_filters(raw: dict) -> dict:
    s = get_settings()
    statuses = raw.get("statuses") or DEFAULT_STATUSES
    if not isinstance(statuses, list) or not set(statuses) <= set(LEAD_STATUSES):
        raise CampaignError("statuses must be a list of: " + ", ".join(LEAD_STATUSES))
    older = int(raw.get("older_than_days", 30))
    min_score = int(raw.get("min_score", 0))
    raw_cap = raw.get("max_recipients")
    cap = s.campaign_max_recipients if raw_cap is None else int(raw_cap)  # 0 is an error, not "use default"
    if not 0 <= older <= 3650:
        raise CampaignError("older_than_days must be 0-3650")
    if not 0 <= min_score <= 100:
        raise CampaignError("min_score must be 0-100")
    if cap < 1:
        raise CampaignError("max_recipients must be at least 1")
    return {
        "statuses": statuses,
        "older_than_days": older,
        "min_score": min_score,
        "max_recipients": min(cap, s.campaign_max_recipients),
    }


async def create(tenant: dict, name: str, channel: str, subject: str, body: str, filters: dict) -> dict:
    if channel not in CHANNELS:
        raise CampaignError("channel must be sms or email")
    validate_template(body)
    if channel == "email":
        if not subject.strip():
            raise CampaignError("An email campaign needs a subject")
        validate_template(subject)
    row = await db.pool().fetchrow(
        "INSERT INTO campaigns (tenant_id, name, channel, subject, body, filters) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb) RETURNING *",
        tenant["id"], name.strip()[:120] or "Campaign", channel, subject.strip()[:200], body,
        json.dumps(clean_filters(filters)),
    )
    return dict(row)


async def get(campaign_id: int) -> dict | None:
    row = await db.pool().fetchrow("SELECT * FROM campaigns WHERE id = $1", campaign_id)
    return dict(row) if row else None


def _filters(campaign: dict) -> dict:
    raw = campaign["filters"]
    return json.loads(raw) if isinstance(raw, str) else dict(raw)


# ---- audience ----------------------------------------------------------------
async def audience(tenant: dict, campaign: dict) -> dict:
    """Who would receive this campaign right now, and why others are left out."""
    s = get_settings()
    f = _filters(campaign)
    channel = campaign["channel"]
    column = "phone" if channel == "sms" else "email"
    leads = await db.pool().fetch(
        f"""
        SELECT id, name, email, phone, status, score, created_at FROM leads
        WHERE tenant_id = $1 AND consent_marketing = true AND {column} <> ''
          AND status = ANY($2::text[]) AND score >= $3
          AND created_at < now() - make_interval(days => $4)
        ORDER BY score DESC, created_at DESC
        """,
        tenant["id"], f["statuses"], f["min_score"], f["older_than_days"],
    )
    opted_out = {r["contact"] for r in await db.pool().fetch(
        "SELECT contact FROM opt_outs WHERE tenant_id = $1", tenant["id"])}
    recent = {contact_key(r["to_addr"], casetimeline.tenant_country_code(tenant)) for r in await db.pool().fetch(
        "SELECT to_addr FROM outbox WHERE tenant_id = $1 AND campaign_id IS NOT NULL AND channel = $2 "
        "AND status IN ('pending','sending','sent') AND created_at > now() - make_interval(days => $3)",
        tenant["id"], channel, s.campaign_cooldown_days)}

    seen: set[str] = set()
    eligible: list[dict] = []
    skipped = {"opted_out": 0, "cooldown": 0, "duplicate": 0, "over_cap": 0}
    for lead in leads:
        lead = dict(lead)
        key = contact_key(lead[column], casetimeline.tenant_country_code(tenant))
        if key in seen:
            skipped["duplicate"] += 1
        elif key in opted_out:
            skipped["opted_out"] += 1
        elif key in recent:
            skipped["cooldown"] += 1
        elif len(eligible) >= f["max_recipients"]:
            skipped["over_cap"] += 1
        else:
            eligible.append({**lead, "to_addr": lead[column], "key": key})
        seen.add(key)
    return {"eligible": eligible, "skipped": skipped}


def readiness(tenant: dict, channel: str) -> list[str]:
    """Reasons this campaign could not be sent right now (empty list = ready)."""
    problems = []
    if not tenant.get("campaigns_enabled"):
        problems.append("Campaigns are switched off for this client (campaigns_enabled).")
    if channel == "sms":
        if not tenant.get("sms_enabled"):
            problems.append("Texting is not enabled for this client (sms_enabled).")
        if not sms.sender_ready(tenant):
            problems.append("No SMS provider is configured.")
    else:
        if not get_settings().email_configured:
            problems.append("Email (SMTP) is not configured.")
        if not unsub.available():
            problems.append("UNSUBSCRIBE_SECRET (or ADMIN_TOKEN) is not set, so unsubscribe links cannot be made.")
    return problems


async def preview(tenant: dict, campaign: dict) -> dict:
    result = await audience(tenant, campaign)
    sample_lead = result["eligible"][0] if result["eligible"] else None
    return {
        "recipients": len(result["eligible"]),
        "skipped": result["skipped"],
        "ready": not readiness(tenant, campaign["channel"]),
        "problems": readiness(tenant, campaign["channel"]),
        "sample_recipients": [
            {"name": first_name(x["name"]), "contact": mask(x["to_addr"]), "score": x["score"]}
            for x in result["eligible"][:5]
        ],
        "sample_message": render(campaign["body"], sample_lead, tenant) if sample_lead else None,
    }


# ---- send / cancel -------------------------------------------------------------
async def send(tenant: dict, campaign: dict, expected_recipients: int) -> dict:
    if campaign["status"] != "draft":
        raise CampaignError(f"Campaign is already {campaign['status']}")
    problems = readiness(tenant, campaign["channel"])
    if problems:
        raise CampaignError(" ".join(problems))
    result = await audience(tenant, campaign)
    eligible = result["eligible"]
    if len(eligible) != expected_recipients:
        raise CampaignError(
            f"Audience changed: preview showed {expected_recipients} but {len(eligible)} are eligible now. "
            "Preview again and confirm the new number."
        )
    if not eligible:
        raise CampaignError("Nobody is eligible to receive this campaign")

    s = get_settings()
    channel = campaign["channel"]
    per_hour = s.campaign_sms_per_hour if channel == "sms" else s.campaign_email_per_hour
    times = send_times(datetime.now(timezone.utc), len(eligible), per_hour)
    queued = 0
    for lead, when in zip(eligible, times):
        text = render(campaign["body"], lead, tenant)
        if channel == "sms":
            text = text if text.rstrip().endswith("STOP to opt out.") else text.rstrip() + STOP_LINE
            subject = ""
        else:
            text = text + "\n" + email_footer(tenant, lead["to_addr"])
            subject = render(campaign["subject"], lead, tenant)
        if await outbox.enqueue(
            tenant["id"], "campaign", channel, lead["to_addr"], text, subject=subject, send_at=when,
            dedupe_key=f"camp:{campaign['id']}:{channel}:{lead['key']}", lead_id=lead["id"],
            campaign_id=campaign["id"],
        ):
            queued += 1
    await db.pool().execute(
        "UPDATE campaigns SET status = 'queued', queued_at = now(), recipient_count = $2 WHERE id = $1",
        campaign["id"], queued,
    )
    return {"queued": queued, "first_send": times[0].isoformat(), "last_send": times[-1].isoformat()}


async def cancel(campaign: dict) -> int:
    result = await db.pool().execute(
        "UPDATE outbox SET status = 'cancelled' WHERE campaign_id = $1 AND status = 'pending'", campaign["id"])
    await db.pool().execute("UPDATE campaigns SET status = 'cancelled' WHERE id = $1", campaign["id"])
    return int(result.split()[-1])


async def stats(campaign_id: int) -> dict:
    rows = await db.pool().fetch(
        "SELECT status, count(*) AS n FROM outbox WHERE campaign_id = $1 GROUP BY status", campaign_id)
    return {r["status"]: r["n"] for r in rows}


# ---- unsubscribe ---------------------------------------------------------------
async def unsubscribe(token: str) -> dict | None:
    """Honour a valid unsubscribe token. Returns {'tenant_name', 'contact'} or None if invalid."""
    parsed = unsub.read_token(token)
    if parsed is None:
        return None
    tenant_id, contact = parsed
    name = await db.pool().fetchval("SELECT name FROM tenants WHERE id = $1::uuid", tenant_id)
    if name is None:
        return None
    await outbox.opt_out(tenant_id, contact)
    await db.pool().execute(
        "UPDATE outbox SET status = 'cancelled' WHERE tenant_id = $1::uuid AND to_addr = $2 "
        "AND campaign_id IS NOT NULL AND status = 'pending'",
        tenant_id, contact,
    )
    return {"tenant_name": name, "contact": contact}
