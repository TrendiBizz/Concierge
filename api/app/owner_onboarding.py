"""Tenant-scoped owner onboarding profile and safe channel visibility.

Configuration is NOT proof that an external provider works. This module does not
connect accounts, send messages, modify phone routing or enable a channel.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import db, tenants
from .config import get_settings


class OwnerBusinessProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    site_url: str | None = Field(default=None, max_length=2048)
    greeting: str | None = Field(default=None, max_length=500)
    notify_phone: str | None = Field(default=None, max_length=16)
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
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", value):
            raise ValueError("Enter the owner phone in international format, for example +64211234567")
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
    return {
        "business": {
            "name": tenant["name"],
            "site_url": tenant.get("site_url") or "",
            "greeting": tenant.get("greeting") or "",
            "notify_phone": tenant.get("notify_phone") or "",
            "notify_email": tenant.get("notify_email") or "",
            "timezone": tenant.get("timezone") or "Pacific/Auckland",
        },
        "channels": {
            **website_channel_status(tenant, settings),
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


async def update_profile(tenant_slug: str, profile: OwnerBusinessProfile) -> dict:
    changed = profile.model_dump(exclude_unset=True, exclude_none=True)
    if not changed:
        raise ValueError("No profile fields provided")
    saved = await tenants.update(tenant_slug, changed)
    if saved is None:
        raise ValueError("Tenant unavailable")
    return {
        "name": saved["name"],
        "site_url": saved.get("site_url") or "",
        "greeting": saved.get("greeting") or "",
        "notify_phone": saved.get("notify_phone") or "",
        "notify_email": saved.get("notify_email") or "",
        "timezone": saved.get("timezone") or "Pacific/Auckland",
    }
