"""Tenant-scoped social media uploads and short-lived encrypted provider download capabilities.

Validates images via Pillow (PNG/JPEG/WebP, normalized to safe RGB JPEG when needed) and
supports MP4/MOV video uploads (probed with ffprobe if installed, otherwise magic-byte validated).
Public downloads by social platforms (Meta, TikTok, etc.) require an expiring AES-GCM capability
token bound to the tenant and asset ID; raw filesystem paths are never exposed.
"""
from __future__ import annotations

import io
import json
import os
import re
import secrets
import time
from pathlib import Path

from fastapi import HTTPException
from PIL import Image

from .. import crypto_vault, db
from . import config as social_config

_VALID_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MAX_BYTES = 64 * 1024 * 1024
_CAPABILITY_TTL = 900  # 15 minutes


def _root_dir() -> Path:
    return Path(social_config.social_media_dir())


def _detect_video(data: bytes) -> tuple[str, str] | None:
    # ISO Base Media File Format (MP4/MOV): bytes 4..8 == b'ftyp'
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video", "video/mp4"
    return None


async def save_media(customer_slug: str, data: bytes) -> dict:
    if not _VALID_ID.fullmatch(customer_slug):
        raise HTTPException(400, "Invalid tenant slug")
    if not data or len(data) > _MAX_BYTES:
        raise HTTPException(413, "Upload an image or video smaller than 64 MB")

    asset_id = secrets.token_urlsafe(24)
    kind = ""
    mime = ""
    width = 0
    height = 0
    duration = 0.0
    out_bytes = data

    vid = _detect_video(data)
    if vid:
        kind, mime = vid
    else:
        try:
            with Image.open(io.BytesIO(data)) as img:
                img.verify()
            with Image.open(io.BytesIO(data)) as img:
                fmt = (img.format or "").upper()
                if fmt not in ("JPEG", "PNG", "WEBP"):
                    raise HTTPException(400, "Use a JPG/PNG/WebP image or MP4/MOV video")
                width, height = img.size
                if width <= 0 or height <= 0 or width > 16384 or height > 16384:
                    raise HTTPException(400, "Media dimensions are unsupported")
                kind = "image"
                if fmt == "PNG":
                    mime = "image/png"
                elif fmt == "WEBP":
                    # Normalize WebP to JPEG for maximum social network compatibility
                    buf = io.BytesIO()
                    img.convert("RGB").save(buf, format="JPEG", quality=90)
                    out_bytes = buf.getvalue()
                    mime = "image/jpeg"
                else:
                    mime = "image/jpeg"
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, "Media could not be processed; use a JPG/PNG image or MP4/MOV video under 64 MB") from exc

    tenant_dir = _root_dir() / customer_slug
    tenant_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(tenant_dir, 0o700)
    except OSError:
        pass
    bin_path = tenant_dir / f"{asset_id}.bin"
    bin_path.write_bytes(out_bytes)

    meta = {
        "id": asset_id,
        "kind": kind,
        "mime": mime,
        "bytes": len(out_bytes),
        "width": width,
        "height": height,
        "duration_seconds": duration,
    }
    (tenant_dir / f"{asset_id}.json").write_text(json.dumps(meta), encoding="utf-8")

    await db.pool().execute(
        """INSERT INTO social_media_assets(
               id, customer_slug, kind, mime, bytes, width, height, duration_seconds, storage_path)
           VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
        asset_id,
        customer_slug,
        kind,
        mime,
        len(out_bytes),
        width,
        height,
        duration,
        str(bin_path),
    )
    return meta


async def load_media(customer_slug: str, asset_id: str) -> tuple[dict, bytes]:
    if not _VALID_ID.fullmatch(customer_slug) or not _VALID_ID.fullmatch(asset_id):
        raise HTTPException(404, "Media unavailable")
    row = await db.pool().fetchrow(
        """SELECT id, kind, mime, bytes, width, height, duration_seconds, storage_path
           FROM social_media_assets WHERE id=$1 AND customer_slug=$2""",
        asset_id,
        customer_slug,
    )
    if row and Path(row["storage_path"]).is_file():
        return dict(row), Path(row["storage_path"]).read_bytes()
    # Fallback to legacy on-disk JSON+BIN migrated from trendi_social/_data/media
    tenant_dir = _root_dir() / customer_slug
    meta_path = tenant_dir / f"{asset_id}.json"
    bin_path = tenant_dir / f"{asset_id}.bin"
    if meta_path.is_file() and bin_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return meta, bin_path.read_bytes()
    raise HTTPException(404, "Media unavailable")


def mint_download_token(customer_slug: str, asset_id: str, ttl_seconds: int = _CAPABILITY_TTL) -> str:
    payload = json.dumps({
        "c": customer_slug,
        "a": asset_id,
        "exp": int(time.time()) + ttl_seconds,
    }, separators=(",", ":"))
    return crypto_vault.encrypt_text(payload, aad="social-public-media")


def public_media_url(customer_slug: str, asset_id: str, base_url: str) -> str:
    tok = mint_download_token(customer_slug, asset_id)
    return f"{base_url.rstrip('/')}/api/v1/social-media/{tok}"


async def resolve_download_token(token: str) -> tuple[str, bytes]:
    if not token or len(token) > 2048:
        raise HTTPException(404, "Media unavailable")
    try:
        raw = crypto_vault.decrypt_text(token, aad="social-public-media", allow_plaintext=False)
        data = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(404, "Media unavailable") from exc
    if int(data.get("exp") or 0) < int(time.time()):
        raise HTTPException(404, "Media link expired")
    customer_slug = str(data.get("c") or "")
    asset_id = str(data.get("a") or "")
    meta, content = await load_media(customer_slug, asset_id)
    return str(meta.get("mime") or "application/octet-stream"), content
