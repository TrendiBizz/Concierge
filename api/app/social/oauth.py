"""Modernised OAuth 2.0 (+ PKCE) connection, token renewal, and disconnect for all 7 networks.

Networks:
- facebook (Meta Graph API v22.0, Pages + Messenger/IG webhook sync)
- instagram (Meta Graph API v22.0 via Facebook Pages or Instagram Business Login)
- linkedin (OIDC + w_member_social, REST API versioned)
- linkedin_organization (Company Pages via organizationAcls)
- x (OAuth 2.0 PKCE S256, API v2, offline.access)
- tiktok (OAuth 2.0 PKCE S256, Open API v2)
- google_business (OAuth 2.0 PKCE S256, Google Business Profile API)
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from . import config as social_config
from . import store

# ---- Scopes ---------------------------------------------------------------------------------
FB_SCOPES = (
    "pages_show_list,pages_manage_posts,pages_read_engagement,"
    "pages_messaging,pages_manage_metadata,business_management"
)
IG_FACEBOOK_SCOPES = (
    "pages_show_list,pages_read_engagement,pages_messaging,pages_manage_metadata,"
    "instagram_basic,instagram_content_publish,instagram_manage_messages,business_management"
)
IG_DIRECT_SCOPES = "instagram_business_basic,instagram_business_content_publish"
META_WEBHOOK_FIELDS = "messages,messaging_postbacks"

LINKEDIN_SCOPES = "openid profile email w_member_social"
LINKEDIN_ORG_SCOPES = "r_organization_social w_organization_social rw_organization_admin"
X_SCOPES = "tweet.read tweet.write users.read offline.access"
GOOGLE_SCOPES = "https://www.googleapis.com/auth/business.manage"
TIKTOK_BASE_SCOPE = "user.info.basic"
TIKTOK_VIDEO_SCOPE = "user.info.basic,video.publish"


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _normalize_scopes(raw: str) -> str:
    parts = [p.strip() for p in (raw or "").replace(",", " ").split() if p.strip()]
    return " ".join(sorted(set(parts)))


async def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    auth: tuple[str, str] | None = None,
    timeout: float = 15.0,
) -> tuple[int, dict]:
    """Isolated HTTP JSON helper (cleanly mockable in unit tests)."""
    hdrs = {"Accept": "application/json", **(headers or {})}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            resp = await client.request(
                method, url, headers=hdrs, params=params, data=data, json=json_body, auth=auth
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Social provider is temporarily unreachable") from exc
    try:
        body = resp.json()
    except ValueError:
        body = {}
    return resp.status_code, body if isinstance(body, dict) else {}


def _graph_base() -> str:
    return f"https://graph.facebook.com/{social_config.meta_graph_version()}"


# ---- Start OAuth (all 7 networks) -----------------------------------------------------------
async def start_oauth(customer_slug: str, network: str) -> dict:
    cfg = social_config.provider_config(network)
    if not cfg:
        raise HTTPException(503, f"{network.replace('_', ' ').title()} OAuth is not configured on this server")

    state = secrets.token_urlsafe(32)
    verifier, challenge = _pkce_pair()
    await store.oauth_begin(customer_slug, network, state, verifier, ttl_seconds=600)

    if network == "facebook":
        ver = social_config.meta_graph_version()
        params = urlencode({
            "client_id": cfg.client_id,
            "redirect_uri": cfg.callback,
            "state": state,
            "scope": FB_SCOPES,
            "response_type": "code",
            "auth_type": "rerequest",
        })
        auth_url = f"https://www.facebook.com/{ver}/dialog/oauth?{params}"

    elif network == "instagram":
        if cfg.extra == "instagram":
            params = urlencode({
                "client_id": cfg.client_id,
                "redirect_uri": cfg.callback,
                "state": state,
                "scope": IG_DIRECT_SCOPES,
                "response_type": "code",
            })
            auth_url = f"https://www.instagram.com/oauth/authorize?{params}"
        else:
            ver = social_config.meta_graph_version()
            params = urlencode({
                "client_id": cfg.client_id,
                "redirect_uri": cfg.callback,
                "state": state,
                "scope": IG_FACEBOOK_SCOPES,
                "response_type": "code",
                "auth_type": "rerequest",
            })
            auth_url = f"https://www.facebook.com/{ver}/dialog/oauth?{params}"

    elif network == "linkedin":
        params = urlencode({
            "response_type": "code",
            "client_id": cfg.client_id,
            "redirect_uri": cfg.callback,
            "state": state,
            "scope": LINKEDIN_SCOPES,
        })
        auth_url = f"https://www.linkedin.com/oauth/v2/authorization?{params}"

    elif network == "linkedin_organization":
        params = urlencode({
            "response_type": "code",
            "client_id": cfg.client_id,
            "redirect_uri": cfg.callback,
            "state": state,
            "scope": LINKEDIN_ORG_SCOPES,
        })
        auth_url = f"https://www.linkedin.com/oauth/v2/authorization?{params}"

    elif network == "x":
        params = urlencode({
            "response_type": "code",
            "client_id": cfg.client_id,
            "redirect_uri": cfg.callback,
            "scope": X_SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        auth_url = f"https://x.com/i/oauth2/authorize?{params}"

    elif network == "tiktok":
        scope = TIKTOK_VIDEO_SCOPE if social_config.tiktok_video_scope_enabled() else TIKTOK_BASE_SCOPE
        params = urlencode({
            "client_key": cfg.client_id,
            "redirect_uri": cfg.callback,
            "response_type": "code",
            "scope": scope,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        auth_url = f"https://www.tiktok.com/v2/auth/authorize/?{params}"

    elif network == "google_business":
        params = urlencode({
            "client_id": cfg.client_id,
            "redirect_uri": cfg.callback,
            "response_type": "code",
            "scope": GOOGLE_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"

    else:
        raise HTTPException(400, "Unsupported social network")

    return {"authorization_url": auth_url, "state": state}


# ---- Finish OAuth (all 7 networks) ----------------------------------------------------------
async def finish_oauth(customer_slug: str, network: str, state: str, code: str) -> dict:
    if not state or len(state) < 32 or not code or len(code) > 2048:
        raise HTTPException(400, "Invalid OAuth callback")
    cfg = social_config.provider_config(network)
    if not cfg:
        raise HTTPException(503, f"{network.replace('_', ' ').title()} OAuth is not configured on this server")

    verifier = await store.oauth_consume(customer_slug, network, state)

    if network in ("facebook", "instagram"):
        return await _finish_meta(customer_slug, cfg, code)
    if network == "linkedin":
        return await _finish_linkedin(customer_slug, cfg, code)
    if network == "linkedin_organization":
        return await _finish_linkedin_org(customer_slug, cfg, code)
    if network == "x":
        return await _finish_x(customer_slug, cfg, code, verifier)
    if network == "tiktok":
        return await _finish_tiktok(customer_slug, cfg, code, verifier)
    if network == "google_business":
        return await _finish_google_business(customer_slug, cfg, code, verifier)
    raise HTTPException(400, "Unsupported social network")


async def _finish_meta(customer_slug: str, cfg: social_config.OAuthProviderConfig, code: str) -> dict:
    gbase = _graph_base()
    if cfg.network == "instagram" and cfg.extra == "instagram":
        status, tok = await _http_json(
            "POST",
            "https://api.instagram.com/oauth/access_token",
            data={
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret,
                "grant_type": "authorization_code",
                "redirect_uri": cfg.callback,
                "code": code,
            },
        )
        short_tok = str(tok.get("access_token") or "")
        if status >= 300 or not short_tok:
            raise HTTPException(400, "Instagram authorization rejected")
        ll_status, ll = await _http_json(
            "GET",
            "https://graph.instagram.com/access_token",
            params={"grant_type": "ig_exchange_token", "client_secret": cfg.client_secret, "access_token": short_tok},
        )
        access_token = str(ll.get("access_token") or short_tok) if ll_status < 300 else short_tok
        expires_in = int(ll.get("expires_in") or 5184000) if ll_status < 300 else 3600
        p_status, prof = await _http_json(
            "GET",
            "https://graph.instagram.com/me",
            params={"fields": "id,username,account_type", "access_token": access_token},
        )
        ig_id = str(prof.get("id") or "")
        if p_status >= 300 or not ig_id:
            raise HTTPException(400, "Instagram profile unavailable")
        name = str(prof.get("username") or ig_id)
        acct_id = await store.upsert_verified_account(
            customer_slug=customer_slug,
            network="instagram",
            external_id=ig_id,
            display_name=name,
            access_token=access_token,
            expires_at=int(time.time()) + expires_in,
            granted_scopes=IG_DIRECT_SCOPES,
        )
        return {"account_ids": [acct_id], "channels": []}

    # Facebook Login (for Facebook Pages or Facebook-linked Instagram Professional Accounts)
    status, tok = await _http_json(
        "GET",
        f"{gbase}/oauth/access_token",
        params={
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "redirect_uri": cfg.callback,
            "code": code,
        },
    )
    short_tok = str(tok.get("access_token") or "")
    if status >= 300 or not short_tok:
        raise HTTPException(400, "Meta authorization rejected")

    # Exchange for long-lived user token (60 days -> yields non-expiring Page access tokens)
    ll_status, ll = await _http_json(
        "GET",
        f"{gbase}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "fb_exchange_token": short_tok,
        },
    )
    user_token = str(ll.get("access_token") or short_tok) if ll_status < 300 else short_tok

    # Verify token belongs to our Meta app via debug_token
    dbg_status, dbg = await _http_json(
        "GET",
        f"{gbase}/debug_token",
        params={"input_token": user_token, "access_token": f"{cfg.client_id}|{cfg.client_secret}"},
    )
    dbg_data = (dbg.get("data") or {}) if dbg_status < 300 else {}
    if not dbg_data.get("is_valid"):
        raise HTTPException(400, "Meta token validation failed")
    if dbg_data.get("app_id") and str(dbg_data.get("app_id")) != cfg.client_id:
        raise HTTPException(400, "Meta token belongs to another application")
    granted_scopes = _normalize_scopes(" ".join(dbg_data.get("scopes") or []))

    # Fetch authorized Facebook Pages
    pg_status, pg_data = await _http_json(
        "GET",
        f"{gbase}/me/accounts",
        params={"fields": "id,name,access_token,tasks,instagram_business_account{id,username}", "limit": "50"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    if pg_status >= 300:
        raise HTTPException(400, "Facebook Page lookup rejected")
    pages = pg_data.get("data") or []
    if not pages:
        raise HTTPException(400, "No authorized Facebook Pages found")

    account_ids: list[str] = []
    channels: list[dict] = []

    for page in pages:
        page_id = str(page.get("id") or "").strip()
        page_name = str(page.get("name") or page_id).strip()
        page_token = str(page.get("access_token") or "").strip()
        if not page_id or not page_token:
            continue

        if cfg.network == "facebook":
            acct_id = await store.upsert_verified_account(
                customer_slug=customer_slug,
                network="facebook",
                external_id=page_id,
                display_name=page_name,
                access_token=page_token,
                expires_at=None,
                granted_scopes=granted_scopes or FB_SCOPES,
            )
            account_ids.append(acct_id)
            # Best-effort subscribe Page to messaging webhooks
            sub_status, _ = await _http_json(
                "POST",
                f"{gbase}/{page_id}/subscribed_apps",
                params={"subscribed_fields": META_WEBHOOK_FIELDS},
                headers={"Authorization": f"Bearer {page_token}"},
            )
            channels.append({
                "account_id": acct_id,
                "channel": "messenger",
                "external_id": page_id,
                "page_id": page_id,
                "display_name": page_name,
                "access_token": page_token,
                "webhook_subscribed": sub_status < 300,
            })
        else:
            ig = page.get("instagram_business_account") or {}
            ig_id = str(ig.get("id") or "").strip()
            if not ig_id:
                continue
            ig_name = str(ig.get("username") or page_name or ig_id).strip()
            acct_id = await store.upsert_verified_account(
                customer_slug=customer_slug,
                network="instagram",
                external_id=ig_id,
                display_name=ig_name,
                access_token=page_token,
                expires_at=None,
                granted_scopes=granted_scopes or IG_FACEBOOK_SCOPES,
            )
            account_ids.append(acct_id)
            sub_status, _ = await _http_json(
                "POST",
                f"{gbase}/{page_id}/subscribed_apps",
                params={"subscribed_fields": META_WEBHOOK_FIELDS},
                headers={"Authorization": f"Bearer {page_token}"},
            )
            channels.append({
                "account_id": acct_id,
                "channel": "instagram",
                "external_id": ig_id,
                "page_id": page_id,
                "display_name": ig_name,
                "access_token": page_token,
                "webhook_subscribed": sub_status < 300,
            })

    if not account_ids:
        if cfg.network == "instagram":
            raise HTTPException(400, "No linked professional Instagram account found")
        raise HTTPException(400, "No authorized Facebook Pages found")

    return {"account_ids": account_ids, "channels": channels}


async def _finish_linkedin(customer_slug: str, cfg: social_config.OAuthProviderConfig, code: str) -> dict:
    status, tok = await _http_json(
        "POST",
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg.callback,
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
        },
    )
    access_token = str(tok.get("access_token") or "")
    expires_in = int(tok.get("expires_in") or 0)
    if status >= 300 or not access_token or expires_in <= 0:
        raise HTTPException(400, "LinkedIn authorization was rejected")

    u_status, prof = await _http_json(
        "GET",
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    sub = str(prof.get("sub") or "").strip()
    if u_status >= 300 or not sub:
        raise HTTPException(400, "LinkedIn profile verification failed")
    display_name = str(prof.get("name") or prof.get("given_name") or sub).strip()
    scopes = _normalize_scopes(str(tok.get("scope") or LINKEDIN_SCOPES))
    acct_id = await store.upsert_verified_account(
        customer_slug=customer_slug,
        network="linkedin",
        external_id=f"urn:li:person:{sub}" if not sub.startswith("urn:") else sub,
        display_name=display_name,
        access_token=access_token,
        refresh_token=tok.get("refresh_token"),
        expires_at=int(time.time()) + expires_in,
        granted_scopes=scopes,
    )
    return {"account_id": acct_id, "account_ids": [acct_id]}


async def _finish_linkedin_org(customer_slug: str, cfg: social_config.OAuthProviderConfig, code: str) -> dict:
    status, tok = await _http_json(
        "POST",
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg.callback,
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
        },
    )
    access_token = str(tok.get("access_token") or "")
    expires_in = int(tok.get("expires_in") or 0)
    if status >= 300 or not access_token or expires_in <= 0:
        raise HTTPException(400, "LinkedIn authorization was rejected")

    li_ver = social_config.linkedin_api_version()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Linkedin-Version": li_ver,
        "X-Restli-Protocol-Version": "2.0.0",
    }
    a_status, acls = await _http_json(
        "GET",
        "https://api.linkedin.com/rest/organizationAcls",
        params={"q": "roleAssignee", "role": "ADMINISTRATOR", "state": "APPROVED"},
        headers=headers,
    )
    if a_status >= 300:
        raise HTTPException(400, "LinkedIn Company Page lookup failed")

    elements = acls.get("elements") or []
    scopes = _normalize_scopes(str(tok.get("scope") or LINKEDIN_ORG_SCOPES))
    account_ids: list[str] = []
    for el in elements:
        org_urn = str(el.get("organization") or "").strip()
        if not org_urn.startswith("urn:li:organization:"):
            continue
        org_num = org_urn.rsplit(":", 1)[-1]
        o_status, org = await _http_json(
            "GET", f"https://api.linkedin.com/rest/organizations/{org_num}", headers=headers
        )
        name = str(org.get("localizedName") or org_urn) if o_status < 300 else org_urn
        acct_id = await store.upsert_verified_account(
            customer_slug=customer_slug,
            network="linkedin_organization",
            external_id=org_urn,
            display_name=name,
            access_token=access_token,
            refresh_token=tok.get("refresh_token"),
            expires_at=int(time.time()) + expires_in,
            granted_scopes=scopes,
        )
        account_ids.append(acct_id)

    if not account_ids:
        raise HTTPException(400, "No administered LinkedIn Company Pages found")
    return {"account_ids": account_ids}


async def _finish_x(customer_slug: str, cfg: social_config.OAuthProviderConfig, code: str, verifier: str) -> dict:
    status, tok = await _http_json(
        "POST",
        "https://api.x.com/2/oauth2/token",
        auth=(cfg.client_id, cfg.client_secret),
        data={
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": cfg.callback,
            "code_verifier": verifier,
        },
    )
    access_token = str(tok.get("access_token") or "")
    expires_in = int(tok.get("expires_in") or 7200)
    if status >= 300 or not access_token:
        raise HTTPException(400, "X authorization rejected")

    u_status, me = await _http_json(
        "GET",
        "https://api.x.com/2/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    user_data = me.get("data") or {}
    uid = str(user_data.get("id") or "").strip()
    if u_status >= 300 or not uid:
        raise HTTPException(400, "X profile verification failed")
    username = str(user_data.get("username") or user_data.get("name") or uid)
    acct_id = await store.upsert_verified_account(
        customer_slug=customer_slug,
        network="x",
        external_id=uid,
        display_name=f"@{username}" if not username.startswith("@") else username,
        access_token=access_token,
        refresh_token=tok.get("refresh_token"),
        expires_at=int(time.time()) + expires_in,
        granted_scopes=_normalize_scopes(str(tok.get("scope") or X_SCOPES)),
    )
    return {"account_id": acct_id, "account_ids": [acct_id]}


async def _finish_tiktok(customer_slug: str, cfg: social_config.OAuthProviderConfig, code: str, verifier: str) -> dict:
    status, tok = await _http_json(
        "POST",
        "https://open.tiktokapis.com/v2/oauth/token/",
        data={
            "client_key": cfg.client_id,
            "client_secret": cfg.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": cfg.callback,
            "code_verifier": verifier,
        },
    )
    access_token = str(tok.get("access_token") or "")
    expires_in = int(tok.get("expires_in") or 86400)
    if status >= 300 or not access_token:
        raise HTTPException(400, "TikTok authorization rejected")

    u_status, me = await _http_json(
        "GET",
        "https://open.tiktokapis.com/v2/user/info/",
        params={"fields": "open_id,display_name"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    user_data = (me.get("data") or {}).get("user") or {}
    open_id = str(user_data.get("open_id") or tok.get("open_id") or "").strip()
    if u_status >= 300 or not open_id:
        raise HTTPException(400, "TikTok profile verification failed")
    display_name = str(user_data.get("display_name") or open_id).strip()
    acct_id = await store.upsert_verified_account(
        customer_slug=customer_slug,
        network="tiktok",
        external_id=open_id,
        display_name=display_name,
        access_token=access_token,
        refresh_token=tok.get("refresh_token"),
        expires_at=int(time.time()) + expires_in,
        granted_scopes=_normalize_scopes(str(tok.get("scope") or TIKTOK_BASE_SCOPE)),
    )
    return {"account_id": acct_id, "account_ids": [acct_id]}


async def _finish_google_business(
    customer_slug: str, cfg: social_config.OAuthProviderConfig, code: str, verifier: str
) -> dict:
    status, tok = await _http_json(
        "POST",
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "redirect_uri": cfg.callback,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        },
    )
    access_token = str(tok.get("access_token") or "")
    expires_in = int(tok.get("expires_in") or 3600)
    if status >= 300 or not access_token:
        raise HTTPException(400, "Google Business authorization rejected")

    a_status, accts = await _http_json(
        "GET",
        "https://mybusinessaccountmanagement.googleapis.com/v1/accounts",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if a_status >= 300:
        raise HTTPException(400, "Google Business Profile account lookup failed")
    g_accounts = accts.get("accounts") or []
    account_ids: list[str] = []
    for ga in g_accounts:
        acct_name = str(ga.get("name") or "").strip()  # e.g. accounts/123456
        if not acct_name:
            continue
        loc_status, locs = await _http_json(
            "GET",
            f"https://mybusinessbusinessinformation.googleapis.com/v1/{acct_name}/locations",
            params={"readMask": "name,title"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        locations = (locs.get("locations") or []) if loc_status < 300 else []
        if locations:
            for loc in locations:
                loc_name = str(loc.get("name") or "").strip()
                title = str(loc.get("title") or ga.get("accountName") or loc_name).strip()
                ext_id = f"{acct_name}/{loc_name}" if not loc_name.startswith("accounts/") else loc_name
                aid = await store.upsert_verified_account(
                    customer_slug=customer_slug,
                    network="google_business",
                    external_id=ext_id,
                    display_name=title,
                    access_token=access_token,
                    refresh_token=tok.get("refresh_token"),
                    expires_at=int(time.time()) + expires_in,
                    granted_scopes=_normalize_scopes(str(tok.get("scope") or GOOGLE_SCOPES)),
                )
                account_ids.append(aid)
        else:
            aid = await store.upsert_verified_account(
                customer_slug=customer_slug,
                network="google_business",
                external_id=acct_name,
                display_name=str(ga.get("accountName") or acct_name),
                access_token=access_token,
                refresh_token=tok.get("refresh_token"),
                expires_at=int(time.time()) + expires_in,
                granted_scopes=_normalize_scopes(str(tok.get("scope") or GOOGLE_SCOPES)),
            )
            account_ids.append(aid)

    if not account_ids:
        raise HTTPException(400, "No Google Business Profile accounts found")
    return {"account_ids": account_ids}


# ---- Token Refresh (manual + automatic before scheduled publishing) -------------------------
async def refresh_account_token(customer_slug: str, account_id: str, *, force: bool = False) -> dict:
    creds = await store.get_account_credentials(customer_slug, account_id, allow_expired=True)
    network = creds["network"]
    expires_at = creds["expires_at"]
    now = int(time.time())

    if network == "instagram" and social_config.instagram_login_mode() != "instagram":
        raise HTTPException(400, "Facebook-linked Instagram access uses Page permissions; reconnect if revoked")
    if network == "facebook":
        raise HTTPException(400, "Facebook Page tokens do not use refresh tokens; reconnect if revoked")

    if not force and expires_at and expires_at > now + (7 * 86400):
        raise HTTPException(400, "Account token does not need renewal yet")

    cfg = social_config.provider_config(network)
    if not cfg:
        raise HTTPException(503, f"{network.replace('_', ' ').title()} OAuth is not configured")

    if network == "instagram":
        status, tok = await _http_json(
            "GET",
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": creds["access_token"]},
        )
    elif network == "google_business":
        if not creds["refresh_token"]:
            await store.mark_needs_reauth(customer_slug, account_id)
            raise HTTPException(400, "Google Business account needs reauthorization")
        status, tok = await _http_json(
            "POST",
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": creds["refresh_token"],
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret,
            },
        )
    elif network == "x":
        if not creds["refresh_token"]:
            await store.mark_needs_reauth(customer_slug, account_id)
            raise HTTPException(400, "Reconnect X for offline access")
        status, tok = await _http_json(
            "POST",
            "https://api.x.com/2/oauth2/token",
            auth=(cfg.client_id, cfg.client_secret),
            data={"grant_type": "refresh_token", "refresh_token": creds["refresh_token"]},
        )
    elif network == "tiktok":
        if not creds["refresh_token"]:
            await store.mark_needs_reauth(customer_slug, account_id)
            raise HTTPException(400, "TikTok refresh credential unavailable; reconnect account")
        status, tok = await _http_json(
            "POST",
            "https://open.tiktokapis.com/v2/oauth/token/",
            data={
                "grant_type": "refresh_token",
                "refresh_token": creds["refresh_token"],
                "client_key": cfg.client_id,
                "client_secret": cfg.client_secret,
            },
        )
    elif network in ("linkedin", "linkedin_organization"):
        if not creds["refresh_token"]:
            await store.mark_needs_reauth(customer_slug, account_id)
            raise HTTPException(400, "LinkedIn account requires reconnection")
        status, tok = await _http_json(
            "POST",
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "refresh_token",
                "refresh_token": creds["refresh_token"],
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret,
            },
        )
    else:
        raise HTTPException(400, "Account must be reconnected to renew this network")

    if status >= 300:
        await store.mark_needs_reauth(customer_slug, account_id)
        raise HTTPException(400, "Provider rejected token renewal; reconnect account")

    new_access = str(tok.get("access_token") or "")
    expires_in = int(tok.get("expires_in") or 0)
    if not new_access or not (1 <= expires_in <= 5_184_000):
        raise HTTPException(400, "Invalid renewed token expiry")

    new_expiry = now + expires_in
    await store.update_refreshed_token(
        customer_slug=customer_slug,
        account_id=account_id,
        network=network,
        external_id=creds["external_id"],
        expected_old_token_enc=creds["token_enc"],
        new_access_token=new_access,
        new_refresh_token=tok.get("refresh_token"),
        new_expires_at=new_expiry,
    )
    return {"ok": True, "account_id": account_id, "expires_at": new_expiry}


async def disconnect_account(customer_slug: str, account_id: str, expected_network: str | None = None) -> dict:
    removed = await store.disconnect_account(customer_slug, account_id, expected_network=expected_network)
    # Best-effort remote revocation for X
    if removed["network"] == "x" and removed.get("access_token"):
        cfg = social_config.x_config()
        if cfg:
            try:
                await _http_json(
                    "POST",
                    "https://api.x.com/2/oauth2/revoke",
                    auth=(cfg.client_id, cfg.client_secret),
                    data={"token": removed["access_token"], "token_type_hint": "access_token"},
                )
            except HTTPException:
                pass
    return {"ok": True, "id": account_id}
