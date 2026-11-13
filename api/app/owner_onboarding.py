"""Tenant-scoped owner onboarding profile and safe channel visibility.

Configuration is NOT proof that an external provider works. This module does not
connect accounts, send messages, modify phone routing or enable a channel.
"""
from __future__ import annotations

import logging
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

log = logging.getLogger("concierge.onboarding")

from . import channel_authorization, db, inbound_readiness, tenants
from .config import get_settings


class OwnerBusinessProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_auto_reply: bool | None = None
    voice_enabled: bool | None = None
    native_booking: bool | None = None
    slot_minutes: int | None = Field(default=None, ge=5, le=240)
    business_hours: dict[str, list[list[str]]] | None = None

    @field_validator('business_hours')
    @classmethod
    def hours_safe(cls, value):
        if value is None:
            return value
        if len(value) > 7:
            raise ValueError('Use the seven weekday names')
        for day, windows in value.items():
            if day not in ('mon','tue','wed','thu','fri','sat','sun') or len(windows)>4:
                raise ValueError('Use weekday names and at most four opening windows per day')
            last = ''
            for window in sorted(windows):
                if len(window)!=2 or not all(re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', x) for x in window) or window[0]>=window[1] or window[0]<last:
                    raise ValueError('Use non-overlapping opening windows HH:MM-HH:MM')
                last=window[1]
        return value
    name: str | None = Field(default=None, min_length=1, max_length=160)
    site_url: str | None = Field(default=None, max_length=2048)
    greeting: str | None = Field(default=None, max_length=500)
    notify_phone: str | None = Field(default=None, max_length=32)
    notify_email: str | None = Field(default=None, max_length=254)
    timezone: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def name_safe(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Enter your business name")
        return value

    @field_validator("site_url")
    @classmethod
    def website_safe(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if value == "":
            return ""
        try:
            url = urlsplit(value)
            if (url.scheme != "https" or not url.hostname or "." not in url.hostname
                    or url.username or url.password or url.fragment
                    or any(ch.isspace() or ord(ch) < 32 for ch in value)):
                raise ValueError()
            _ = url.port
        except ValueError:
            raise ValueError("Enter a public HTTPS website address") from None
        # Saving a reference URL does not crawl it, allow an origin or activate chat.
        return value

    @field_validator("greeting")
    @classmethod
    def greeting_safe(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("Greeting contains control characters")
        return value.strip()

    @field_validator("notify_email")
    @classmethod
    def email_safe(cls, value: str | None) -> str | None:
        if value is None:
            return value
        address = value.strip().lower()
        if address == "":
            return ""
        if address.count("@") != 1 or any(ch.isspace() for ch in address):
            raise ValueError("Valid notification email required")
        local, domain = address.split("@")
        if not local or not domain or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("Valid notification email required")
        return address

    @field_validator("notify_phone")
    @classmethod
    def phone_safe(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        import re
        value = value.strip()
        # Any usual way of writing a number; the real check (and the conversion to +country form) happens in
        # update_profile, which knows the business's country.
        if not re.fullmatch(r"(\+[1-9]|\(?[0-9])[0-9 ()\-.]{6,31}", value):
            raise ValueError(PHONE_HELP)
        return value

    @field_validator("timezone")
    @classmethod
    def timezone_safe(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            raise ValueError("Use a valid IANA timezone") from None
        return value


def website_channel_status(tenant: dict, settings) -> dict:
    verified = tenant.get("slug") in {v.strip() for v in settings.website_verified_tenants.split(",") if v.strip()}
    chat = bool(tenant.get("site_url") and settings.effective_llm_key)
    voice = bool(tenant.get("voice_enabled") and settings.xai_api_key)
    return {
        "website_chat": {"configured": chat, "verified": chat and verified},
        "website_voice": {"configured": voice, "verified": voice and verified},
    }


async def overview(tenant_id) -> dict:
    tenant = await tenants.get_by_id(tenant_id)
    if tenant is None:
        raise ValueError("Tenant unavailable")
    numbers = await db.pool().fetch(
        "SELECT e164,enabled FROM phone_numbers WHERE tenant_id=$1 ORDER BY e164",
        tenant_id,
    )
    settings = get_settings()
    phone_device = await db.pool().fetchrow(
        "SELECT last_seen,verified_at,inbound_verified_at FROM sms_devices WHERE tenant_id=$1 AND enabled", tenant_id)
    from datetime import datetime, timezone
    device_online = bool(phone_device and phone_device["last_seen"] and
                         (datetime.now(timezone.utc)-phone_device["last_seen"]).total_seconds()<300)
    device_sms = tenant.get("sms_transport") == "device"
    from . import phone_relay,phone_sip
    telephone_ready=bool(tenant.get("phone_enabled") and any(r["enabled"] for r in numbers) and
                         (phone_relay.configured() or phone_sip.configured_for_tenant(tenant,numbers)))
    phone_verified=tenant.get("slug") in {v.strip() for v in settings.phone_verified_tenants.split(',') if v.strip()}
    try:
        inbound = await inbound_readiness.check(tenant_id)
    except Exception:  # noqa: BLE001 - onboarding must still render if the check fails
        log.exception("inbound readiness unavailable during onboarding")
        inbound = {"ok": False, "blocked": [{"check": "inspection",
                                             "message": "inbound readiness check failed"}],
                   "warnings": [], "checks": {}}
    return {
        "inbound_email": inbound,
        "business": {
            "slug": tenant.get("slug") or "",
            "name": tenant["name"],
            "site_url": tenant.get("site_url") or "",
            "greeting": tenant.get("greeting") or "",
            "voice_enabled": bool(tenant.get("voice_enabled")),
            "native_booking": bool(tenant.get("native_booking")),
            "slot_minutes": tenant.get("slot_minutes",30),
            "business_hours": tenant.get("business_hours",{}),
            "email_auto_reply": bool(tenant.get("email_auto_reply")),
            "notify_phone": tenant.get("notify_phone") or "",
            "notify_email": tenant.get("notify_email") or "",
            "timezone": tenant.get("timezone") or "Pacific/Auckland",
            "public_key": tenant.get("public_key") or "",
            "reply_address": tenant.get("reply_address") or "",
        },
        "channels": {
            **website_channel_status(tenant, settings),
            "booking": booking_readiness(tenant),
            "telephone": {
                "configured": telephone_ready,
                "registered_numbers": len(numbers), "verified": telephone_ready and phone_verified,
            },
            "email": {"configured": bool(tenant.get("notify_email") and settings.email_configured),
                      "verified": False},
            "sms": {"configured": bool(tenant.get("sms_enabled") and
                                        (device_online if device_sms else settings.sms_configured)),
                    "verified": bool(device_sms and device_online and phone_device["verified_at"] and phone_device["inbound_verified_at"]),
                    "connection": "paired phone" if device_sms else "carrier gateway"},
            "social": {"configured": bool(settings.social_service_enabled), "verified": False},
            "crm": {"configured": True, "verified": True, "built_in": True},
        },
        "customer_activation_enabled": False,
    }


_TZ_COUNTRY = {"Pacific/Auckland": "64", "Pacific/Chatham": "64"}


def country_code_for(tenant: dict | None) -> str:
    """The dialling country for a business's local numbers.

    Its own setting first, then its timezone (a New Zealand business must never be given the global default of 1),
    and only then the global default.
    """
    from .config import get_settings
    tenant = tenant or {}
    own = str(tenant.get("default_country_code") or "").strip()
    if own.isdigit() and 1 <= len(own) <= 3:
        return own
    zone = str(tenant.get("timezone") or "")
    if zone in _TZ_COUNTRY:
        return _TZ_COUNTRY[zone]
    if zone.startswith("Australia/"):
        return "61"
    return get_settings().default_country_code


PHONE_HELP = "Enter your mobile number, for example 027 123 4567 or +64 27 123 4567."


async def update_profile(tenant_slug: str, profile: OwnerBusinessProfile) -> dict:
    changed = profile.model_dump(exclude_unset=True, exclude_none=True)
    if not changed:
        raise ValueError("No profile fields provided")
    if changed.get("notify_phone"):
        # Accept the way people actually write a number and store it in international form.
        from .contact import normalize_phone
        current = await tenants.get_by_slug(tenant_slug) or {}
        if changed.get("timezone"):
            current = {**current, "timezone": changed["timezone"]}
        international = normalize_phone(changed["notify_phone"], country_code_for(current))
        if not international:
            raise ValueError("That phone number does not look right. " + PHONE_HELP)
        changed["notify_phone"] = international
    saved = await tenants.update(tenant_slug, changed)
    if saved is None:
        raise ValueError("Tenant unavailable")
    if saved.get("notify_email") and not saved.get("reply_address"):
        try:
            saved = await reply_address.ensure(saved)
        except Exception:  # noqa: BLE001 - onboarding must not fail on routing setup
            log.exception("reply address setup failed for %s", tenant_slug)
    return {
        "name": saved["name"],
        "site_url": saved.get("site_url") or "",
        "greeting": saved.get("greeting") or "",
        "email_auto_reply": bool(saved.get("email_auto_reply")),
        "notify_phone": saved.get("notify_phone") or "",
        "notify_email": saved.get("notify_email") or "",
        "timezone": saved.get("timezone") or "Pacific/Auckland",
    }


async def set_email_auto_reply(
    tenant: dict, *, enabled: bool, actor_id: str, acknowledgement: bool,
) -> dict:
    """Turn automatic email replies on or off for one business, as one auditable action.

    A reply is only delivered when THREE things agree, each checked at a different stage:

      1. tenants.email_auto_reply                     -- queues the job at ingress, gates the worker
      2. tenant_channel_authorizations('email_read')  -- gates the worker and delivery
      3. tenant_channel_authorizations('email_send')  -- gates delivery

    Setting only the flag leaves the worker writing jobs it then marks 'held', which reads as a
    broken feature rather than a missing authorization. Setting only the authorizations queues
    nothing. So this writes all three, and reports whether the result is actually READY.

    `acknowledgement` is required to ENABLE, because an owner is affirming they control the mailbox
    and have authority to let the assistant answer it. It is deliberately NOT required to DISABLE:
    someone switching this off may be reacting to a live problem, and making an emergency stop
    harder than the start would be backwards.

    Returns a truthful readiness report. A partial enable is reported as partial -- never as working.
    """
    if enabled and not acknowledgement:
        raise ValueError(
            "Enabling automatic email replies requires acknowledgement that the business controls "
            "this mailbox and authorizes the assistant to answer it"
        )

    saved = await tenants.update(tenant["slug"], {"email_auto_reply": bool(enabled)})
    if saved is None:
        raise ValueError("Tenant unavailable")

    failures: list[str] = []
    for channel in ("email_read", "email_send"):
        try:
            await channel_authorization.record_authorization(
                tenant["id"], actor_id,
                channel_authorization.ChannelAuthorization(
                    channel=channel, authorized=bool(enabled), acknowledgement=True,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - report, never claim success we did not achieve
            failures.append(f"{channel}: {exc}")

    ready = enabled and not failures
    return {
        "email_auto_reply": bool(enabled),
        "enabled": bool(enabled),
        # Only true when every gate is satisfied, so a caller cannot mistake a half-enable for a
        # working channel.
        "ready": ready,
        "authorizations_set": [c for c in ("email_read", "email_send")
                               if not any(f.startswith(c) for f in failures)],
        "reason": "" if ready or not enabled else "; ".join(failures)
                  or "Automatic replies are switched off",
    }


# ---------------------------------------------------------------- booking enablement

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def open_day_count(hours: dict | None) -> int:
    """How many weekdays have at least one opening window."""
    if not isinstance(hours, dict):
        return 0
    return sum(1 for day in DAYS if hours.get(day))


def _minutes(hhmm: str) -> int:
    hh, mm = hhmm.split(":")
    return int(hh) * 60 + int(mm)


def booking_hours_problem(hours: dict | None, slot_minutes: int) -> str:
    """Explain why these hours cannot produce a booking, or '' when they can.

    Checked BEFORE enabling, because the failure it prevents is silent: with every day closed, or
    with a window shorter than one slot, availability returns "no free times" for every date and the
    customer simply concludes the business is fully booked. Nothing raises, so nothing gets fixed.

    The boundary is deliberate: a window exactly one slot long (09:00-09:30 with 30-minute slots)
    yields exactly one bookable time and must be accepted, not rejected as too short.
    """
    if not isinstance(hours, dict) or not open_day_count(hours):
        return (
            "No opening hours are set, so booking would offer no times on any day. "
            "Set at least one opening window before enabling booking."
        )
    slot = max(int(slot_minutes or 0), 1)
    usable = 0
    for day in DAYS:
        for window in hours.get(day) or []:
            try:
                if _minutes(window[1]) - _minutes(window[0]) >= slot:
                    usable += 1
            except (TypeError, ValueError, IndexError):
                continue  # malformed entries are the validator's job; ignore them here
    if not usable:
        return (
            f"No opening window is long enough for a {slot}-minute appointment, so booking could "
            "never offer a time. Widen an opening window or shorten the appointment length."
        )
    return ""


def booking_readiness(tenant: dict) -> dict:
    """Whether this business can really take a booking, and why not when it cannot.

    Reported through `overview` so the owner portal can show the reason BEFORE the owner tries to
    switch booking on. Without this the only feedback was a 400 on submit, which is exactly the
    silent-breakage shape `booking_hours_problem` exists to prevent: an owner who never presses the
    button is never told their hours cannot produce a single appointment.

    `enabled` and `ready` are deliberately separate. A business may have booking switched on from an
    earlier configuration and then have its hours emptied; that state must be visible as
    enabled-but-not-ready rather than silently reported as fine.
    """
    slots = max(int(tenant.get("slot_minutes") or 30), 1)
    problem = booking_hours_problem(tenant.get("business_hours"), slots)
    enabled = bool(tenant.get("native_booking"))
    return {
        "configured": enabled and not problem,
        "enabled": enabled,
        "ready": enabled and not problem,
        "open_days": open_day_count(tenant.get("business_hours")),
        "slot_minutes": slots,
        "reason": problem,
    }


async def set_native_booking(tenant: dict, *, enabled: bool, acknowledgement: bool) -> dict:
    """Turn customer booking on or off for one business, and say whether it can really book.

    Enabling requires acknowledgement AND usable hours. Refusing a broken enable is the whole point:
    the alternative is a tool that advertises availability and then answers "no free times" forever.

    Disabling needs no acknowledgement and is never blocked by bad hours. An owner whose hours are
    misconfigured must still be able to stop taking bookings -- making the stop harder than the start
    would be backwards, exactly as with email replies.
    """
    if enabled and not acknowledgement:
        raise ValueError(
            "Enabling customer booking requires acknowledgement that the business hours and rules "
            "are correct and that the assistant may book appointments"
        )

    problem = booking_hours_problem(tenant.get("business_hours"), tenant.get("slot_minutes") or 30)
    if enabled and problem:
        raise ValueError(problem)

    saved = await tenants.update(tenant["slug"], {"native_booking": bool(enabled)})
    if saved is None:
        raise ValueError("Tenant unavailable")

    ready = bool(enabled) and not problem
    return {
        "native_booking": bool(enabled),
        "enabled": bool(enabled),
        "ready": ready,
        "open_days": open_day_count(tenant.get("business_hours")),
        "slot_minutes": int(tenant.get("slot_minutes") or 30),
        # Reported even when switching OFF, so a broken configuration stays visible.
        "reason": problem if (problem or not enabled) else "",
    }
