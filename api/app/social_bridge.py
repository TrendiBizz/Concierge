"""In-process facade for Concierge's unified social publishing module (`api/app/social`).

Preserves the historical `social_bridge` function signatures so callers and tests work
without any separate HTTP service or sidecar process.
"""
from __future__ import annotations

import re

from fastapi import HTTPException

from . import social

POST_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def _require_enabled() -> None:
    if not social.config.is_social_enabled():
        raise HTTPException(503, "Social publishing is not enabled on this server")


async def ensure_tenant(tenant: dict) -> str:
    _require_enabled()
    slug = str(tenant.get("slug") or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", slug):
        raise HTTPException(400, "Invalid tenant slug")
    return await social.store.ensure_customer(slug, str(tenant.get("name") or slug))


async def provider_status() -> dict:
    return social.config.provider_status()


async def accounts(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await social.store.list_accounts(slug)


async def posts(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await social.store.list_posts(slug)


async def compose(tenant: dict, payload: dict):
    slug = await ensure_tenant(tenant)
    accts = await social.store.list_accounts(slug)
    rules = await social.store.get_rules(slug)
    try:
        return social.guardrails.compose_variants(payload, accts, rules)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


async def create_draft(
    tenant: dict,
    content: str,
    account_ids: list[str],
    link: str = "",
    hashtags: str = "",
    media: list[str] | None = None,
    options: dict | None = None,
):
    slug = await ensure_tenant(tenant)
    if not content.strip() or len(content) > 10000 or not 1 <= len(account_ids) <= 10:
        raise HTTPException(400, "A valid post and one or more accounts are required")
    if any(not POST_ID.fullmatch(a) for a in account_ids):
        raise HTTPException(400, "Invalid account identifier")
    media = media or []
    if len(media) > 10 or any(
        not isinstance(m, str)
        or len(m) > 2048
        or not (m.startswith("https://") or re.fullmatch(r"upload:[A-Za-z0-9_-]{20,128}", m))
        for m in media
    ):
        raise HTTPException(400, "Only HTTPS media URLs are allowed")
    return await social.store.create_draft(
        slug,
        content=content,
        account_ids=account_ids,
        link=link,
        hashtags=hashtags,
        media=media,
        options=options or {},
    )


async def submit_draft(tenant: dict, post_id: str):
    slug = await ensure_tenant(tenant)
    if not POST_ID.fullmatch(post_id):
        raise HTTPException(400, "Invalid post identifier")
    return await social.store.submit_draft(slug, post_id)


async def request_approval(tenant: dict, post_id: str, scheduled_at: int):
    slug = await ensure_tenant(tenant)
    if not POST_ID.fullmatch(post_id):
        raise HTTPException(400, "Invalid post identifier")
    return await social.store.request_approval(slug, post_id, scheduled_at)


async def decide(tenant: dict, token: str, approve: bool):
    slug = await ensure_tenant(tenant)
    if not POST_ID.fullmatch(token):
        raise HTTPException(400, "Invalid approval token")
    return await social.store.decide_approval(slug, token, approve)


async def renew_social_token(tenant: dict, account_id: str):
    if not POST_ID.fullmatch(account_id):
        raise HTTPException(400, "Invalid social account")
    slug = await ensure_tenant(tenant)
    return await social.oauth.refresh_account_token(slug, account_id)


async def start_tiktok_oauth(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await social.oauth.start_oauth(slug, "tiktok")


async def finish_tiktok_oauth(tenant: dict, state: str, code: str):
    slug = await ensure_tenant(tenant)
    return await social.oauth.finish_oauth(slug, "tiktok", state, code)


async def disconnect_tiktok(tenant: dict, account_id: str):
    if not POST_ID.fullmatch(account_id):
        raise HTTPException(400, "Invalid account identifier")
    slug = await ensure_tenant(tenant)
    return await social.oauth.disconnect_account(slug, account_id, expected_network="tiktok")


async def start_google_oauth(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await social.oauth.start_oauth(slug, "google_business")


async def finish_google_oauth(tenant: dict, state: str, code: str):
    slug = await ensure_tenant(tenant)
    return await social.oauth.finish_oauth(slug, "google_business", state, code)


async def disconnect_google(tenant: dict, account_id: str):
    if not POST_ID.fullmatch(account_id):
        raise HTTPException(400, "Invalid account identifier")
    slug = await ensure_tenant(tenant)
    return await social.oauth.disconnect_account(slug, account_id, expected_network="google_business")


async def start_x_oauth(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await social.oauth.start_oauth(slug, "x")


async def finish_x_oauth(tenant: dict, state: str, code: str):
    slug = await ensure_tenant(tenant)
    return await social.oauth.finish_oauth(slug, "x", state, code)


async def disconnect_x(tenant: dict, account_id: str):
    if not POST_ID.fullmatch(account_id):
        raise HTTPException(400, "Invalid account identifier")
    slug = await ensure_tenant(tenant)
    return await social.oauth.disconnect_account(slug, account_id, expected_network="x")


async def start_meta_oauth(tenant: dict, network: str):
    if network not in ("facebook", "instagram"):
        raise HTTPException(400, "Unsupported social network")
    slug = await ensure_tenant(tenant)
    return await social.oauth.start_oauth(slug, network)


async def finish_meta_oauth(tenant: dict, network: str, state: str, code: str):
    if network not in ("facebook", "instagram"):
        raise HTTPException(400, "Unsupported social network")
    slug = await ensure_tenant(tenant)
    return await social.oauth.finish_oauth(slug, network, state, code)


async def unlink_meta(tenant: dict, network: str, account_id: str):
    if network not in ("facebook", "instagram") or not POST_ID.fullmatch(account_id):
        raise HTTPException(400, "Invalid social account")
    slug = await ensure_tenant(tenant)
    return await social.oauth.disconnect_account(slug, account_id, expected_network=network)


async def list_meta_pages(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await social.meta_review.list_meta_pages(slug)


async def select_meta_page(tenant: dict, page_id: str, include_instagram: bool = True):
    slug = await ensure_tenant(tenant)
    return await social.meta_review.select_meta_page(slug, page_id, include_instagram=include_instagram)


async def list_meta_businesses(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await social.meta_review.list_meta_businesses(slug)


async def link_meta_page_to_business(tenant: dict, business_id: str, page_id: str, relation: str = "owned"):
    slug = await ensure_tenant(tenant)
    return await social.meta_review.link_page_to_business(
        slug, business_id=business_id, page_id=page_id, relation=relation
    )


async def get_meta_page_activity(tenant: dict, account_id: str, limit: int = 10):
    if not POST_ID.fullmatch(account_id):
        raise HTTPException(400, "Invalid account identifier")
    slug = await ensure_tenant(tenant)
    return await social.meta_review.get_page_activity(slug, account_id, limit=limit)


async def publish_now(tenant: dict, post_id: str):
    if not POST_ID.fullmatch(post_id):
        raise HTTPException(400, "Invalid post identifier")
    slug = await ensure_tenant(tenant)
    return await social.scheduler.publish_post_now(slug, post_id)


async def start_linkedin_oauth(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await social.oauth.start_oauth(slug, "linkedin")


async def finish_linkedin_oauth(tenant: dict, state: str, code: str):
    slug = await ensure_tenant(tenant)
    return await social.oauth.finish_oauth(slug, "linkedin", state, code)


async def unlink_linkedin(tenant: dict, account_id: str):
    if not POST_ID.fullmatch(account_id):
        raise HTTPException(400, "Invalid account identifier")
    slug = await ensure_tenant(tenant)
    return await social.oauth.disconnect_account(slug, account_id, expected_network="linkedin")


async def start_linkedin_organization_oauth(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await social.oauth.start_oauth(slug, "linkedin_organization")


async def finish_linkedin_organization_oauth(tenant: dict, state: str, code: str):
    slug = await ensure_tenant(tenant)
    return await social.oauth.finish_oauth(slug, "linkedin_organization", state, code)
