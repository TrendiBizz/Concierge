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
            if response.status_code in (400, 409):
                raise HTTPException(409, "Social post cannot be changed in its current state")
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
        await _request("POST", "/v1/customers", {
            "id": slug, "name": tenant["name"],
            "approval_contact": "",  # not inferred from a user's email
        })
    return slug


async def accounts(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await _request("GET", f"/v1/customers/{slug}/accounts")


async def posts(tenant: dict):
    slug = await ensure_tenant(tenant)
    return await _request("GET", f"/v1/customers/{slug}/posts")


async def create_draft(tenant: dict, content: str, account_ids: list[str],
                       link: str = "", hashtags: str = ""):
    slug = await ensure_tenant(tenant)
    if not content.strip() or len(content) > 10000 or not 1 <= len(account_ids) <= 10:
        raise HTTPException(400, "A valid post and one or more accounts are required")
    if any(not POST_ID.fullmatch(a) for a in account_ids):
        raise HTTPException(400, "Invalid account identifier")
    return await _request("POST", f"/v1/customers/{slug}/posts", {
        "content": content, "account_ids": account_ids,
        "link": link, "hashtags": hashtags, "media": [],
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
