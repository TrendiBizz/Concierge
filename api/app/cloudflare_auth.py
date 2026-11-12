"""Cloudflare API authentication headers.

The account was using a Global API Key (`X-Auth-Key` + `X-Auth-Email`). A global
key is full account access with no scope and no expiry, so the services now
prefer a scoped API token (`CLOUDFLARE_API_TOKEN`) sent as a Bearer credential.
The legacy key headers remain as a fallback so a deploy that lands before the
env file is updated keeps working; once the token is live and the global key is
rolled in the dashboard the fallback is dead code and can be deleted.
"""
from .config import Settings


def configured(settings: Settings) -> bool:
    """True when some Cloudflare credential is present."""
    return bool(settings.cloudflare_api_token or settings.cloudflare_api_key)


def headers(settings: Settings) -> dict[str, str]:
    """Auth headers for api.cloudflare.com; token wins over the global key."""
    if settings.cloudflare_api_token:
        return {"Authorization": f"Bearer {settings.cloudflare_api_token}"}
    return {
        "X-Auth-Email": settings.cloudflare_email,
        "X-Auth-Key": settings.cloudflare_api_key,
    }
