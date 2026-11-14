"""Branded images, short videos and hosted AI images for client marketing.

Rendering happens in the internal media-render sidecar (Satori + FFmpeg);
AI images come from Cloudflare Workers AI. No GPU or local model weights.
"""
from __future__ import annotations

import base64
import hashlib
import mimetypes
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import db, owner_auth
from .config import get_settings

router = APIRouter(prefix="/owner/media", tags=["media"])

TEMPLATES = [
    {"id": "showcase", "name": "Project showcase", "needs": "1 photo"},
    {"id": "before_after", "name": "Before / after", "needs": "2 photos"},
    {"id": "quote", "name": "Quote card", "needs": "text only"},
    {"id": "service", "name": "Service card", "needs": "text only"},
]
FORMATS = [
    {"id": "square", "name": "Square 1080×1080"},
    {"id": "portrait", "name": "Portrait 1080×1350"},
    {"id": "story", "name": "Story 1080×1920"},
]


class Brand(BaseModel):
    name: str = Field(default="", max_length=120)
    accent: str = Field(default="#c8f560", pattern=r"^#[0-9a-fA-F]{6}$")
    contact: str = Field(default="", max_length=160)
    logo: str | None = Field(default=None, max_length=400_000)


class ImageRequest(BaseModel):
    template: Literal["showcase", "before_after", "quote", "service"]
    format: Literal["square", "portrait", "story"] = "square"
    headline: str = Field(default="", max_length=240)
    subline: str = Field(default="", max_length=600)
    kicker: str = Field(default="", max_length=60)
    before_label: str = Field(default="BEFORE", max_length=30)
    after_label: str = Field(default="AFTER", max_length=30)
    photos: list[str] = Field(default_factory=list, max_length=20)


class AiRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)


def _configured() -> str:
    url = get_settings().media_render_url.rstrip("/")
    if not url:
        raise HTTPException(503, "Media rendering is not configured")
    return url


# Cloudflare gives up on an origin that has not answered in about 100 seconds, and then serves
# its own error page instead of ours. Waiting 200s meant a slow AI image was reported to the
# customer as "The origin web server returned an invalid or incomplete response to Cloudflare" —
# our own plumbing, printed at them. Finish first and say something useful.
RENDER_TIMEOUT_SECONDS = 85.0


async def _render(path: str, payload: dict) -> bytes:
    try:
        async with httpx.AsyncClient(base_url=_configured(), timeout=RENDER_TIMEOUT_SECONDS) as client:
            response = await client.post(path, json=payload)
    except httpx.TimeoutException:
        raise HTTPException(504, "That took longer than we allow. The image is still being made — "
                                 "try again in a minute and it will usually come back straight away.")
    except httpx.HTTPError as exc:
        raise HTTPException(503, f"The image studio is not answering ({type(exc).__name__}).") from exc
    if response.status_code >= 400:
        detail = response.text[:300] or f"Render HTTP {response.status_code}"
        raise HTTPException(502, detail)
    return response.content


def _photos(values: list[str]) -> list[str]:
    cleaned = []
    total = 0
    for value in values:
        if not value.startswith("data:image/") or len(value) > 25_000_000:
            raise HTTPException(400, "Photos must be image uploads under 25 MB each")
        total += len(value)
        cleaned.append(value)
    if total > 40_000_000:
        raise HTTPException(413, "Send fewer photos at once (about 40 MB total)")
    return cleaned


async def _check_quota(tenant_id, kind: str) -> None:
    settings = get_settings()
    limits = {"image": settings.media_image_limit, "video": settings.media_video_limit, "ai": settings.media_ai_limit}
    row = await db.pool().fetchrow(
        """SELECT count(*) FILTER (WHERE kind='image') AS images,
                  count(*) FILTER (WHERE kind='video') AS videos,
                  count(*) FILTER (WHERE kind='ai') AS ai,
                  COALESCE(sum(size_bytes),0) AS bytes
           FROM media_assets WHERE tenant_id=$1 AND created_at >= date_trunc('month', now())""",
        tenant_id)
    used = {"image": row["images"], "video": row["videos"], "ai": row["ai"]}[kind]
    if used >= limits[kind]:
        raise HTTPException(429, f"Monthly {kind} limit reached ({limits[kind]}). It resets next month.")
    total = await db.pool().fetchval("SELECT COALESCE(sum(size_bytes),0) FROM media_assets WHERE tenant_id=$1", tenant_id)
    if total >= settings.media_storage_limit_bytes:
        raise HTTPException(413, "Media storage limit reached. Download and remove older media, then try again.")


