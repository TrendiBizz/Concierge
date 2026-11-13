"""Design and plan uploads for quotation takeoff.

Files are stored outside the database per tenant. Uploads are untrusted: the
name is reduced to a safe extension, size is capped, and ClamAV scans the bytes
when configured. Parsing/takeoff is a separate step.
"""
import hashlib
import html
import json
import subprocess
import sys
import os
import re
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
import secrets
from fastapi.responses import FileResponse

from . import db, owner_auth
import asyncio
from .config import get_settings

router = APIRouter(prefix="/owner/designs", tags=["designs"])
public_router = APIRouter(prefix="/api/v1/public-design", tags=["designs"])
page_router = APIRouter(tags=["designs"])

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


async def _save(tenant_id, uploaded_by: str, filename: str, content_type: str, body: bytes) -> dict:
    name = safe_filename(filename)
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
            pass
    digest = hashlib.sha256(body).hexdigest()
    folder = Path(settings.designs_dir) / str(tenant_id)
    folder.mkdir(parents=True, exist_ok=True)
    row = await db.pool().fetchrow(
        """INSERT INTO design_uploads(tenant_id,uploaded_by,filename,content_type,size_bytes,sha256,storage_path)
           VALUES($1,$2,$3,$4,$5,$6,'') RETURNING id""",
        tenant_id, uploaded_by, name, content_type[:100], len(body), digest)
    path = folder / f"{row['id']}{Path(name).suffix.lower()}"
    path.write_bytes(body)
    await db.pool().execute("UPDATE design_uploads SET storage_path=$2 WHERE id=$1", row["id"], str(path))
    return {"id": row["id"], "filename": name, "size_bytes": len(body), "sha256": digest}


@router.post("", status_code=201)
async def upload(request: Request, filename: str, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    return await _save(user["tenant_id"], user.get("email", ""), filename,
                       request.headers.get("content-type", "application/octet-stream"), await request.body())


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


def _takeoff(path: str) -> dict:
    """Measure an IFC in a child process, so a model that crashes the parser cannot crash the API."""
    import subprocess

    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.ifc_takeoff", path],
            capture_output=True, text=True, timeout=120,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("reading this model took too long") from None
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "{}")
    except (ValueError, IndexError):
        payload = {}
    if result.returncode != 0 or "error" in payload:
        if "error" in payload:
            raise RuntimeError(payload["error"])
        if result.returncode < 0:
            raise RuntimeError("the IFC reader crashed on this file (signal %s); re-export it as IFC4 and try again" % (-result.returncode))
        raise RuntimeError((result.stderr or "the IFC reader failed").strip().splitlines()[-1][:200])
    return payload


@router.post("/{design_id}/takeoff")
async def takeoff(design_id: UUID, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    row = await db.pool().fetchrow(
        "SELECT storage_path,filename FROM design_uploads WHERE tenant_id=$1 AND id=$2",
        user["tenant_id"], design_id)
    if not row or not Path(row["storage_path"]).is_file():
        raise HTTPException(404, "Design not found")
    if not row["filename"].lower().endswith(".ifc"):
        raise HTTPException(400, "Takeoff is available for IFC models")
    try:
        summary = await asyncio.to_thread(_takeoff, row["storage_path"])
    except ImportError:
        raise HTTPException(503, "IFC takeoff is not installed") from None
    except Exception as error:  # noqa: BLE001 - malformed client models are expected
        await db.pool().execute("UPDATE design_uploads SET status='failed' WHERE id=$1", design_id)
        raise HTTPException(422, "This IFC could not be read: " + str(error)[:160]) from None
    await db.pool().execute(
        "UPDATE design_uploads SET status='parsed', summary=$2::jsonb WHERE id=$1", design_id, json.dumps(summary))
    return summary


@router.post("/link")
async def customer_link(user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    token = secrets.token_urlsafe(24)
    await db.pool().execute(
        "INSERT INTO design_links(token,tenant_id,created_by,expires_at) VALUES($1,$2,$3,now()+interval '7 days')",
        token, user["tenant_id"], user.get("email", ""))
    return {"token": token, "url": "/upload/" + token, "expires_in_days": 7}


@page_router.get("/upload/{token}", response_class=HTMLResponse, include_in_schema=False)
async def upload_page(token: str):
    row = await db.pool().fetchrow("SELECT tenant_id,expires_at FROM design_links WHERE token=$1 AND expires_at>now()", token)
    if not row:
        raise HTTPException(404, "This upload link has expired")
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex, nofollow, noai, noimageai"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Send your plans</title><style>body{{font-family:system-ui,sans-serif;max-width:560px;margin:8vh auto;padding:24px}}input,button{{font:inherit;margin-top:12px}}</style></head>
<body><h1>Send your plans</h1><p>Upload the original plan drawings or a 3D model. PDF, DWG, IFC, GLB and common formats up to 50 MB.</p>
<input id="file" type="file" accept=".pdf,.dwg,.dxf,.ifc,.glb,.gltf,.obj,.stl,.3dm,.step,.stp"><br>
<button id="send">Send securely</button><p id="status" role="status"></p>
<script>
document.getElementById('send').addEventListener('click',async()=>{{
 const f=document.getElementById('file').files[0]; if(!f){{document.getElementById('status').textContent='Choose a file first.';return;}}
 document.getElementById('status').textContent='Uploading…';
 const r=await fetch('/api/v1/public-design/{html.escape(token)}?filename='+encodeURIComponent(f.name),{{method:'POST',headers:{{'Content-Type':f.type||'application/octet-stream'}},body:f}});
 const d=await r.json().catch(()=>({{}}));
 document.getElementById('status').textContent=r.ok?'Thank you. Your plans were received.':(d.detail||'Upload failed.');
}});
</script></body></html>""")


@public_router.post("/{token}", status_code=201)
async def public_upload(request: Request, token: str, filename: str):
    row = await db.pool().fetchrow("SELECT tenant_id FROM design_links WHERE token=$1 AND expires_at>now()", token)
    if not row:
        raise HTTPException(404, "This upload link has expired")
    return await _save(row["tenant_id"], "customer", filename,
                       request.headers.get("content-type", "application/octet-stream"), await request.body())
