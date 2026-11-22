"""N10 Remainder — Email Professionalism:
- Automated SPF / DKIM / DMARC DNS verification (via Cloudflare DoH, zero dnspython dep)
- Per-tenant DKIM RSA-2048 key generation, encrypted storage, and RFC 6376 signing
- Inbound email attachment byte storage & owner download
- Gmail / Microsoft 365 send-as OAuth (disabled cleanly until credentials are supplied)
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from email.message import EmailMessage
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import crypto_vault, db, owner_auth
from .config import get_settings

router = APIRouter(prefix="/owner/email", tags=["email-n10"])

DOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")
SELECTOR_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB


# ---- DNS TXT lookup seam (tests can monkeypatch `dns_txt`) ----------------------------------
async def dns_txt(name: str) -> list[str]:
    """Resolve TXT records via DNS-over-HTTPS (no extra system/pip dependency)."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(
            "https://cloudflare-dns.com/dns-query",
            params={"name": name, "type": "TXT"},
            headers={"Accept": "application/dns-json"},
        )
    if resp.status_code != 200:
        return []
    answers = (resp.json() or {}).get("Answer") or []
    out: list[str] = []
    for ans in answers:
        data = str(ans.get("data") or "").strip()
        if data.startswith('"') and data.endswith('"'):
            data = data[1:-1].replace('" "', "")
        if data:
            out.append(data)
    return out


async def check_domain_auth(domain: str, selector: str = "concierge") -> dict:
    """Check SPF, DKIM, and DMARC TXT records for a tenant's sending domain."""
    dom = (domain or "").strip().lower()
    sel = (selector or "concierge").strip().lower()
    if not DOMAIN_RE.fullmatch(dom):
        raise ValueError("Invalid domain name")
    if not SELECTOR_RE.fullmatch(sel):
        raise ValueError("Invalid DKIM selector")

    root_txt = await dns_txt(dom)
    dmarc_txt = await dns_txt(f"_dmarc.{dom}")
    dkim_txt = await dns_txt(f"{sel}._domainkey.{dom}")

    spf_rec = next((r for r in root_txt if r.lower().startswith("v=spf1")), "")
    dmarc_rec = next((r for r in dmarc_txt if r.lower().startswith("v=dmarc1")), "")
    dkim_rec = next((r for r in dkim_txt if "v=dkim1" in r.lower() and "p=" in r.lower()), "")

    policy = ""
    if dmarc_rec:
        m = re.search(r"\bp=(none|quarantine|reject)\b", dmarc_rec, re.I)
        policy = m.group(1).lower() if m else ""

    return {
        "domain": dom,
        "spf": {"ok": bool(spf_rec), "record": spf_rec},
        "dkim": {"ok": bool(dkim_rec), "selector": sel, "host": f"{sel}._domainkey.{dom}", "record": dkim_rec},
        "dmarc": {"ok": bool(dmarc_rec), "policy": policy, "record": dmarc_rec},
        "ready": bool(spf_rec and dkim_rec and dmarc_rec),
    }


