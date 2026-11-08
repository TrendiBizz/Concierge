"""Concierge owner's tenant-scoped bridge to the independent Rust social service.

Disabled by default. Customer browsers never see social-service keys. No social
network access tokens, passwords or approval secrets are stored in this module.
"""
from urllib.parse import urlsplit
import re

import httpx
from fastapi import HTTPException

from .config import get_settings

POST_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def _configuration() -> tuple[str, str]:
    s = get_settings()
    if not s.social_service_enabled:
        raise HTTPException(503, "Social service is not enabled")
    if not s.social_concierge_key or len(s.social_concierge_key) < 32:
        raise HTTPException(503, "Social service credentials are not configured")
    base = s.social_service_url.rstrip("/")
    url = urlsplit(base)
    # The backend is always a private operator-controlled service. Do not accept
    # arbitrary tenant-configured URLs or public hostnames as backend targets.
    if (url.scheme != "http"
            or url.hostname not in ("127.0.0.1", "localhost", "host.docker.internal")
            or url.port != 4390 or url.path or url.query or url.fragment
            or url.username or url.password):
        raise HTTPException(503, "Social service address is not an approved internal endpoint")
    return base, s.social_concierge_key


async def _request(method: str, path: str, data: dict | None = None):
    base, key = _configuration()
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            response = await client.request(method, base + path,
                headers={"Authorization": "Bearer " + key,
                         "Accept": "application/json"},
                json=data)
        if response.status_code >= 300:
            if response.status_code == 404:
                raise HTTPException(404, "Social resource not found")
            if response.status_code == 400 and "/oauth/meta/" in path:
                # Rust only returns audited, static errors for expected Meta
                # provider failures. Do not forward arbitrary untrusted text.
                safe = {
                    "Facebook authorization rejected",
                    "Facebook long-lived token rejected",
                    "Facebook permissions not verified",
                    "Facebook Page permissions not granted",
                    "Facebook Page lookup rejected",
                    "No authorized Facebook Pages found",
                    "Facebook Page lacks content management access",
                    "Meta authorization rejected",
                    "Meta long-lived token rejected",
                    "Meta permission lookup rejected",
                    "Instagram Graph API permissions not granted",
                    "Meta connected Pages rejected",
                    "No linked professional Instagram account found",
                    "No authorized Facebook Pages returned for Instagram",
                    "Meta business Page discovery unavailable",
                    "Meta business Page discovery invalid",
                    "Meta business Page pagination requires review",
                    "Meta returned Page without usable Page access token",
                    "Meta denied access to selected business Page",
                    "Meta business_management permission missing for Page discovery",
                    "Instagram Page link query unavailable",
                    "Instagram Page link response invalid",
                    "Instagram Page link identity mismatch",
                    "Facebook Pages lack Instagram management permissions",
                    "Facebook Page returned without accessible Instagram professional link",
                    "Instagram professional identity lookup unavailable",
                    "Instagram professional identity mismatch",
                    "Instagram professional identity not verified",
                    "Instagram professional identity response invalid",
                    "Linked Instagram account is not a verified professional account",
                    "Meta access token missing",
                    "Meta token validation failed",
                    "Meta token belongs to another application",
                    "Meta token is expired",
                    "Meta token has invalid expiry",
                    "Too many selected Facebook Pages for safe discovery",
                    "Linked Instagram Page lacks content management access",
                    "Facebook account has too many Pages; pagination not yet supported",
                    "Meta Page pagination requires operator review",
                    "OAuth state expired or invalid",
                    "Facebook authorization unavailable",
                    "Facebook token invalid",
                    "Facebook token missing",
                    "Facebook long-lived token unavailable",
                    "Facebook long-lived token invalid",
                    "Facebook long-lived token missing expiry",
                    "Facebook permission check unavailable",
                    "Facebook permission response invalid",
                    "Facebook Page lookup unavailable",
                    "Facebook Page list invalid",
                    "Meta authorization unavailable",
                    "Invalid Meta token",
                    "Meta token missing",
                    "Meta long-lived exchange unavailable",
                    "Invalid Meta long-lived token",
                    "Meta token missing expiry",
                    "Meta permissions unavailable",
                    "Meta permission response invalid",
                    "Meta connected Pages lookup unavailable",
                    "Invalid Meta Pages response",
                    "Meta Page pagination requires operator review",
                    "Instagram authorization unavailable",
                    "Instagram authorization rejected",
                    "Invalid Instagram token response",
                    "Instagram access token missing",
                    "Instagram long-lived exchange unavailable",
                    "Instagram long-lived token rejected",
                    "Instagram long-lived token invalid",
                    "Instagram long-lived token missing expiry",
                    "Instagram profile unavailable",
                    "Instagram identity not verified",
                    "Invalid Instagram profile",
                }
                try:
                    message = response.json().get("error")
                except (ValueError, AttributeError):
                    message = None
                raise HTTPException(400, message if message in safe
                                    else "Meta authorization could not be completed")
            if response.status_code == 400 and "/oauth/linkedin/" in path:
                # Forward only audited errors authored by our Rust connector.
                # Never expose LinkedIn's raw response, tokens or codes.
                safe_linkedin = {
                    "LinkedIn authorization was rejected",
                    "Invalid LinkedIn OAuth token response",
                    "Invalid LinkedIn OAuth token expiry",
                    "LinkedIn did not grant the requested permissions",
                    "LinkedIn profile lookup unavailable",
                    "LinkedIn profile verification failed",
                    "Invalid LinkedIn profile",
                    "LinkedIn profile missing identity",
                    "OAuth state expired or invalid",
                    "LinkedIn authorization unavailable",
                    "LinkedIn account storage failed",
                    "LinkedIn credential encryption failed",
                }
                try:
                    message = response.json().get("error")
                except (ValueError, AttributeError):
                    message = None
                raise HTTPException(400, message if message in safe_linkedin
                                    else "LinkedIn authorization could not be completed")
            if response.status_code == 400:
                raise HTTPException(400, "Social request could not be completed")
            if response.status_code == 409:
                raise HTTPException(409, "Social action conflicts with its current state")
            raise HTTPException(502, "Social service rejected request")
        return response.json()
    except httpx.HTTPError:
        raise HTTPException(503, "Social service unavailable")


