"""Modernised social network publishers with rate-limit retries and dry-run verification.

Supports all 7 networks:
- facebook (Meta Graph API v22.0: /{page_id}/feed, /photos, /videos)
- instagram (Meta Graph API v22.0: /{ig_id}/media -> container status -> /media_publish)
- linkedin & linkedin_organization (LinkedIn REST /rest/posts with Linkedin-Version)
- x (X API v2 POST /2/tweets)
- tiktok (TikTok Content Posting API v2 /v2/post/publish/video/init/)
- google_business (Google Business Profile localPosts API)

Never posts when `dry_run=True` or when the network's publish switch is disabled.
Retries ONLY on HTTP 429 (honouring Retry-After) or pre-accept transient 5xx/transport errors.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException

from . import config as social_config
from . import media as social_media


@dataclass
class PublishOutcome:
    ok: bool
    external_post_id: str | None = None
    external_url: str | None = None
    pending: bool = False
    retryable: bool = False
    retry_after_seconds: int = 0
    error: str | None = None
    dry_run_payload: dict | None = None


async def _request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    max_retries: int = 2,
    timeout: float = 20.0,
) -> tuple[int, dict, int]:
    """HTTP helper with bounded 429/503 retry and Retry-After parsing."""
    hdrs = {"Accept": "application/json", **(headers or {})}
    attempt = 0
    while True:
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                req_kwargs: dict[str, Any] = {
                    "headers": hdrs,
                    "params": params,
                    "json": json_body,
                    "data": data,
                }
                if files is not None:
                    req_kwargs["files"] = files
                resp = await client.request(method, url, **req_kwargs)
        except httpx.HTTPError as exc:
            if attempt < max_retries:
                attempt += 1
                await asyncio.sleep(min(2 ** attempt, 4))
                continue
            return 599, {"error": str(exc)}, 60

        retry_after = 0
        ra = resp.headers.get("retry-after")
        if ra and ra.isdigit():
            retry_after = min(int(ra), 900)

        if resp.status_code in (429, 502, 503, 504) and attempt < max_retries and retry_after <= 5:
            attempt += 1
            await asyncio.sleep(retry_after or min(2 ** attempt, 4))
            continue

        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text[:300]}
        return resp.status_code, body if isinstance(body, dict) else {}, retry_after


def _compose_text(post: dict) -> str:
    parts = [str(post.get("content") or "").strip()]
    link = str(post.get("link") or "").strip()
    tags = str(post.get("hashtags") or "").strip()
    if link:
        parts.append(link)
    if tags:
        parts.append(tags)
    return "\n\n".join(p for p in parts if p)


async def _resolve_media(customer_slug: str, ref: str) -> tuple[str, bytes | None, str]:
    if ref.startswith("upload:"):
        asset_id = ref[len("upload:"):]
        meta, raw_bytes = await social_media.load_media(customer_slug, asset_id)
        is_video = (meta.get("kind") == "video") or str(meta.get("mime") or "").startswith("video/")
        mime = str(meta.get("mime") or ("video/mp4" if is_video else "image/jpeg"))
        if not is_video and mime != "image/jpeg":
            raw_bytes, _, _ = social_media._normalize_image_to_jpeg(raw_bytes)
            mime = "image/jpeg"
        ext = ".mp4" if is_video else ".jpg"
        base = social_config.public_media_base_url()
        url = social_media.public_media_url(customer_slug, asset_id, base, ext=ext)
        return url, raw_bytes, mime
    return ref, None, ""


async def publish_to_account(
    *,
    customer_slug: str,
    post: dict,
    account: dict,
    dry_run: bool = False,
) -> PublishOutcome:
    network = account["network"]
    external_id = account["external_id"]
    token = account["access_token"]
    text = _compose_text(post)
    media_refs: list[str] = list(post.get("media") or [])
    first_media = ""
    first_media_bytes: bytes | None = None
    first_media_mime = ""
    if media_refs:
        try:
            first_media, first_media_bytes, first_media_mime = await _resolve_media(customer_slug, media_refs[0])
        except HTTPException:
            return PublishOutcome(
                ok=False,
                retryable=False,
                error="Uploaded image or video could not be found; re-upload the file and try again.",
            )

    if not dry_run and not social_config.is_network_publish_enabled(network):
        return PublishOutcome(
            ok=False,
            retryable=False,
            error=f"Live publishing is paused for {network.replace('_', ' ')}",
        )

    if network == "facebook":
        return await _publish_facebook(
            external_id,
            token,
            text,
            post.get("link") or "",
            first_media,
            dry_run,
            media_bytes=first_media_bytes,
            media_mime=first_media_mime,
        )
    if network == "instagram":
        return await _publish_instagram(external_id, token, text, first_media, dry_run)
    if network in ("linkedin", "linkedin_organization"):
        return await _publish_linkedin(network, external_id, token, text, post.get("link") or "", dry_run)
    if network == "x":
        return await _publish_x(token, text, dry_run)
    if network == "tiktok":
        return await _publish_tiktok(token, text, first_media, dry_run)
    if network == "google_business":
        return await _publish_google_business(external_id, token, text, post.get("link") or "", first_media, dry_run)
    return PublishOutcome(ok=False, error=f"Unsupported network: {network}")


def _is_video_url(url: str) -> bool:
    clean = (url or "").split("?", 1)[0].lower()
    return clean.endswith((".mp4", ".mov", ".webm", ".m4v", ".avi"))


async def _publish_facebook(
    page_id: str,
    token: str,
    text: str,
    link: str,
    media_url: str,
    dry_run: bool,
    *,
    media_bytes: bytes | None = None,
    media_mime: str = "",
) -> PublishOutcome:
    ver = social_config.meta_graph_version()
    upload_files: dict[str, Any] | None = None
    if media_url and _is_video_url(media_url):
        url = f"https://graph.facebook.com/{ver}/{page_id}/videos"
        payload = {"file_url": media_url, "description": text, "published": "true"}
    elif media_url:
        url = f"https://graph.facebook.com/{ver}/{page_id}/photos"
        if media_bytes and not dry_run:
            payload = {"caption": text, "published": "true"}
            upload_files = {"source": ("photo.jpg", media_bytes, media_mime or "image/jpeg")}
        else:
            payload = {"url": media_url, "caption": text, "published": "true"}
    else:
        url = f"https://graph.facebook.com/{ver}/{page_id}/feed"
        payload = {"message": text}
        if link:
            payload["link"] = link
    if dry_run:
        return PublishOutcome(ok=True, external_post_id="dry-run:facebook", dry_run_payload={"url": url, "payload": payload})
    if upload_files is not None:
        status, body, ra = await _request_with_retry(
            "POST", url, headers={"Authorization": f"Bearer {token}"}, data=payload, files=upload_files
        )
    else:
        status, body, ra = await _request_with_retry(
            "POST", url, headers={"Authorization": f"Bearer {token}"}, data=payload
        )
    if status < 300 and (body.get("id") or body.get("post_id")):
        pid = str(body.get("post_id") or body.get("id"))
        permalink = f"https://www.facebook.com/{pid}"
        p_code, p_body, _ = await _request_with_retry(
            "GET",
            f"https://graph.facebook.com/{ver}/{pid}",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "permalink_url"},
            max_retries=0,
            timeout=8.0,
        )
        if p_code < 300 and p_body.get("permalink_url"):
            permalink = str(p_body["permalink_url"])
        return PublishOutcome(ok=True, external_post_id=pid, external_url=permalink)
    msg = (body.get("error") or {}).get("message") if isinstance(body.get("error"), dict) else "Facebook rejected post"
    return PublishOutcome(
        ok=False,
        retryable=status in (429, 500, 502, 503, 504, 599),
        retry_after_seconds=ra or 60,
        error=f"Facebook error ({status}): {str(msg)[:200]}",
    )


async def _publish_instagram(
    ig_id: str, token: str, caption: str, media_url: str, dry_run: bool
) -> PublishOutcome:
    if not media_url:
        return PublishOutcome(ok=False, error="Instagram requires an image or video")
    ver = social_config.meta_graph_version()
    create_url = f"https://graph.facebook.com/{ver}/{ig_id}/media"
    is_vid = _is_video_url(media_url)
    payload = (
        {"media_type": "REELS", "video_url": media_url, "caption": caption}
        if is_vid
        else {"image_url": media_url, "caption": caption}
    )
    if dry_run:
        return PublishOutcome(ok=True, external_post_id="dry-run:instagram", dry_run_payload={"url": create_url, "payload": payload})
    status, body, ra = await _request_with_retry(
        "POST", create_url, headers={"Authorization": f"Bearer {token}"}, data=payload
    )
    creation_id = str(body.get("id") or "")
    if status >= 300 or not creation_id:
        msg = (body.get("error") or {}).get("message") if isinstance(body.get("error"), dict) else "Instagram media container rejected"
        return PublishOutcome(
            ok=False,
            retryable=status in (429, 500, 502, 503, 504, 599),
            retry_after_seconds=ra or 60,
            error=f"Instagram error ({status}): {str(msg)[:200]}",
        )
    status_url = f"https://graph.facebook.com/{ver}/{creation_id}?fields=status_code"
    polls = 10 if is_vid else 5
    for _ in range(polls):
        s_code, s_body, _ = await _request_with_retry("GET", status_url, headers={"Authorization": f"Bearer {token}"})
        code = str(s_body.get("status_code") or "").upper()
        if s_code >= 300 or not code or code in ("FINISHED", "PUBLISHED"):
            break
        if code in ("ERROR", "EXPIRED"):
            return PublishOutcome(ok=False, error=f"Instagram media container failed ({code})")
        await asyncio.sleep(2 if is_vid else 1)
    pub_url = f"https://graph.facebook.com/{ver}/{ig_id}/media_publish"
    p_status, p_body, p_ra = await _request_with_retry(
        "POST", pub_url, headers={"Authorization": f"Bearer {token}"}, data={"creation_id": creation_id}
    )
    if p_status < 300 and p_body.get("id"):
        media_id = str(p_body["id"])
        permalink = None
        m_code, m_body, _ = await _request_with_retry(
            "GET",
            f"https://graph.facebook.com/{ver}/{media_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "id,permalink,shortcode"},
            max_retries=0,
            timeout=8.0,
        )
        if m_code < 300:
            if m_body.get("permalink"):
                permalink = str(m_body["permalink"])
            elif m_body.get("shortcode"):
                permalink = f"https://www.instagram.com/p/{m_body['shortcode']}/"
        return PublishOutcome(ok=True, external_post_id=media_id, external_url=permalink)
    msg = (p_body.get("error") or {}).get("message") if isinstance(p_body.get("error"), dict) else "Instagram publish rejected"
    return PublishOutcome(
        ok=False,
        retryable=p_status in (429, 500, 502, 503, 504, 599),
        retry_after_seconds=p_ra or 60,
        error=f"Instagram publish error ({p_status}): {str(msg)[:200]}",
    )


async def _publish_linkedin(
    network: str, author_urn: str, token: str, text: str, link: str, dry_run: bool
) -> PublishOutcome:
    url = "https://api.linkedin.com/rest/posts"
    payload: dict[str, Any] = {
        "author": author_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if link:
        payload["content"] = {"article": {"source": link, "title": text[:100]}}
    if dry_run:
        return PublishOutcome(ok=True, external_post_id=f"dry-run:{network}", dry_run_payload={"url": url, "payload": payload})
    headers = {
        "Authorization": f"Bearer {token}",
        "Linkedin-Version": social_config.linkedin_api_version(),
        "X-Restli-Protocol-Version": "2.0.0",
    }
    status, body, ra = await _request_with_retry("POST", url, headers=headers, json_body=payload)
    if status < 300:
        pid = str(body.get("id") or "linkedin:published")
        return PublishOutcome(ok=True, external_post_id=pid)
    return PublishOutcome(
        ok=False,
        retryable=status in (429, 500, 502, 503, 504, 599),
        retry_after_seconds=ra or 60,
        error=f"LinkedIn error ({status}): {str(body.get('message') or 'rejected')[:200]}",
    )


async def _publish_x(token: str, text: str, dry_run: bool) -> PublishOutcome:
    url = "https://api.x.com/2/tweets"
    payload = {"text": text}
    if dry_run:
        return PublishOutcome(ok=True, external_post_id="dry-run:x", dry_run_payload={"url": url, "payload": payload})
    status, body, ra = await _request_with_retry(
        "POST", url, headers={"Authorization": f"Bearer {token}"}, json_body=payload
    )
    tid = str((body.get("data") or {}).get("id") or "")
    if status < 300 and tid:
        return PublishOutcome(ok=True, external_post_id=tid, external_url=f"https://x.com/i/web/status/{tid}")
    return PublishOutcome(
        ok=False,
        retryable=status in (429, 500, 502, 503, 504, 599),
        retry_after_seconds=ra or 60,
        error=f"X error ({status}): {str(body.get('detail') or body.get('title') or 'rejected')[:200]}",
    )


async def _publish_tiktok(token: str, caption: str, media_url: str, dry_run: bool) -> PublishOutcome:
    if not media_url:
        return PublishOutcome(ok=False, error="TikTok requires a video")
    url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    payload = {
        "post_info": {
            "title": caption[:2200],
            "privacy_level": "SELF_ONLY",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {"source": "PULL_FROM_URL", "video_url": media_url},
    }
    if dry_run:
        return PublishOutcome(ok=True, external_post_id="dry-run:tiktok", dry_run_payload={"url": url, "payload": payload})
    status, body, ra = await _request_with_retry(
        "POST", url, headers={"Authorization": f"Bearer {token}"}, json_body=payload
    )
    pub_id = str((body.get("data") or {}).get("publish_id") or "")
    if status < 300 and pub_id:
        return PublishOutcome(ok=True, external_post_id=f"pending:tiktok:{pub_id}", pending=True)
    err = (body.get("error") or {}).get("message") if isinstance(body.get("error"), dict) else "TikTok rejected upload"
    return PublishOutcome(
        ok=False,
        retryable=status in (429, 500, 502, 503, 504, 599),
        retry_after_seconds=ra or 60,
        error=f"TikTok error ({status}): {str(err)[:200]}",
    )


async def _publish_google_business(
    location_name: str, token: str, text: str, link: str, media_url: str, dry_run: bool
) -> PublishOutcome:
    url = f"https://mybusiness.googleapis.com/v4/{location_name}/localPosts"
    payload: dict[str, Any] = {"languageCode": "en", "summary": text[:1500], "topicType": "STANDARD"}
    if link:
        payload["callToAction"] = {"actionType": "LEARN_MORE", "url": link}
    if media_url:
        payload["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": media_url}]
    if dry_run:
        return PublishOutcome(
            ok=True, external_post_id="dry-run:google_business", dry_run_payload={"url": url, "payload": payload}
        )
    status, body, ra = await _request_with_retry(
        "POST", url, headers={"Authorization": f"Bearer {token}"}, json_body=payload
    )
    if status < 300 and body.get("name"):
        return PublishOutcome(ok=True, external_post_id=str(body["name"]), external_url=body.get("searchUrl"))
    err = (body.get("error") or {}).get("message") if isinstance(body.get("error"), dict) else "Google Business rejected post"
    return PublishOutcome(
        ok=False,
        retryable=status in (429, 500, 502, 503, 504, 599),
        retry_after_seconds=ra or 60,
        error=f"Google Business error ({status}): {str(err)[:200]}",
    )