async def _brand(tenant_id) -> dict:
    row = await db.pool().fetchrow("SELECT * FROM media_brand WHERE tenant_id=$1", tenant_id)
    return dict(row) if row else {"name": "", "accent": "#c8f560", "contact": "", "logo_data": None}


def _brand_payload(row: dict) -> dict:
    return {"name": row.get("name") or "", "accent": row.get("accent") or "#c8f560",
            "contact": row.get("contact") or "", "logo": row.get("logo_data") or ""}


async def _store(tenant_id, kind: str, template: str, prompt: str, fmt: str,
                 content: bytes, content_type: str, email: str) -> dict:
    folder = Path(get_settings().media_dir) / str(tenant_id)
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(content).hexdigest()[:16]
    name = f"{kind}-{digest}.{'mp4' if content_type == 'video/mp4' else 'png' if content_type == 'image/png' else 'jpg'}"
    path = folder / name
    path.write_bytes(content)
    row = await db.pool().fetchrow(
        """INSERT INTO media_assets(tenant_id,kind,template,prompt,format,content_type,storage_path,created_by,size_bytes)
           VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *""",
        tenant_id, kind, template, prompt[:2000], fmt, content_type, str(path), email, len(content))
    return dict(row)


@router.get("/templates")
async def templates(user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    return {"templates": TEMPLATES, "formats": FORMATS}


@router.get("/brand")
async def get_brand(user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    return await _brand(user["tenant_id"])


@router.put("/brand")
async def put_brand(body: Brand, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if body.logo and not body.logo.startswith("data:image/"):
        raise HTTPException(400, "Logo must be an image upload")
    row = await db.pool().fetchrow(
        """INSERT INTO media_brand(tenant_id,name,accent,contact,logo_data,updated_at)
           VALUES($1,$2,$3,$4,$5,now())
           ON CONFLICT(tenant_id) DO UPDATE SET name=EXCLUDED.name,accent=EXCLUDED.accent,
             contact=EXCLUDED.contact,logo_data=EXCLUDED.logo_data,updated_at=now()
           RETURNING *""",
        user["tenant_id"], body.name, body.accent, body.contact, body.logo)
    # The widget and chat surfaces read the tenant accent, so keep them in step.
    await db.pool().execute("UPDATE tenants SET accent_color=$2 WHERE id=$1", user["tenant_id"], body.accent)
    return dict(row)


@router.post("/image", status_code=201)
async def image(body: ImageRequest, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    await _check_quota(user["tenant_id"], "image")
    brand = _brand_payload(await _brand(user["tenant_id"]))
    content = await _render("/render/image", {
        "template": body.template, "format": body.format, "brand": brand,
        "photos": _photos(body.photos),
        "text": {"headline": body.headline, "subline": body.subline, "kicker": body.kicker,
                 "before_label": body.before_label, "after_label": body.after_label},
    })
    return await _store(user["tenant_id"], "image", body.template, "", body.format,
                        content, "image/png", user.get("email", ""))


VIDEO_TYPES = {"video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm"}
IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
UPLOAD_LIMIT = 200_000_000


@router.post("/upload", status_code=201)
async def upload(request: Request, user=Depends(owner_auth.current_user)):
    """Take a video the customer already made — with an AI tool elsewhere, or filmed themselves.

    We do not generate video: the model catalogue on this account has no text-to-video model, and
    promising one produced nothing but disappointment. What we do well is post it.
    """
    owner_auth.require_role(user, "editor")
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type in VIDEO_TYPES:
        kind, suffix = "video", VIDEO_TYPES[content_type]
    elif content_type in IMAGE_TYPES:
        kind, suffix = "image", IMAGE_TYPES[content_type]
    else:
        raise HTTPException(400, "That file type is not supported. Send MP4, MOV, WebM, JPEG, PNG "
                                 "or WebP.")
    body = await request.body()
    if not body:
        raise HTTPException(400, "That file was empty")
    if len(body) > UPLOAD_LIMIT:
        raise HTTPException(413, "That file is over 200 MB. Trim it, or export at a smaller size.")
    storage = await db.pool().fetchval("SELECT COALESCE(sum(size_bytes),0) FROM media_assets WHERE tenant_id=$1",
                                       user["tenant_id"])
    if storage + len(body) > get_settings().media_storage_limit_bytes:
        raise HTTPException(413, "Media storage limit reached. Delete older media, then try again.")
    row = await _store(user["tenant_id"], kind, "upload", "", "landscape", body,
                       content_type, user.get("email", ""))
    path = Path(row["storage_path"])
    path.rename(path.with_suffix("." + suffix))
    await db.pool().execute("UPDATE media_assets SET storage_path=$2 WHERE id=$1",
                            row["id"], str(path.with_suffix("." + suffix)))
    row["storage_path"] = str(path.with_suffix("." + suffix))
    return row


@router.post("/ai-image", status_code=201)
async def ai_image(body: AiRequest, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    await _check_quota(user["tenant_id"], "ai")
    content = await _render("/ai-image", {"prompt": body.prompt})
    return await _store(user["tenant_id"], "ai", "ai", body.prompt, "square",
                        content, "image/jpeg", user.get("email", ""))


@router.get("/usage")
async def usage(user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    settings = get_settings()
    row = await db.pool().fetchrow(
        """SELECT count(*) FILTER (WHERE kind='image') AS images,
                  count(*) FILTER (WHERE kind='video') AS videos,
                  count(*) FILTER (WHERE kind='ai') AS ai
           FROM media_assets WHERE tenant_id=$1 AND created_at >= date_trunc('month', now())""",
        user["tenant_id"])
    total = await db.pool().fetchval("SELECT COALESCE(sum(size_bytes),0) FROM media_assets WHERE tenant_id=$1", user["tenant_id"])
    return {"images": {"used": row["images"], "limit": settings.media_image_limit},
            "videos": {"used": row["videos"], "limit": settings.media_video_limit},
            "ai": {"used": row["ai"], "limit": settings.media_ai_limit},
            "storage": {"used": total, "limit": settings.media_storage_limit_bytes}}


@router.get("/assets")
async def assets(user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    rows = await db.pool().fetch(
        "SELECT id,kind,template,prompt,format,content_type,created_at FROM media_assets "
        "WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 100", user["tenant_id"])
    return [dict(row) for row in rows]


@router.post("/assets/{asset_id}/to-social")
async def to_social(asset_id: UUID, user=Depends(owner_auth.current_user)):
    """Copy a finished asset into the social media library so the composer can use it."""
    owner_auth.require_role(user, "editor")
    row = await db.pool().fetchrow(
        "SELECT content_type,storage_path FROM media_assets WHERE tenant_id=$1 AND id=$2",
        user["tenant_id"], asset_id)
    if not row or not Path(row["storage_path"]).is_file():
        raise HTTPException(404, "Media not found")
    from . import social_bridge
    base, key = social_bridge._configuration()
    slug = await social_bridge.ensure_tenant(user)
    data = Path(row["storage_path"]).read_bytes()
    async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
        result = await client.post(
            base + f"/v1/customers/{slug}/media",
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/octet-stream"},
            content=data)
    if result.status_code != 200:
        raise HTTPException(502, "Social media upload failed")
    return result.json()


@router.get("/assets/{asset_id}/file")
async def asset_file(asset_id: UUID, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    row = await db.pool().fetchrow(
        "SELECT content_type,storage_path FROM media_assets WHERE tenant_id=$1 AND id=$2",
        user["tenant_id"], asset_id)
    if not row or not Path(row["storage_path"]).is_file():
        raise HTTPException(404, "Media not found")
    return FileResponse(row["storage_path"], media_type=row["content_type"])


class DeleteMany(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=200)


@router.post("/assets/delete")
async def delete_assets(body: DeleteMany, user=Depends(owner_auth.current_user)):
    """Delete several pictures at once.

    The page had one Delete per card, so clearing a dozen test images meant a dozen confirmations.
    """
    owner_auth.require_role(user, "owner")
    rows = await db.pool().fetch(
        "DELETE FROM media_assets WHERE tenant_id=$1 AND id = ANY($2::uuid[]) RETURNING storage_path",
        user["tenant_id"], [str(i) for i in body.ids])
    for row in rows:
        try:
            Path(row["storage_path"]).unlink(missing_ok=True)
        except OSError:
            pass
    return {"deleted": len(rows)}


@router.delete("/assets/{asset_id}")
async def delete_asset(asset_id: UUID, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    row = await db.pool().fetchrow(
        "DELETE FROM media_assets WHERE tenant_id=$1 AND id=$2 RETURNING storage_path",
        user["tenant_id"], asset_id)
    if not row:
        raise HTTPException(404, "Media not found")
    try:
        Path(row["storage_path"]).unlink(missing_ok=True)
    except OSError:
        pass
    return {"ok": True}