async def ensure_tenant(tenant: dict) -> str:
    slug = tenant["slug"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", slug):
        raise HTTPException(400, "Invalid tenant slug")
    try:
        await _request("GET", f"/v1/customers/{slug}/rules")
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        try:
            await _request("POST", "/v1/customers", {
                "id": slug, "name": tenant["name"],
                "approval_contact": "",  # not inferred from a user's email
            })
        except HTTPException as create_exc:
            if create_exc.status_code not in (400, 409):
                raise
            # Parallel requests for posts and accounts can race to provision a
            # new business. Treat the conflict as success ONLY if the exact
            # authenticated tenant now exists. Never accept a bare conflict.
            await _request("GET", f"/v1/customers/{slug}/rules")
    return slug


async def provider_status() -> dict:
    return await _request("GET", "/v1/oauth/providers")


async def accounts(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await _request("GET", f"/v1/customers/{slug}/accounts")


async def posts(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await _request("GET", f"/v1/customers/{slug}/posts")


async def create_draft(tenant: dict, content: str, account_ids: list[str],
                       link: str = "", hashtags: str = "", media: list[str] | None = None):
    slug = await ensure_tenant(tenant)
    if not content.strip() or len(content) > 10000 or not 1 <= len(account_ids) <= 10:
        raise HTTPException(400, "A valid post and one or more accounts are required")
    if any(not POST_ID.fullmatch(a) for a in account_ids):
        raise HTTPException(400, "Invalid account identifier")
    media = media or []
    if len(media) > 10 or any(not isinstance(m, str) or len(m) > 2048
                              or not m.startswith("https://") for m in media):
        raise HTTPException(400, "Only HTTPS media URLs are allowed")
    return await _request("POST", f"/v1/customers/{slug}/posts", {
        "content": content, "account_ids": account_ids,
        "link": link, "hashtags": hashtags, "media": media,
    })


async def submit_draft(tenant: dict, post_id: str):
    slug = await ensure_tenant(tenant)
    if not POST_ID.fullmatch(post_id):
        raise HTTPException(400, "Invalid post identifier")
    return await _request("POST", f"/v1/customers/{slug}/posts/{post_id}/submit")


async def request_approval(tenant: dict, post_id: str, scheduled_at: int):
    slug = await ensure_tenant(tenant)
    if not POST_ID.fullmatch(post_id):
        raise HTTPException(400, "Invalid post identifier")
    return await _request("POST",
        f"/v1/customers/{slug}/posts/{post_id}/approval-request",
        {"scheduled_at": scheduled_at})


async def decide(tenant: dict, token: str, approve: bool):
    slug = await ensure_tenant(tenant)
    if not POST_ID.fullmatch(token):
        raise HTTPException(400, "Invalid approval token")
    return await _request("POST",
        f"/v1/customers/{slug}/approvals/{token}/"
        + ("approve" if approve else "reject"))


async def start_tiktok_oauth(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await _request("POST", f"/v1/customers/{slug}/oauth/tiktok/start")


async def finish_tiktok_oauth(tenant: dict, state: str, code: str):
    if not POST_ID.fullmatch(state) or not code or len(code) > 2048:
        raise HTTPException(400, "Invalid OAuth callback")
    slug = await ensure_tenant(tenant)
    return await _request("POST", f"/v1/customers/{slug}/oauth/tiktok/finish",
                          {"state": state, "code": code})


async def disconnect_tiktok(tenant: dict, account_id: str):
    if not POST_ID.fullmatch(account_id):
        raise HTTPException(400, "Invalid account identifier")
    slug = await ensure_tenant(tenant)
    return await _request("DELETE",
                          f"/v1/customers/{slug}/oauth/tiktok/accounts/{account_id}")


async def start_google_oauth(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await _request("POST", f"/v1/customers/{slug}/oauth/google/start")


async def finish_google_oauth(tenant: dict, state: str, code: str):
    if not POST_ID.fullmatch(state) or not code or len(code) > 2048:
        raise HTTPException(400, "Invalid OAuth callback")
    slug = await ensure_tenant(tenant)
    return await _request("POST", f"/v1/customers/{slug}/oauth/google/finish", {"state": state, "code": code})


async def disconnect_google(tenant: dict, account_id: str):
    if not POST_ID.fullmatch(account_id):
        raise HTTPException(400, "Invalid account identifier")
    slug = await ensure_tenant(tenant)
    return await _request("DELETE", f"/v1/customers/{slug}/oauth/google/accounts/{account_id}")


async def renew_social_token(tenant: dict, account_id: str):
    if not POST_ID.fullmatch(account_id):
        raise HTTPException(400, "Invalid social account")
    slug = await ensure_tenant(tenant)
    return await _request("POST", f"/v1/customers/{slug}/oauth/renew/{account_id}")


async def start_meta_oauth(tenant: dict, network: str):
    if network not in ("facebook", "instagram"):
        raise HTTPException(400, "Unsupported social network")
    slug = await ensure_tenant(tenant)
    return await _request("POST", f"/v1/customers/{slug}/oauth/meta/{network}/start")


async def finish_meta_oauth(tenant: dict, network: str, state: str, code: str):
    if network not in ("facebook", "instagram"):
        raise HTTPException(400, "Unsupported social network")
    if not POST_ID.fullmatch(state) or not code or len(code) > 2048:
        raise HTTPException(400, "Invalid OAuth callback")
    slug = await ensure_tenant(tenant)
    return await _request("POST", f"/v1/customers/{slug}/oauth/meta/{network}/finish",
                          {"state": state, "code": code})


async def unlink_meta(tenant: dict, network: str, account_id: str):
    if network not in ("facebook", "instagram") or not POST_ID.fullmatch(account_id):
        raise HTTPException(400, "Invalid social account")
    slug = await ensure_tenant(tenant)
    return await _request("DELETE", f"/v1/customers/{slug}/oauth/meta/{network}/accounts/{account_id}")


async def start_mastodon_oauth(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await _request("POST", f"/v1/customers/{slug}/oauth/mastodon/start")


async def finish_mastodon_oauth(tenant: dict, state: str, code: str):
    slug = await ensure_tenant(tenant)
    if not POST_ID.fullmatch(state) or not code or len(code) > 2048:
        raise HTTPException(400, "Invalid OAuth callback")
    return await _request("POST", f"/v1/customers/{slug}/oauth/mastodon/finish",
                          {"state": state, "code": code})


async def disconnect_mastodon(tenant: dict, account_id: str):
    slug = await ensure_tenant(tenant)
    if not POST_ID.fullmatch(account_id):
        raise HTTPException(400, "Invalid account identifier")
    return await _request("DELETE",
        f"/v1/customers/{slug}/oauth/mastodon/accounts/{account_id}")


async def start_linkedin_oauth(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await _request("POST", f"/v1/customers/{slug}/oauth/linkedin/start")


async def finish_linkedin_oauth(tenant: dict, state: str, code: str):
    slug = await ensure_tenant(tenant)
    if not POST_ID.fullmatch(state) or not code or len(code) > 2048:
        raise HTTPException(400, "Invalid OAuth callback")
    return await _request("POST", f"/v1/customers/{slug}/oauth/linkedin/finish",
                          {"state": state, "code": code})


async def unlink_linkedin(tenant: dict, account_id: str):
    slug = await ensure_tenant(tenant)
    if not POST_ID.fullmatch(account_id):
        raise HTTPException(400, "Invalid account identifier")
    return await _request("DELETE",
        f"/v1/customers/{slug}/oauth/linkedin/accounts/{account_id}")
