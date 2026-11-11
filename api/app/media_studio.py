"""Marketing media via a private Imagination Studio host.

The Studio (Apache-2.0, local Mac/DGX Spark app) runs on its own machine and is
reached over a private network. Concierge queues stills/clips, stores the job
link and proxies finished files for owner review. Nothing is published from here.
"""
from __future__ import annotations

import mimetypes
from typing import Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from uuid import UUID

from . import db, owner_auth
from .config import get_settings

router = APIRouter(prefix="/owner/media", tags=["media"])


def configured() -> bool:
    settings = get_settings()
    return bool(settings.studio_url and settings.studio_key)


async def _call(method: str, path: str, body: dict | None = None) -> dict | list:
    if not configured():
        raise HTTPException(503, "The marketing media studio is not connected yet")
    settings = get_settings()
    headers = {"X-Studio-Key": settings.studio_key, "Accept": "application/json"}
    async with httpx.AsyncClient(base_url=settings.studio_url.rstrip("/"), timeout=60.0) as client:
        response = await client.request(method, path, json=body, headers=headers)
    if response.status_code >= 400:
        detail = response.text[:300] or f"Studio HTTP {response.status_code}"
        raise HTTPException(502, detail)
    return response.json()


def params_for(kind: str, prompt: str, count: int, preset: str | None, image_model: str | None) -> dict:
    if kind == "still":
        params = {"prompt": prompt, "count": max(1, min(12, count))}
        if preset:
            params["preset"] = preset
        if image_model:
            params["image_model"] = image_model
        return params
    return {"prompt": prompt, "preset": preset} if preset else {"prompt": prompt}


class JobCreate(BaseModel):
    kind: Literal["still", "clip"]
    prompt: str = Field(min_length=3, max_length=2000)
    title: str = Field(default="", max_length=160)
    count: int = Field(default=1, ge=1, le=12)
    preset: str | None = Field(default=None, max_length=32)
    image_model: str | None = Field(default=None, max_length=64)


async def _refresh(row) -> dict:
    if row["studio_job_id"] and row["status"] in ("queued", "running"):
        job = await _call("GET", f"/api/jobs/{quote(row['studio_job_id'])}")
        status = job.get("status") if job.get("status") in ("queued", "running", "done", "failed", "cancelled") else row["status"]
        outputs = job.get("outputs") or []
        await db.pool().execute(
            "UPDATE media_jobs SET status=$2, outputs=$3, error=$4, updated_at=now() WHERE id=$1",
            row["id"], status, outputs, (job.get("error") or "")[:500] or None)
        row = dict(row, status=status, outputs=outputs)
    return dict(row)


@router.get("/status")
async def status(user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    if not configured():
        return {"configured": False, "detail": "Connect a Studio host to enable marketing media."}
    state = await _call("GET", "/api/state")
    return {"configured": True, "platform": state.get("platform_label") or state.get("platform"),
            "version": state.get("version"), "engine": state.get("engine"),
            "image_models": state.get("image_models") or []}


@router.get("/jobs")
async def jobs(user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    rows = await db.pool().fetch(
        "SELECT * FROM media_jobs WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 100", user["tenant_id"])
    return [await _refresh(row) for row in rows]


@router.post("/jobs", status_code=201)
async def create(body: JobCreate, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if not configured():
        raise HTTPException(503, "The marketing media studio is not connected yet")
    studio_kind = "scout" if body.kind == "still" else "video"
    title = body.title.strip() or ("Marketing still" if body.kind == "still" else "Marketing clip")
    job = await _call("POST", "/api/jobs", {
        "kind": studio_kind, "title": title[:160],
        "params": params_for(body.kind, body.prompt, body.count, body.preset, body.image_model),
    })
    row = await db.pool().fetchrow(
        """INSERT INTO media_jobs(tenant_id,studio_job_id,kind,title,prompt,status,outputs,created_by)
           VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *""",
        user["tenant_id"], job.get("id"), body.kind, title, body.prompt,
        job.get("status") if job.get("status") in ("queued", "running", "done", "failed", "cancelled") else "queued",
        job.get("outputs") or [], user.get("email", ""))
    return dict(row)


@router.get("/jobs/{job_id}")
async def one(job_id: UUID, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    row = await db.pool().fetchrow("SELECT * FROM media_jobs WHERE tenant_id=$1 AND id=$2", user["tenant_id"], job_id)
    if not row:
        raise HTTPException(404, "Media job not found")
    return await _refresh(row)


@router.get("/jobs/{job_id}/file")
async def file(job_id: UUID, path: str, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    row = await db.pool().fetchrow("SELECT outputs FROM media_jobs WHERE tenant_id=$1 AND id=$2", user["tenant_id"], job_id)
    if not row or path not in (row["outputs"] or []):
        raise HTTPException(404, "Media file not found")
    if not configured():
        raise HTTPException(503, "The marketing media studio is not connected yet")
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.studio_url.rstrip("/"), timeout=120.0) as client:
        response = await client.get(f"/files/{quote(path)}", headers={"X-Studio-Key": settings.studio_key})
    if response.status_code != 200:
        raise HTTPException(404, "Media file not available")
    media = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return Response(response.content, media_type=media)


@router.post("/jobs/{job_id}/cancel")
async def cancel(job_id: UUID, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    row = await db.pool().fetchrow("SELECT * FROM media_jobs WHERE tenant_id=$1 AND id=$2", user["tenant_id"], job_id)
    if not row:
        raise HTTPException(404, "Media job not found")
    if row["studio_job_id"] and row["status"] in ("queued", "running"):
        try:
            await _call("POST", f"/api/jobs/{quote(row['studio_job_id'])}/cancel")
        except HTTPException:
            pass
    await db.pool().execute("UPDATE media_jobs SET status='cancelled', updated_at=now() WHERE id=$1", job_id)
    return {"ok": True}
