"""Meta Graph API flows required for Meta App Review (Pages, Business assets, and Page activity).

Authentication model:
- Standard User OAuth 2.0 via Facebook Login (no system user tokens).
- The tenant owner completes Facebook Login in a browser popup, granting the 6 permissions:
  pages_show_list, pages_manage_posts, pages_read_engagement, business_management,
  instagram_basic, instagram_content_publish.
- The encrypted 60-day long-lived User Access Token is stored in `social_meta_sessions` for
  Page discovery (`/me/accounts`), Business discovery (`/me/businesses`), and linking Pages to a
  Meta Business Portfolio (`/{business_id}/owned_pages` or `/{business_id}/client_pages`).
- Derived non-expiring Page Access Tokens are encrypted per account in `social_accounts` for
  reading Page engagement (`/{page_id}` and `/{page_id}/posts`), publishing to Facebook Pages,
  and publishing to linked Instagram Professional accounts.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from fastapi import HTTPException

from . import config as social_config
from . import oauth, store

_NUMERIC_ID = re.compile(r"^[0-9]{3,40}$")
_PAGE_FIELDS = (
    "id,name,access_token,tasks,category,fan_count,followers_count,"
    "picture.type(large){url},"
    "instagram_business_account{id,username,name,profile_picture_url,followers_count}"
)


def _graph_base() -> str:
    return f"https://graph.facebook.com/{social_config.meta_graph_version()}"


def _graph_error_detail(body: dict, fallback: str) -> tuple[int | None, str]:
    err = body.get("error")
    if isinstance(err, dict):
        code = err.get("code")
        msg = str(err.get("error_user_msg") or err.get("message") or fallback).strip()
        return (int(code) if isinstance(code, int) else None), msg[:260]
    return None, fallback


def _page_avatar_url(page: dict, page_id: str) -> str:
    pic_url = str(((page.get("picture") or {}).get("data") or {}).get("url") or "").strip()
    if pic_url:
        return pic_url
    if page_id:
        return f"{_graph_base()}/{page_id}/picture?type=large"
    return ""


def _extract_page_summary(page: dict, connected_fb: dict[str, dict], connected_ig: dict[str, dict]) -> dict:
    page_id = str(page.get("id") or "").strip()
    page_name = str(page.get("name") or page_id).strip()
    pic_url = _page_avatar_url(page, page_id)
    ig = page.get("instagram_business_account") or {}
    ig_id = str(ig.get("id") or "").strip()
    ig_info = None
    if ig_id:
        ig_acct = connected_ig.get(ig_id)
        ig_info = {
            "id": ig_id,
            "username": str(ig.get("username") or ig.get("name") or ig_id).strip(),
            "avatar_url": str(ig.get("profile_picture_url") or "").strip(),
            "followers_count": ig.get("followers_count"),
            "connected_account_id": ig_acct["id"] if ig_acct else None,
        }
    fb_acct = connected_fb.get(page_id)
    fb_meta = (fb_acct or {}).get("metadata") or {}
    return {
        "page_id": page_id,
        "name": page_name,
        "avatar_url": pic_url,
        "category": str(page.get("category") or ""),
        "followers_count": page.get("followers_count"),
        "fan_count": page.get("fan_count"),
        "tasks": list(page.get("tasks") or []),
        "connected_account_id": fb_acct["id"] if fb_acct else None,
        "linked_business_id": str(fb_meta.get("linked_business_id") or ""),
        "linked_business_name": str(fb_meta.get("linked_business_name") or ""),
        "business_link_status": str(fb_meta.get("business_link_status") or ""),
        "instagram": ig_info,
    }


async def list_meta_pages(customer_slug: str) -> dict:
    """List authorized Facebook Pages (with avatars & linked IG accounts) using pages_show_list + instagram_basic."""
    session = await store.get_meta_session(customer_slug)
    accounts = await store.list_accounts(customer_slug)
    connected_fb = {a["external_id"]: a for a in accounts if a["network"] == "facebook"}
    connected_ig = {a["external_id"]: a for a in accounts if a["network"] == "instagram"}

    if not session:
        # Still return already-connected Facebook Pages from the store if present
        fallback_pages = []
        for ext_id, acct in connected_fb.items():
            meta = acct.get("metadata") or {}
            ig_meta = meta.get("linked_instagram") if isinstance(meta.get("linked_instagram"), dict) else None
            ig_info = None
            if ig_meta and ig_meta.get("id"):
                ig_acct = connected_ig.get(str(ig_meta["id"]))
                ig_info = {
                    "id": str(ig_meta["id"]),
                    "username": str(ig_meta.get("username") or ""),
                    "avatar_url": str(ig_meta.get("avatar_url") or ""),
                    "followers_count": ig_meta.get("followers_count"),
                    "connected_account_id": ig_acct["id"] if ig_acct else None,
                }
            fallback_pages.append({
                "page_id": ext_id,
                "name": acct["display_name"],
                "avatar_url": str(meta.get("avatar_url") or "") or (f"{_graph_base()}/{ext_id}/picture?type=large" if ext_id else ""),
                "category": str(meta.get("category") or ""),
                "followers_count": meta.get("followers_count"),
                "fan_count": meta.get("fan_count"),
                "tasks": list(meta.get("tasks") or []),
                "connected_account_id": acct["id"],
                "linked_business_id": str(meta.get("linked_business_id") or ""),
                "linked_business_name": str(meta.get("linked_business_name") or ""),
                "business_link_status": str(meta.get("business_link_status") or ""),
                "instagram": ig_info,
            })
        return {
            "connected": False,
            "meta_user_name": "",
            "granted_scopes": [],
            "selected_business_id": "",
            "selected_business_name": "",
            "pages": fallback_pages,
        }

    gbase = _graph_base()
    status, body = await oauth._http_json(
        "GET",
        f"{gbase}/me/accounts",
        params={"fields": _PAGE_FIELDS, "limit": "50"},
        headers={"Authorization": f"Bearer {session['user_access_token']}"},
    )
    if status >= 300:
        _, msg = _graph_error_detail(body, "Could not load Facebook Pages from Meta")
        raise HTTPException(400, msg)

    pages = [
        _extract_page_summary(p, connected_fb, connected_ig)
        for p in (body.get("data") or [])
        if str(p.get("id") or "").strip()
    ]
    return {
        "connected": True,
        "meta_user_name": session["meta_user_name"],
        "granted_scopes": session["granted_scopes"],
        "selected_business_id": session["selected_business_id"],
        "selected_business_name": session["selected_business_name"],
        "pages": pages,
    }


async def select_meta_page(customer_slug: str, page_id: str, *, include_instagram: bool = True) -> dict:
    """Connect/select an authorized Facebook Page (and its linked IG Professional account) from the Page picker."""
    clean_page_id = (page_id or "").strip()
    if not _NUMERIC_ID.fullmatch(clean_page_id):
        raise HTTPException(400, "Invalid Facebook Page ID")

    session = await store.get_meta_session(customer_slug)
    if not session:
        raise HTTPException(409, "Sign in with Facebook first to select a Page")

    gbase = _graph_base()
    status, body = await oauth._http_json(
        "GET",
        f"{gbase}/me/accounts",
        params={"fields": _PAGE_FIELDS, "limit": "50"},
        headers={"Authorization": f"Bearer {session['user_access_token']}"},
    )
    if status >= 300:
        _, msg = _graph_error_detail(body, "Facebook Page lookup rejected")
        raise HTTPException(400, msg)

    match = next((p for p in (body.get("data") or []) if str(p.get("id") or "").strip() == clean_page_id), None)
    if not match:
        raise HTTPException(404, "Selected Facebook Page was not found in your authorized Pages")

    page_name = str(match.get("name") or clean_page_id).strip()
    page_token = str(match.get("access_token") or "").strip()
    if not page_token:
        raise HTTPException(400, "Meta did not return a Page access token for the selected Page")

    pic_url = _page_avatar_url(match, clean_page_id)
    ig = match.get("instagram_business_account") or {}
    ig_id = str(ig.get("id") or "").strip()
    ig_username = str(ig.get("username") or ig.get("name") or "").strip()
    ig_avatar = str(ig.get("profile_picture_url") or "").strip()
    ig_followers = ig.get("followers_count")

    linked_ig = (
        {
            "id": ig_id,
            "username": ig_username or page_name,
            "avatar_url": ig_avatar,
            "followers_count": ig_followers,
        }
        if ig_id
        else None
    )
    granted_str = " ".join(session["granted_scopes"]) or oauth.META_REVIEW_SCOPES

    fb_account_id = await store.upsert_verified_account(
        customer_slug=customer_slug,
        network="facebook",
        external_id=clean_page_id,
        display_name=page_name,
        access_token=page_token,
        expires_at=None,
        granted_scopes=granted_str,
        metadata={
            "avatar_url": pic_url,
            "category": str(match.get("category") or ""),
            "fan_count": match.get("fan_count"),
            "followers_count": match.get("followers_count"),
            "tasks": list(match.get("tasks") or []),
            "linked_instagram": linked_ig,
        },
    )

    ig_account_id = None
    if include_instagram and ig_id:
        ig_account_id = await store.upsert_verified_account(
            customer_slug=customer_slug,
            network="instagram",
            external_id=ig_id,
            display_name=ig_username or page_name,
            access_token=page_token,
            expires_at=None,
            granted_scopes=granted_str,
            metadata={
                "avatar_url": ig_avatar,
                "page_id": clean_page_id,
                "page_name": page_name,
                "followers_count": ig_followers,
            },
        )

    msg = f"Selected Facebook Page '{page_name}'"
    if ig_account_id and ig_username:
        msg += f" and linked Instagram '@{ig_username}'."
    else:
        msg += "."

    await store.record_event(customer_slug, None, "meta.page_selected", f"page={clean_page_id}")
    return {
        "ok": True,
        "page_id": clean_page_id,
        "page_name": page_name,
        "avatar_url": pic_url,
        "facebook_account_id": fb_account_id,
        "instagram_account_id": ig_account_id,
        "instagram": linked_ig,
        "message": msg,
    }


async def list_meta_businesses(customer_slug: str) -> dict:
    """List Meta Business Portfolios for the signed-in user using business_management."""
    session = await store.get_meta_session(customer_slug)
    if not session:
        return {
            "connected": False,
            "granted_business_management": False,
            "selected_business_id": "",
            "selected_business_name": "",
            "businesses": [],
        }

    granted_bm = "business_management" in set(session["granted_scopes"])
    gbase = _graph_base()
    status, body = await oauth._http_json(
        "GET",
        f"{gbase}/me/businesses",
        params={"fields": "id,name,profile_picture_uri,verification_status,primary_page{id,name}", "limit": "25"},
        headers={"Authorization": f"Bearer {session['user_access_token']}"},
    )
    if status >= 300:
        _, msg = _graph_error_detail(body, "Could not load Meta Business Portfolios")
        raise HTTPException(400, msg)

    businesses = []
    for biz in (body.get("data") or [])[:15]:
        bid = str(biz.get("id") or "").strip()
        bname = str(biz.get("name") or bid).strip()
        if not bid:
            continue
        owned_ids: list[str] = []
        client_ids: list[str] = []
        own_status, own_body = await oauth._http_json(
            "GET",
            f"{gbase}/{bid}/owned_pages",
            params={"fields": "id,name", "limit": "25"},
            headers={"Authorization": f"Bearer {session['user_access_token']}"},
        )
        if own_status < 300:
            owned_ids = [str(p.get("id")) for p in (own_body.get("data") or []) if p.get("id")]

        cli_status, cli_body = await oauth._http_json(
            "GET",
            f"{gbase}/{bid}/client_pages",
            params={"fields": "id,name", "limit": "25"},
            headers={"Authorization": f"Bearer {session['user_access_token']}"},
        )
        if cli_status < 300:
            client_ids = [str(p.get("id")) for p in (cli_body.get("data") or []) if p.get("id")]

        businesses.append({
            "id": bid,
            "name": bname,
            "avatar_url": str(biz.get("profile_picture_uri") or "").strip(),
            "verification_status": str(biz.get("verification_status") or ""),
            "primary_page": biz.get("primary_page") if isinstance(biz.get("primary_page"), dict) else None,
            "owned_page_ids": owned_ids,
            "client_page_ids": client_ids,
        })

    return {
        "connected": True,
        "granted_business_management": granted_bm,
        "selected_business_id": session["selected_business_id"],
        "selected_business_name": session["selected_business_name"],
        "businesses": businesses,
    }


async def link_page_to_business(
    customer_slug: str,
    *,
    business_id: str,
    page_id: str,
    relation: str = "owned",
) -> dict:
    """Link or claim a Facebook Page under a selected Meta Business Portfolio via business_management."""
    clean_biz_id = (business_id or "").strip()
    clean_page_id = (page_id or "").strip()
    if not _NUMERIC_ID.fullmatch(clean_biz_id):
        raise HTTPException(400, "Invalid Meta Business ID")
    if not _NUMERIC_ID.fullmatch(clean_page_id):
        raise HTTPException(400, "Invalid Facebook Page ID")
    if relation not in ("owned", "client"):
        raise HTTPException(400, "Relation must be 'owned' or 'client'")

    session = await store.get_meta_session(customer_slug)
    if not session:
        raise HTTPException(409, "Sign in with Facebook first to manage Business assets")
    if session["granted_scopes"] and "business_management" not in set(session["granted_scopes"]):
        raise HTTPException(403, "business_management permission was not granted; reconnect with Facebook")

    gbase = _graph_base()
    headers = {"Authorization": f"Bearer {session['user_access_token']}"}

    # Verify Business belongs to user and get its display name (plus primary_page for already-owned detection)
    b_status, b_body = await oauth._http_json(
        "GET", f"{gbase}/me/businesses", params={"fields": "id,name,primary_page{id,name}", "limit": "50"}, headers=headers
    )
    if b_status >= 300:
        _, msg = _graph_error_detail(b_body, "Could not verify Meta Business Portfolio")
        raise HTTPException(400, msg)
    biz_match = next((b for b in (b_body.get("data") or []) if str(b.get("id") or "") == clean_biz_id), None)
    if not biz_match:
        raise HTTPException(404, "Selected Meta Business Portfolio was not found for this account")
    business_name = str(biz_match.get("name") or clean_biz_id).strip()
    primary_page_id = str(((biz_match.get("primary_page") or {}).get("id")) or "").strip()

    # Resolve Page display name from connected accounts or /me/accounts
    accounts = await store.list_accounts(customer_slug)
    fb_acct = next((a for a in accounts if a["network"] == "facebook" and a["external_id"] == clean_page_id), None)
    page_name = fb_acct["display_name"] if fb_acct else clean_page_id
    if not fb_acct:
        p_status, p_body = await oauth._http_json(
            "GET", f"{gbase}/me/accounts", params={"fields": "id,name", "limit": "50"}, headers=headers
        )
        if p_status < 300:
            pm = next((p for p in (p_body.get("data") or []) if str(p.get("id") or "") == clean_page_id), None)
            if pm:
                page_name = str(pm.get("name") or clean_page_id).strip()

    if relation == "owned":
        l_status, l_body = await oauth._http_json(
            "POST",
            f"{gbase}/{clean_biz_id}/owned_pages",
            data={"page_id": clean_page_id},
            headers=headers,
        )
    else:
        l_status, l_body = await oauth._http_json(
            "POST",
            f"{gbase}/{clean_biz_id}/client_pages",
            data={
                "page_id": clean_page_id,
                "permitted_tasks": json.dumps(["CREATE_CONTENT", "MODERATE", "ANALYZE", "MANAGE"]),
            },
            headers=headers,
        )

    access_status = ""
    if l_status < 300:
        access_status = str(l_body.get("access_status") or "CONFIRMED").upper()
    else:
        err_code, err_msg = _graph_error_detail(l_body, "Could not link Page to Meta Business")
        err_lower = err_msg.lower()
        already_hint = err_code == 3944 or any(
            phrase in err_lower
            for phrase in (
                "already has access",
                "already owned",
                "already linked",
                "already claimed",
                "already associated",
                "already been added",
                "primary page",
            )
        )
        edge = "owned_pages" if relation == "owned" else "client_pages"
        v_status, v_body = await oauth._http_json(
            "GET", f"{gbase}/{clean_biz_id}/{edge}", params={"fields": "id,name", "limit": "100"}, headers=headers
        )
        verified_ids = {str(p.get("id") or "") for p in (v_body.get("data") or [])} if v_status < 300 else set()
        already_in_business = (
            clean_page_id in verified_ids
            or (relation == "owned" and primary_page_id == clean_page_id)
            or already_hint
        )
        if already_in_business:
            access_status = "ALREADY_LINKED"
        else:
            prefix = f"Meta error ({err_code})" if err_code is not None else "Meta error"
            raise HTTPException(400, f"{prefix}: {err_msg}")

    linked_at = datetime.now(timezone.utc).isoformat()
    await store.update_meta_session_business(customer_slug, clean_biz_id, business_name)
    if fb_acct:
        await store.update_account_metadata(
            customer_slug,
            fb_acct["id"],
            {
                "linked_business_id": clean_biz_id,
                "linked_business_name": business_name,
                "business_link_status": access_status,
                "business_link_relation": relation,
                "business_linked_at": linked_at,
            },
        )
    await store.record_event(
        customer_slug,
        None,
        "meta.business_page_linked",
        f"business={clean_biz_id} page={clean_page_id} relation={relation} status={access_status}",
    )

    if access_status == "ALREADY_LINKED":
        message = f"Page is linked to {business_name}."
    elif access_status == "PENDING":
        message = f"Link request submitted for Facebook Page '{page_name}' under business '{business_name}' (Pending approval)."
    else:
        message = f"Page is linked to {business_name} (Confirmed)."

    return {
        "ok": True,
        "business_id": clean_biz_id,
        "business_name": business_name,
        "page_id": clean_page_id,
        "page_name": page_name,
        "relation": relation,
        "access_status": access_status,
        "linked_at": linked_at,
        "message": message,
    }


async def get_page_activity(customer_slug: str, account_id: str, *, limit: int = 10) -> dict:
    """Retrieve Facebook Page profile, followers, recent posts, engagement, and photos via pages_read_engagement."""
    creds = await store.get_account_credentials(customer_slug, account_id, allow_expired=False)
    if creds["network"] != "facebook":
        raise HTTPException(400, "Page activity is available for connected Facebook Pages")

    page_id = creds["external_id"]
    page_token = creds["access_token"]
    gbase = _graph_base()
    headers = {"Authorization": f"Bearer {page_token}"}
    clamped_limit = max(1, min(int(limit or 10), 25))

    # 1. Page profile & follower metrics
    info_status, info_body = await oauth._http_json(
        "GET",
        f"{gbase}/{page_id}",
        params={
            "fields": (
                "id,name,category,link,fan_count,followers_count,"
                "picture.type(large){url},"
                "instagram_business_account{id,username,profile_picture_url,followers_count}"
            )
        },
        headers=headers,
    )
    if info_status >= 300:
        _, msg = _graph_error_detail(info_body, "Could not retrieve Facebook Page details")
        raise HTTPException(400, msg)

    # 2. Recent Page posts with engagement summary counts (likes, comments, shares)
    posts_status, posts_body = await oauth._http_json(
        "GET",
        f"{gbase}/{page_id}/posts",
        params={
            "fields": (
                "id,message,story,created_time,permalink_url,full_picture,"
                "likes.summary(true).limit(0),comments.summary(true).limit(0),shares"
            ),
            "limit": str(clamped_limit),
        },
        headers=headers,
    )
    if posts_status >= 300:
        _, msg = _graph_error_detail(posts_body, "Could not retrieve Page posts and engagement")
        raise HTTPException(400, msg)

    # 3. Best-effort uploaded Page photos
    photos: list[dict] = []
    ph_status, ph_body = await oauth._http_json(
        "GET",
        f"{gbase}/{page_id}/photos",
        params={"type": "uploaded", "fields": "id,name,images,picture,link,created_time", "limit": "6"},
        headers=headers,
    )
    if ph_status < 300:
        for ph in ph_body.get("data") or []:
            imgs = ph.get("images") or []
            img_url = str(imgs[0].get("source") or "") if imgs and isinstance(imgs[0], dict) else ""
            if not img_url:
                img_url = str(ph.get("picture") or "")
            if img_url:
                photos.append({
                    "id": str(ph.get("id") or ""),
                    "caption": str(ph.get("name") or ""),
                    "image_url": img_url,
                    "link": str(ph.get("link") or ""),
                    "created_time": str(ph.get("created_time") or ""),
                })

    page_name = str(info_body.get("name") or creds["display_name"] or page_id).strip()
    avatar_url = _page_avatar_url(info_body, page_id)
    ig = info_body.get("instagram_business_account") or {}
    ig_info = (
        {
            "id": str(ig.get("id") or ""),
            "username": str(ig.get("username") or ""),
            "avatar_url": str(ig.get("profile_picture_url") or ""),
            "followers_count": ig.get("followers_count"),
        }
        if ig.get("id")
        else None
    )

    posts_out: list[dict] = []
    total_likes = 0
    total_comments = 0
    total_shares = 0
    for item in posts_body.get("data") or []:
        likes = int(((item.get("likes") or {}).get("summary") or {}).get("total_count") or 0)
        comments = int(((item.get("comments") or {}).get("summary") or {}).get("total_count") or 0)
        shares = int((item.get("shares") or {}).get("count") or 0)
        total_likes += likes
        total_comments += comments
        total_shares += shares
        pid = str(item.get("id") or "")
        posts_out.append({
            "id": pid,
            "message": str(item.get("message") or item.get("story") or "").strip(),
            "created_time": str(item.get("created_time") or ""),
            "permalink_url": str(item.get("permalink_url") or (f"https://www.facebook.com/{pid}" if pid else "")),
            "image_url": str(item.get("full_picture") or ""),
            "likes": likes,
            "comments": comments,
            "shares": shares,
        })

    # Keep stored account metadata fresh
    await store.update_account_metadata(
        customer_slug,
        account_id,
        {
            "avatar_url": avatar_url,
            "category": str(info_body.get("category") or ""),
            "followers_count": info_body.get("followers_count"),
            "fan_count": info_body.get("fan_count"),
            "linked_instagram": ig_info,
        },
    )

    return {
        "account_id": account_id,
        "page": {
            "id": page_id,
            "name": page_name,
            "avatar_url": avatar_url,
            "category": str(info_body.get("category") or ""),
            "link": str(info_body.get("link") or f"https://www.facebook.com/{page_id}"),
            "followers_count": info_body.get("followers_count"),
            "fan_count": info_body.get("fan_count"),
            "instagram": ig_info,
        },
        "totals": {
            "posts": len(posts_out),
            "likes": total_likes,
            "comments": total_comments,
            "shares": total_shares,
        },
        "posts": posts_out,
        "photos": photos,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
