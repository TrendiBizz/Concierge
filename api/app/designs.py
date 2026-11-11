"""Design and plan uploads for quotation takeoff.

Files are stored outside the database per tenant. Uploads are untrusted: the
name is reduced to a safe extension, size is capped, and ClamAV scans the bytes
when configured. Parsing/takeoff is a separate step.
"""
import hashlib
import json
import os
import re
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from . import db, owner_auth
import asyncio
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


def _takeoff(path: str) -> dict:
    import ifcopenshell
    model = ifcopenshell.open(path)
    walls = list(model.by_type("IfcWall")) + list(model.by_type("IfcWallStandardCase"))
    gross = net = opening_area = 0.0
    for wall in walls:
        for rel in getattr(wall, "IsDefinedBy", []):
            if not rel.is_a("IfcRelDefinesByProperties"):
                continue
            prop = rel.RelatingPropertyDefinition
            if prop is None or not prop.is_a("IfcElementQuantity"):
                continue
            for quantity in prop.Quantities or []:
                if not quantity.is_a("IfcQuantityArea"):
                    continue
                name = quantity.Name or ""
                value = float(quantity.AreaValue or 0)
                if "GrossSideArea" in name:
                    gross += value
                elif "NetSideArea" in name:
                    net += value
    openings = list(model.by_type("IfcOpeningElement"))
    for opening in openings:
        for rel in getattr(opening, "IsDefinedBy", []):
            if not rel.is_a("IfcRelDefinesByProperties"):
                continue
            prop = rel.RelatingPropertyDefinition
            if prop is None or not prop.is_a("IfcElementQuantity"):
                continue
            for quantity in prop.Quantities or []:
                if quantity.is_a("IfcQuantityArea"):
                    opening_area += float(quantity.AreaValue or 0)
    note = "" if gross or net else "This IFC has no wall area quantities. Measure manually or export quantities from the authoring tool."
    return {"wall_count": len(walls), "gross_wall_area_m2": round(gross, 2),
            "net_wall_area_m2": round(net, 2), "opening_count": len(openings),
            "opening_area_m2": round(opening_area, 2),
            "net_cladding_area_m2": round(max(net - opening_area, 0), 2) if net else None,
            "note": note}


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
