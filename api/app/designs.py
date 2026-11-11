"""Design and plan uploads for quotation takeoff.

Files are stored outside the database per tenant. Uploads are untrusted: the
name is reduced to a safe extension, size is capped, and ClamAV scans the bytes
when configured. Parsing/takeoff is a separate step.
"""
import hashlib
import os
import re
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from . import db, owner_auth
from .config import get_settings

router = APIRouter(prefix="/owner/designs", tags=["designs"])

ALLOWED = {".pdf", ".dwg", ".dxf", ".ifc", ".glb", ".gltf", ".obj", ".stl", ".3dm", ".step", ".stp"}
MAX_BYTES = 50 * 1024 * 1024
NAME = re.compile(r"^[A-Za-z0-9._ -]{1,120}$")


def safe_filename(value: str) -> str:
    name = os.path.basename((value or "").strip())
    if not name or not NAME.fullmatch(name):
        raise HTTPException(400, "Use a simple file name")
    if Path(name).suffix.lower() not in ALLOWED:
        raise HTTPException(400, "Unsupported design format")
    return name


@router.get("")
async def listing(user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    rows = await db.pool().fetch(
        "SELECT id,filename,content_type,size_bytes,status,summary,created_at "
        "FROM design_uploads WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 200",
        user["tenant_id"])
    return [dict(row) for row in rows]


@router.post("", status_code=201)
async def upload(request: Request, filename: str, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    name = safe_filename(filename)
    body = await request.body()
    if not body or len(body) > MAX_BYTES:
        raise HTTPException(413, "Design file must be between 1 byte and 50 MB")
    settings = get_settings()
    if settings.clamav_host:
        try:
            from .email_scan import _clamav
            import asyncio
            virus = await asyncio.to_thread(_clamav, body, settings.clamav_host, settings.clamav_port)
            if virus:
                raise HTTPException(400, "The file did not pass the virus scan")
        except HTTPException:
            raise
        except Exception:
            pass  # scanner unavailable: keep the file, parsing stays manual
    digest = hashlib.sha256(body).hexdigest()
    folder = Path(settings.designs_dir) / str(user["tenant_id"])
    folder.mkdir(parents=True, exist_ok=True)
    row = await db.pool().fetchrow(
        """INSERT INTO design_uploads(tenant_id,uploaded_by,filename,content_type,size_bytes,sha256,storage_path)
           VALUES($1,$2,$3,$4,$5,$6,'') RETURNING id""",
        user["tenant_id"], user.get("email", ""), name,
        request.headers.get("content-type", "application/octet-stream")[:100], len(body), digest)
    path = folder / f"{row['id']}{Path(name).suffix.lower()}"
    path.write_bytes(body)
    await db.pool().execute("UPDATE design_uploads SET storage_path=$2 WHERE id=$1", row["id"], str(path))
    return {"id": row["id"], "filename": name, "size_bytes": len(body), "sha256": digest}


@router.get("/{design_id}/file")
async def download(design_id: UUID, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    row = await db.pool().fetchrow(
        "SELECT filename,content_type,storage_path FROM design_uploads WHERE tenant_id=$1 AND id=$2",
        user["tenant_id"], design_id)
    if not row or not Path(row["storage_path"]).is_file():
        raise HTTPException(404, "Design not found")
    return FileResponse(row["storage_path"], media_type=row["content_type"], filename=row["filename"])


@router.delete("/{design_id}")
async def remove(design_id: UUID, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    row = await db.pool().fetchrow(
        "DELETE FROM design_uploads WHERE tenant_id=$1 AND id=$2 RETURNING storage_path",
        user["tenant_id"], design_id)
    if not row:
        raise HTTPException(404, "Design not found")
    try:
        Path(row["storage_path"]).unlink(missing_ok=True)
    except OSError:
        pass
    return {"ok": True}
