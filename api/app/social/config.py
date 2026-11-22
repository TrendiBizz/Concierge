"""Configuration helpers for the unified Concierge social module.

Reads existing SOCIAL_* and META_* settings cleanly (falling back to os.environ so
existing env files continue working without breaking) and validates callback URLs.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..config import get_settings

CALLBACK_PATH = "/owner/social/oauth/callback"

ALL_NETWORKS = (
    "facebook",
    "instagram",
    "linkedin",
    "linkedin_organization",
    "x",
    "tiktok",
    "google_business",
)


def _env_or_setting(setting_name: str, env_name: str, default: str = "") -> str:
    s = get_settings()
    val = getattr(s, setting_name, "")
    if isinstance(val, str) and val.strip():
        return val.strip()
    env_val = os.environ.get(env_name, "")
    if env_val.strip():
        return env_val.strip()
    return default


def _bool_env_or_setting(setting_name: str, env_name: str) -> bool:
    s = get_settings()
    val = getattr(s, setting_name, None)
    if isinstance(val, bool) and val:
        return True
    return os.environ.get(env_name, "").strip().lower() in ("1", "true", "yes", "on")


def is_social_enabled() -> bool:
    s = get_settings()
    return bool(getattr(s, "social_service_enabled", False) or getattr(s, "social_enabled", False))


def is_live_publishing_enabled() -> bool:
    if not is_social_enabled():
        return False
    return bool(
        _bool_env_or_setting("social_live_publishing", "SOCIAL_LIVE_PUBLISHING")
        or _bool_env_or_setting("social_enable_publish", "SOCIAL_ENABLE_PUBLISH")
    )


def is_network_publish_enabled(network: str) -> bool:
    if not is_live_publishing_enabled():
        return False
    mapping = {
        "facebook": ("social_enable_facebook_publish", "SOCIAL_ENABLE_FACEBOOK_PUBLISH"),
        "instagram": ("social_enable_instagram_publish", "SOCIAL_ENABLE_INSTAGRAM_PUBLISH"),
        "linkedin": ("social_enable_linkedin_publish", "SOCIAL_ENABLE_LINKEDIN_PUBLISH"),
        "linkedin_organization": (
            "social_enable_linkedin_organization_publish",
            "SOCIAL_ENABLE_LINKEDIN_ORGANIZATION_PUBLISH",
        ),
        "x": ("social_enable_x_publish", "SOCIAL_ENABLE_X_PUBLISH"),
        "tiktok": ("social_enable_tiktok_publish", "SOCIAL_ENABLE_TIKTOK_PUBLISH"),
        "google_business": (
            "social_enable_google_business_publish",
            "SOCIAL_ENABLE_GOOGLE_BUSINESS_PUBLISH",
        ),
    }
    pair = mapping.get(network)
    if not pair:
        return False
    return _bool_env_or_setting(pair[0], pair[1])


def meta_graph_version() -> str:
    """Single canonical Meta Graph API version used by both Social and Meta Messaging."""
    for setting_name, env_name in (
        ("meta_graph_version", "META_GRAPH_VERSION"),
        ("social_meta_graph_version", "SOCIAL_META_GRAPH_VERSION"),
    ):
        val = _env_or_setting(setting_name, env_name, "")
        if val and val.startswith("v") and len(val) >= 3:
            # Guard against fictional/invalid future versions (e.g. legacy v27.0)
            try:
                major = int(val[1:].split(".", 1)[0])
                if 18 <= major <= 24:
                    return val
            except ValueError:
                pass
    return "v22.0"


def linkedin_api_version() -> str:
    ver = _env_or_setting("social_linkedin_api_version", "SOCIAL_LINKEDIN_API_VERSION", "202605")
    if len(ver) == 6 and ver.isdigit() and 1 <= int(ver[4:]) <= 12:
        return ver
    return "202605"


def instagram_login_mode() -> str:
    mode = _env_or_setting("social_instagram_login_mode", "SOCIAL_INSTAGRAM_LOGIN_MODE", "facebook").lower()
    return "instagram" if mode == "instagram" else "facebook"


def default_callback_url() -> str:
    base = (get_settings().public_base_url or "https://concierge.trendibizz.com").strip().rstrip("/")
    return f"{base}{CALLBACK_PATH}"


def validated_callback(raw: str) -> str | None:
    url_str = (raw or "").strip() or default_callback_url()
    parsed = urlsplit(url_str)
    local_http = parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1")
    if (
        (parsed.scheme != "https" and not local_http)
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path != CALLBACK_PATH
    ):
        return None
    return url_str


@dataclass(frozen=True)
class OAuthProviderConfig:
    network: str
    client_id: str
    client_secret: str
    callback: str
    extra: str = ""


def facebook_config() -> OAuthProviderConfig | None:
    cid = _env_or_setting("social_facebook_client_id", "SOCIAL_FACEBOOK_CLIENT_ID") or _env_or_setting(
        "meta_app_id", "META_APP_ID"
    )
    sec = _env_or_setting("social_facebook_client_secret", "SOCIAL_FACEBOOK_CLIENT_SECRET") or _env_or_setting(
        "meta_app_secret", "META_APP_SECRET"
    )
    cb = validated_callback(_env_or_setting("social_facebook_callback", "SOCIAL_FACEBOOK_CALLBACK"))
    if not cid or not sec or not cb:
        return None
    return OAuthProviderConfig("facebook", cid, sec, cb)


def instagram_config() -> OAuthProviderConfig | None:
    mode = instagram_login_mode()
    if mode == "instagram":
        cid = _env_or_setting("social_instagram_client_id", "SOCIAL_INSTAGRAM_CLIENT_ID")
        sec = _env_or_setting("social_instagram_client_secret", "SOCIAL_INSTAGRAM_CLIENT_SECRET")
        cb = validated_callback(_env_or_setting("social_instagram_callback", "SOCIAL_INSTAGRAM_CALLBACK"))
    else:
        fb = facebook_config()
        if not fb:
            return None
        return OAuthProviderConfig("instagram", fb.client_id, fb.client_secret, fb.callback, extra="facebook")
    if not cid or not sec or not cb:
        return None
    return OAuthProviderConfig("instagram", cid, sec, cb, extra="instagram")


def linkedin_config() -> OAuthProviderConfig | None:
    cid = _env_or_setting("social_linkedin_client_id", "SOCIAL_LINKEDIN_CLIENT_ID")
    sec = _env_or_setting("social_linkedin_client_secret", "SOCIAL_LINKEDIN_CLIENT_SECRET")
    cb = validated_callback(_env_or_setting("social_linkedin_callback", "SOCIAL_LINKEDIN_CALLBACK"))
    if not cid or not sec or not cb:
        return None
    return OAuthProviderConfig("linkedin", cid, sec, cb)


def linkedin_organization_config() -> OAuthProviderConfig | None:
    cid = _env_or_setting("social_linkedin_organization_client_id", "SOCIAL_LINKEDIN_ORGANIZATION_CLIENT_ID")
    sec = _env_or_setting("social_linkedin_organization_client_secret", "SOCIAL_LINKEDIN_ORGANIZATION_CLIENT_SECRET")
    cb = validated_callback(
        _env_or_setting("social_linkedin_organization_callback", "SOCIAL_LINKEDIN_ORGANIZATION_CALLBACK")
    )
    if not cid or not sec or not cb:
        return None
    return OAuthProviderConfig("linkedin_organization", cid, sec, cb)


def x_config() -> OAuthProviderConfig | None:
    cid = _env_or_setting("social_x_client_id", "SOCIAL_X_CLIENT_ID")
    sec = _env_or_setting("social_x_client_secret", "SOCIAL_X_CLIENT_SECRET")
    cb = validated_callback(_env_or_setting("social_x_callback", "SOCIAL_X_CALLBACK"))
    if not cid or not sec or not cb:
        return None
    return OAuthProviderConfig("x", cid, sec, cb)


def tiktok_config() -> OAuthProviderConfig | None:
    cid = _env_or_setting("social_tiktok_client_key", "SOCIAL_TIKTOK_CLIENT_KEY")
    sec = _env_or_setting("social_tiktok_client_secret", "SOCIAL_TIKTOK_CLIENT_SECRET")
    cb = validated_callback(_env_or_setting("social_tiktok_callback", "SOCIAL_TIKTOK_CALLBACK"))
    if not cid or not sec or not cb:
        return None
    return OAuthProviderConfig("tiktok", cid, sec, cb)


def google_business_config() -> OAuthProviderConfig | None:
    cid = _env_or_setting("social_google_client_id", "SOCIAL_GOOGLE_CLIENT_ID")
    sec = _env_or_setting("social_google_client_secret", "SOCIAL_GOOGLE_CLIENT_SECRET")
    cb = validated_callback(_env_or_setting("social_google_callback", "SOCIAL_GOOGLE_CALLBACK"))
    if not cid or not sec or not cb:
        return None
    return OAuthProviderConfig("google_business", cid, sec, cb)


def provider_config(network: str) -> OAuthProviderConfig | None:
    dispatch = {
        "facebook": facebook_config,
        "instagram": instagram_config,
        "linkedin": linkedin_config,
        "linkedin_organization": linkedin_organization_config,
        "x": x_config,
        "tiktok": tiktok_config,
        "google_business": google_business_config,
    }
    fn = dispatch.get(network)
    return fn() if fn else None


def provider_status() -> dict[str, bool]:
    return {net: provider_config(net) is not None for net in ALL_NETWORKS}


def publish_status() -> dict[str, bool]:
    return {net: is_network_publish_enabled(net) for net in ALL_NETWORKS}


def facebook_page_hints() -> list[str]:
    raw = _env_or_setting("social_facebook_page_hints", "SOCIAL_FACEBOOK_PAGE_HINTS")
    return [part.strip() for part in raw.split(",") if part.strip().isdigit()]


def tiktok_video_scope_enabled() -> bool:
    return _bool_env_or_setting("social_tiktok_enable_video_scope", "SOCIAL_TIKTOK_ENABLE_VIDEO_SCOPE")


def tiktok_verified_media_origins() -> list[str]:
    raw = _env_or_setting("social_tiktok_verified_media_origins", "SOCIAL_TIKTOK_VERIFIED_MEDIA_ORIGINS")
    return [p.strip().rstrip("/") for p in raw.split(",") if p.strip().startswith("https://")]


def social_media_dir() -> str:
    custom = _env_or_setting("social_media_dir", "SOCIAL_MEDIA_DIR")
    if custom:
        return custom
    base = (get_settings().media_dir or "/data/media").rstrip("/")
    return f"{base}/social"