# ---- Per-tenant DKIM key generation & RFC 6376 signing -------------------------------------
def generate_dkim_rsa_keypair() -> tuple[str, str]:
    """Return (private_pem, dns_txt_value) for a fresh 2048-bit RSA DKIM key."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError as exc:
        raise RuntimeError("DKIM key generation requires cryptography package") from exc
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    pub_der = priv.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pub_b64 = base64.b64encode(pub_der).decode("ascii")
    return priv_pem, f"v=DKIM1; k=rsa; p={pub_b64}"


def _relaxed_body(body: bytes) -> bytes:
    lines = body.replace(b"\r\n", b"\n").split(b"\n")
    canon = [re.sub(rb"[ \t]+", b" ", line.rstrip(b" \t")) for line in lines]
    while canon and canon[-1] == b"":
        canon.pop()
    return (b"\r\n".join(canon) + b"\r\n") if canon else b"\r\n"


def _relaxed_header(name: str, value: str) -> bytes:
    folded = re.sub(r"\r?\n[ \t]+", " ", value)
    collapsed = re.sub(r"[ \t]+", " ", folded).strip()
    return f"{name.lower().strip()}:{collapsed}".encode("utf-8")


def dkim_sign_header(
    msg: EmailMessage,
    *,
    domain: str,
    selector: str,
    private_key_pem: str,
) -> str:
    """Build an RFC 6376 RSA-SHA256 relaxed/relaxed DKIM-Signature header value."""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as exc:
        raise RuntimeError("DKIM signing requires cryptography package") from exc

    raw = msg.as_bytes()
    _, _, body_bytes = raw.partition(b"\r\n\r\n")
    if not body_bytes and b"\n\n" in raw:
        _, _, body_bytes = raw.partition(b"\n\n")
    bh = base64.b64encode(hashlib.sha256(_relaxed_body(body_bytes)).digest()).decode("ascii")

    signed_names = [h for h in ("from", "to", "subject", "date", "message-id") if msg.get(h)]
    header_tag = ":".join(signed_names)
    dkim_unsigned = (
        f"v=1; a=rsa-sha256; c=relaxed/relaxed; d={domain}; s={selector}; "
        f"h={header_tag}; bh={bh}; b="
    )
    canon_headers = b"\r\n".join(
        [_relaxed_header(h, str(msg.get(h, ""))) for h in signed_names]
        + [_relaxed_header("dkim-signature", dkim_unsigned)]
    )
    priv = serialization.load_pem_private_key(private_key_pem.encode("ascii"), password=None)
    sig = priv.sign(canon_headers, padding.PKCS1v15(), hashes.SHA256())
    return dkim_unsigned + base64.b64encode(sig).decode("ascii")


async def active_dkim_for_tenant(tenant_id) -> dict | None:
    row = await db.pool().fetchrow(
        "SELECT domain, selector, private_key_enc FROM tenant_email_dkim "
        "WHERE tenant_id=$1 AND verified",
        tenant_id,
    )
    if not row:
        return None
    pem = crypto_vault.decrypt_text(row["private_key_enc"], aad=f"dkim:{tenant_id}", allow_plaintext=False)
    return {"domain": row["domain"], "selector": row["selector"], "private_key_pem": pem}


# ---- Attachment byte storage ----------------------------------------------------------------
async def store_attachment(
    tenant_id,
    draft_id: int | None,
    filename: str,
    content_type: str,
    data: bytes,
) -> dict:
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise ValueError("Attachment exceeds 10 MB limit")
    clean_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", (filename or "attachment.bin").strip())[:200] or "attachment.bin"
    ctype = (content_type or "application/octet-stream").strip()[:120]
    digest = hashlib.sha256(data).hexdigest()
    row = await db.pool().fetchrow(
        "INSERT INTO email_attachments(tenant_id, draft_id, filename, content_type, size_bytes, sha256, data) "
        "VALUES($1, $2, $3, $4, $5, $6, $7) RETURNING id, created_at",
        tenant_id, draft_id, clean_name, ctype, len(data), digest, data,
    )
    return {
        "id": str(row["id"]),
        "draft_id": draft_id,
        "filename": clean_name,
        "content_type": ctype,
        "size_bytes": len(data),
        "sha256": digest,
        "created_at": row["created_at"].isoformat(),
    }


# ---- Gmail / M365 send-as OAuth (disabled until credentialed) -------------------------------
def send_as_availability() -> dict[str, dict]:
    s = get_settings()
    gmail_ok = bool(s.gmail_oauth_client_id and s.gmail_oauth_client_secret)
    m365_ok = bool(s.ms_client_id and s.ms_client_secret)
    return {
        "gmail": {
            "label": "Gmail Send-As",
            "enabled": gmail_ok,
            "unavailable_reason": "" if gmail_ok else "needs GMAIL_OAUTH_CLIENT_ID and GMAIL_OAUTH_CLIENT_SECRET",
        },
        "m365": {
            "label": "Microsoft 365 Send-As",
            "enabled": m365_ok,
            "unavailable_reason": "" if m365_ok else "needs MS_CLIENT_ID and MS_CLIENT_SECRET",
        },
    }


def build_send_as_authorize_url(provider: str, state: str) -> str:
    s = get_settings()
    avail = send_as_availability()
    if provider not in avail:
        raise HTTPException(404, "Unknown send-as provider")
    if not avail[provider]["enabled"]:
        raise HTTPException(409, f"{avail[provider]['label']} is disabled: {avail[provider]['unavailable_reason']}")
    cb = f"{s.public_base_url.rstrip('/')}/owner/email/send-as/{provider}/callback"
    if provider == "gmail":
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "client_id": s.gmail_oauth_client_id,
            "redirect_uri": cb,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/gmail.send",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        })
    return f"https://login.microsoftonline.com/{s.ms_tenant}/oauth2/v2.0/authorize?" + urlencode({
        "client_id": s.ms_client_id,
        "redirect_uri": cb,
        "response_type": "code",
        "scope": "offline_access Mail.Send",
        "state": state,
    })


# ---- Owner routes ---------------------------------------------------------------------------
@router.get("/domain-check")
async def owner_domain_check(
    domain: str = Query(min_length=3, max_length=253),
    selector: str = Query(default="concierge", max_length=32),
    user: dict = Depends(owner_auth.current_user),
):
    try:
        return await check_domain_auth(domain, selector)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


class DkimGenBody(BaseModel):
    domain: str = Field(min_length=3, max_length=253)
    selector: str = Field(default="concierge", max_length=32)


@router.post("/dkim/generate", status_code=201)
async def owner_dkim_generate(body: DkimGenBody, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    dom = body.domain.strip().lower()
    sel = body.selector.strip().lower()
    if not DOMAIN_RE.fullmatch(dom) or not SELECTOR_RE.fullmatch(sel):
        raise HTTPException(400, "Invalid domain or selector")
    try:
        priv_pem, txt_val = generate_dkim_rsa_keypair()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None
    enc = crypto_vault.encrypt_text(priv_pem, aad=f"dkim:{user['tenant_id']}")
    await db.pool().execute(
        """INSERT INTO tenant_email_dkim(tenant_id, domain, selector, public_txt, private_key_enc, verified)
           VALUES($1, $2, $3, $4, $5, false)
           ON CONFLICT (tenant_id) DO UPDATE SET
               domain=$2, selector=$3, public_txt=$4, private_key_enc=$5, verified=false, updated_at=now()""",
        user["tenant_id"], dom, sel, txt_val, enc,
    )
    return {"domain": dom, "selector": sel, "dns_host": f"{sel}._domainkey.{dom}", "dns_txt": txt_val}


@router.get("/drafts/{draft_id}/attachments")
async def list_draft_attachments(draft_id: int, user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT id, filename, content_type, size_bytes, sha256, created_at "
        "FROM email_attachments WHERE tenant_id=$1 AND draft_id=$2 ORDER BY created_at ASC",
        user["tenant_id"], draft_id,
    )
    return [
        {**dict(r), "id": str(r["id"]), "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


@router.get("/attachments/{attachment_id}")
async def download_attachment(attachment_id: str, user: dict = Depends(owner_auth.current_user)):
    row = await db.pool().fetchrow(
        "SELECT filename, content_type, data FROM email_attachments WHERE id=$1 AND tenant_id=$2",
        attachment_id, user["tenant_id"],
    )
    if not row:
        raise HTTPException(404, "Attachment not found")
    return Response(
        content=bytes(row["data"]),
        media_type=row["content_type"] or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{row["filename"]}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/send-as")
async def get_send_as_status(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    rows = {
        r["provider"]: r for r in await db.pool().fetch(
            "SELECT provider, status, email_address, updated_at FROM tenant_email_oauth WHERE tenant_id=$1",
            user["tenant_id"],
        )
    }
    out = []
    for prov, info in send_as_availability().items():
        r = rows.get(prov)
        out.append({
            "provider": prov,
            **info,
            "status": r["status"] if r else "disconnected",
            "email_address": r["email_address"] if r else "",
        })
    return {"providers": out}


@router.post("/send-as/{provider}/connect")
async def connect_send_as(provider: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    url = build_send_as_authorize_url(provider, state=str(user["tenant_id"]))
    return {"authorize_url": url}
