"""Cloudflare API authentication.

The account used a Global API Key (`X-Auth-Key` + `X-Auth-Email`) until 2026-11-12:
full account access, no scope, no expiry. It has been replaced by a scoped API token
and rolled in the dashboard, so the global key is dead and this module only speaks
Bearer. There is deliberately no legacy fallback: a half-configured environment must
fail loudly instead of quietly reaching for an unset key.
"""
from .config import Settings


def configured(settings: Settings) -> bool:
    """True when the scoped API token is present."""
    return bool(settings.cloudflare_api_token)


def headers(settings: Settings) -> dict[str, str]:
    """Auth headers for api.cloudflare.com."""
    if not settings.cloudflare_api_token:
        raise RuntimeError("CLOUDFLARE_API_TOKEN is not configured")
    return {"Authorization": f"Bearer {settings.cloudflare_api_token}"}
