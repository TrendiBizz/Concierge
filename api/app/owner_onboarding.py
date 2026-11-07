"""Tenant-scoped owner onboarding profile and safe channel visibility.

Configuration is NOT proof that an external provider works. This module does not
connect accounts, send messages, modify phone routing or enable a channel.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from . import db, tenants
from .config import get_settings


class OwnerBusinessProfile(BaseModel):
    greeting: str | None = Field(default=None, max_length=500)
    notify_email: str | None = Field(default=None, max_length=254)
    timezone: str | None = Field(default=None, max_length=100)

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


async def overview(tenant_id) -> dict:
    tenant = await tenants.get_by_id(tenant_id)
    if tenant is None:
        raise ValueError("Tenant unavailable")
    numbers = await db.pool().fetch(
        "SELECT e164,enabled FROM phone_numbers WHERE tenant_id=$1 ORDER BY e164",
        tenant_id,
    )
    settings = get_settings()
    return {
        "business": {
            "name": tenant["name"],
            "site_url": tenant.get("site_url") or "",
            "greeting": tenant.get("greeting") or "",
            "notify_email": tenant.get("notify_email") or "",
            "timezone": tenant.get("timezone") or "Pacific/Auckland",
        },
        "channels": {
            "website_chat": {"configured": bool(tenant.get("site_url")), "verified": False},
            "telephone": {
                "configured": bool(tenant.get("phone_enabled") and any(r["enabled"] for r in numbers)),
                "registered_numbers": len(numbers), "verified": False,
            },
            "website_voice": {"configured": bool(tenant.get("voice_enabled")), "verified": False},
            "email": {"configured": bool(tenant.get("notify_email") and settings.email_configured),
                      "verified": False},
            "sms": {"configured": bool(tenant.get("sms_enabled") and settings.sms_configured),
                    "verified": False},
            "social": {"configured": bool(settings.social_service_enabled), "verified": False},
            "crm": {"configured": bool(tenant.get("lead_webhook_url") or
                                     (settings.twenty_bridge_url and
                                      tenant.get("slug") == settings.twenty_bridge_tenant_slug)),
                    "verified": False},
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
        "greeting": saved.get("greeting") or "",
        "notify_email": saved.get("notify_email") or "",
        "timezone": saved.get("timezone") or "Pacific/Auckland",
    }
