"""Owner MFA (RFC 6238 TOTP + recovery codes), WebAuthn Passkeys, and session management."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import crypto_vault, db, owner_auth
from .config import get_settings

router = APIRouter(prefix="/owner/auth", tags=["owner-mfa"])

TOTP_PERIOD = 30
TOTP_DIGITS = 6
TOTP_ISSUER = "Trendi Concierge"
MFA_CHALLENGE_MINUTES = 5
WEBAUTHN_CHALLENGE_MINUTES = 5


# ---- RFC 6238 TOTP (pure stdlib) ------------------------------------------------------------
def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def provisioning_uri(secret: str, email: str, issuer: str = TOTP_ISSUER) -> str:
    label = quote(f"{issuer}:{email}", safe=":")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD}"


def totp_code(secret: str, *, for_time: float | None = None, step_offset: int = 0) -> str:
    now = time.time() if for_time is None else for_time
    counter = int(now // TOTP_PERIOD) + step_offset
    padded = secret.upper() + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** TOTP_DIGITS)
    return f"{code_int:0{TOTP_DIGITS}d}"


def verify_totp(secret: str, code: str, *, for_time: float | None = None, window: int = 1,
                last_step: int | None = None) -> int | None:
    """Return the matched time-step integer on valid code (rejecting replays <= last_step), else None."""
    clean = (code or "").strip().replace(" ", "")
    if len(clean) != TOTP_DIGITS or not clean.isdigit():
        return None
    now = time.time() if for_time is None else for_time
    base_step = int(now // TOTP_PERIOD)
    for offset in range(-window, window + 1):
        step = base_step + offset
        if last_step is not None and step <= last_step:
            continue
        expected = totp_code(secret, for_time=now, step_offset=offset)
        if hmac.compare_digest(clean, expected):
            return step
    return None


def _hash_recovery(code: str, salt: str) -> str:
    norm = code.strip().upper().replace("-", "").replace(" ", "")
    return f"{salt}:{hashlib.sha256((salt + ':' + norm).encode()).hexdigest()}"


def generate_recovery_codes(count: int = 8) -> tuple[list[str], list[str]]:
    plain: list[str] = []
    hashed: list[str] = []
    for _ in range(count):
        raw = secrets.token_hex(4).upper()
        formatted = f"{raw[:4]}-{raw[4:]}"
        salt = secrets.token_hex(8)
        plain.append(formatted)
        hashed.append(_hash_recovery(formatted, salt))
    return plain, hashed


def _consume_recovery_code(code: str, stored_hashes: list[str]) -> tuple[bool, list[str]]:
    for idx, entry in enumerate(stored_hashes):
        salt, _, _ = entry.partition(":")
        if not salt:
            continue
        if hmac.compare_digest(_hash_recovery(code, salt), entry):
            return True, stored_hashes[:idx] + stored_hashes[idx + 1:]
    return False, stored_hashes


# ---- MFA state helpers ----------------------------------------------------------------------
async def mfa_methods_for_user(user_id) -> list[str]:
    methods: list[str] = []
    row = await db.pool().fetchrow(
        "SELECT totp_enabled FROM tenant_user_mfa WHERE user_id=$1", user_id
    )
    if row and row["totp_enabled"]:
        methods.append("totp")
    pk_count = await db.pool().fetchval(
        "SELECT count(*) FROM tenant_user_passkeys WHERE user_id=$1", user_id
    )
    if pk_count:
        methods.append("passkey")
    return methods


async def create_mfa_challenge(user_id) -> str:
    token = secrets.token_urlsafe(32)
    await db.pool().execute(
        "INSERT INTO tenant_mfa_challenges(token_hash, user_id, expires_at) "
        "VALUES($1, $2, now() + make_interval(mins => $3))",
        owner_auth.digest(token), user_id, MFA_CHALLENGE_MINUTES,
    )
    return token


# ---- TOTP routes ----------------------------------------------------------------------------
@router.get("/mfa")
async def mfa_status(user: dict = Depends(owner_auth.current_user)):
    row = await db.pool().fetchrow(
        "SELECT totp_enabled, recovery_hashes, enabled_at FROM tenant_user_mfa WHERE user_id=$1",
        user["id"],
    )
    passkeys = await db.pool().fetchval(
        "SELECT count(*) FROM tenant_user_passkeys WHERE user_id=$1", user["id"]
    )
    hashes = json.loads(row["recovery_hashes"]) if (row and isinstance(row["recovery_hashes"], str)) else (row["recovery_hashes"] if row else [])
    return {
        "totp_enabled": bool(row and row["totp_enabled"]),
        "recovery_codes_remaining": len(hashes or []),
        "passkey_count": int(passkeys or 0),
        "enabled_at": row["enabled_at"].isoformat() if (row and row["enabled_at"]) else None,
    }


@router.post("/mfa/totp/setup")
async def totp_setup(user: dict = Depends(owner_auth.current_user)):
    secret = generate_totp_secret()
    enc = crypto_vault.encrypt_text(secret, aad=f"totp:{user['id']}")
    await db.pool().execute(
        """INSERT INTO tenant_user_mfa(user_id, totp_secret_enc, totp_enabled)
           VALUES($1, $2, false)
           ON CONFLICT (user_id) DO UPDATE SET totp_secret_enc=$2, totp_enabled=false, totp_last_step=NULL""",
        user["id"], enc,
    )
    return {"secret": secret, "otpauth_uri": provisioning_uri(secret, user["email"])}


class TotpCodeBody(BaseModel):
    code: str = Field(min_length=6, max_length=20)


@router.post("/mfa/totp/confirm")
async def totp_confirm(body: TotpCodeBody, user: dict = Depends(owner_auth.current_user)):
    row = await db.pool().fetchrow(
        "SELECT totp_secret_enc, totp_last_step FROM tenant_user_mfa WHERE user_id=$1", user["id"]
    )
    if not row or not row["totp_secret_enc"]:
        raise HTTPException(400, "Start TOTP setup first")
    secret = crypto_vault.decrypt_text(row["totp_secret_enc"], aad=f"totp:{user['id']}")
    step = verify_totp(secret, body.code, last_step=row["totp_last_step"])
    if step is None:
        raise HTTPException(400, "Invalid authenticator code")
    plain_codes, hashed_codes = generate_recovery_codes()
    await db.pool().execute(
        "UPDATE tenant_user_mfa SET totp_enabled=true, totp_last_step=$2, recovery_hashes=$3::jsonb, enabled_at=now() "
        "WHERE user_id=$1",
        user["id"], step, json.dumps(hashed_codes),
    )
    return {"totp_enabled": True, "recovery_codes": plain_codes}


@router.post("/mfa/totp/disable")
async def totp_disable(body: TotpCodeBody, user: dict = Depends(owner_auth.current_user)):
    row = await db.pool().fetchrow(
        "SELECT totp_secret_enc, totp_enabled, totp_last_step, recovery_hashes FROM tenant_user_mfa WHERE user_id=$1",
        user["id"],
    )
    if not row or not row["totp_enabled"]:
        raise HTTPException(400, "TOTP is not enabled")
    secret = crypto_vault.decrypt_text(row["totp_secret_enc"], aad=f"totp:{user['id']}")
    hashes = json.loads(row["recovery_hashes"]) if isinstance(row["recovery_hashes"], str) else list(row["recovery_hashes"] or [])
    step = verify_totp(secret, body.code, last_step=row["totp_last_step"])
    used_recovery = False
    if step is None:
        used_recovery, _ = _consume_recovery_code(body.code, hashes)
    if step is None and not used_recovery:
        raise HTTPException(400, "Invalid authenticator or recovery code")
    await db.pool().execute(
        "UPDATE tenant_user_mfa SET totp_enabled=false, totp_secret_enc='', recovery_hashes='[]'::jsonb, enabled_at=NULL "
        "WHERE user_id=$1",
        user["id"],
    )
    return {"totp_enabled": False}


class MfaVerifyBody(BaseModel):
    mfa_token: str = Field(min_length=20, max_length=256)
    code: str = Field(min_length=6, max_length=20)


@router.post("/mfa/verify")
async def mfa_verify(body: MfaVerifyBody, request: Request):
    ip = request.client.host if request.client else "unknown"
    if not await owner_auth.allow_login_attempt(ip, "mfa", body.mfa_token[:16]):
        raise HTTPException(429, "Too many MFA attempts. Try again in a few minutes.")
    challenge = await db.pool().fetchrow(
        "SELECT c.id, c.user_id, u.email, u.role, t.slug "
        "FROM tenant_mfa_challenges c "
        "JOIN tenant_users u ON u.id=c.user_id "
        "JOIN tenants t ON t.id=u.tenant_id "
        "WHERE c.token_hash=$1 AND c.used_at IS NULL AND c.expires_at > now() AND u.active",
        owner_auth.digest(body.mfa_token),
    )
    if not challenge:
        raise HTTPException(401, "MFA challenge expired or invalid")
    row = await db.pool().fetchrow(
        "SELECT totp_secret_enc, totp_enabled, totp_last_step, recovery_hashes FROM tenant_user_mfa WHERE user_id=$1",
        challenge["user_id"],
    )
    if not row or not row["totp_enabled"]:
        raise HTTPException(400, "TOTP is not enabled for this account")
    secret = crypto_vault.decrypt_text(row["totp_secret_enc"], aad=f"totp:{challenge['user_id']}")
    step = verify_totp(secret, body.code, last_step=row["totp_last_step"])
    if step is not None:
        await db.pool().execute(
            "UPDATE tenant_user_mfa SET totp_last_step=$2 WHERE user_id=$1",
            challenge["user_id"], step,
        )
    else:
        hashes = json.loads(row["recovery_hashes"]) if isinstance(row["recovery_hashes"], str) else list(row["recovery_hashes"] or [])
        ok, remaining = _consume_recovery_code(body.code, hashes)
        if not ok:
            raise HTTPException(401, "Invalid authenticator or recovery code")
        await db.pool().execute(
            "UPDATE tenant_user_mfa SET recovery_hashes=$2::jsonb WHERE user_id=$1",
            challenge["user_id"], json.dumps(remaining),
        )
    await db.pool().execute("UPDATE tenant_mfa_challenges SET used_at=now() WHERE id=$1", challenge["id"])
    return await owner_auth.issue_session_for_user(
        challenge["user_id"], challenge["email"], challenge["role"], challenge["slug"],
    )


# ---- Session management ("Sign out all devices") -------------------------------------------
@router.get("/sessions")
async def list_sessions(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT id, created_at, expires_at FROM tenant_sessions "
        "WHERE user_id=$1 AND expires_at > now() ORDER BY created_at DESC",
        user["id"],
    )
    return {
        "sessions": [
            {"id": str(r["id"]), "created_at": r["created_at"].isoformat(), "expires_at": r["expires_at"].isoformat()}
            for r in rows
        ]
    }


@router.post("/logout-all")
async def logout_all_sessions(user: dict = Depends(owner_auth.current_user)):
    deleted = await db.pool().fetchval(
        "WITH d AS (DELETE FROM tenant_sessions WHERE user_id=$1 RETURNING 1) SELECT count(*) FROM d",
        user["id"],
    )
    return {"ok": True, "revoked": int(deleted or 0)}


# ---- Passkeys (WebAuthn) --------------------------------------------------------------------
def _rp_info() -> tuple[str, str]:
    parsed = urlsplit(get_settings().onboarding_url or get_settings().public_base_url)
    rp_id = parsed.hostname or "localhost"
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else "http://localhost:8000"
    return rp_id, origin


def _b64u_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64u_decode(data: str) -> bytes:
    pad = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode((data + pad).encode("ascii"))


@router.get("/passkeys")
async def list_passkeys(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT id, name, credential_id, sign_count, created_at, last_used_at "
        "FROM tenant_user_passkeys WHERE user_id=$1 ORDER BY created_at DESC",
        user["id"],
    )
    return {
        "passkeys": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "credential_id": r["credential_id"],
                "sign_count": r["sign_count"],
                "created_at": r["created_at"].isoformat(),
                "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
            }
            for r in rows
        ]
    }


@router.post("/passkeys/register/options")
async def passkey_register_options(user: dict = Depends(owner_auth.current_user)):
    rp_id, _ = _rp_info()
    challenge = _b64u_encode(secrets.token_bytes(32))
    await db.pool().execute(
        "INSERT INTO webauthn_challenges(challenge, user_id, purpose, expires_at) "
        "VALUES($1, $2, 'register', now() + make_interval(mins => $3))",
        challenge, user["id"], WEBAUTHN_CHALLENGE_MINUTES,
    )
    existing = await db.pool().fetch(
        "SELECT credential_id FROM tenant_user_passkeys WHERE user_id=$1", user["id"]
    )
    return {
        "challenge": challenge,
        "rp": {"id": rp_id, "name": TOTP_ISSUER},
        "user": {
            "id": _b64u_encode(str(user["id"]).encode("utf-8")),
            "name": user["email"],
            "displayName": user["email"],
        },
        "pubKeyCredParams": [
            {"type": "public-key", "alg": -7},    # ES256
            {"type": "public-key", "alg": -257},  # RS256
        ],
        "authenticatorSelection": {"residentKey": "preferred", "userVerification": "preferred"},
        "timeout": 60000,
        "excludeCredentials": [{"type": "public-key", "id": r["credential_id"]} for r in existing],
    }


class PasskeyRegisterVerify(BaseModel):
    credential_id: str = Field(min_length=8, max_length=512)
    public_key_spki: str = Field(min_length=16, max_length=4096)  # base64url SPKI DER
    client_data_json: str = Field(min_length=16, max_length=4096)  # base64url
    name: str = Field(default="Passkey", max_length=80)


@router.post("/passkeys/register/verify", status_code=201)
async def passkey_register_verify(body: PasskeyRegisterVerify, user: dict = Depends(owner_auth.current_user)):
    try:
        client_data = json.loads(_b64u_decode(body.client_data_json).decode("utf-8"))
    except Exception:
        raise HTTPException(400, "Invalid clientDataJSON") from None
    if client_data.get("type") != "webauthn.create":
        raise HTTPException(400, "Unexpected WebAuthn ceremony type")
    _, expected_origin = _rp_info()
    origin = (client_data.get("origin") or "").rstrip("/")
    if origin != expected_origin.rstrip("/"):
        raise HTTPException(400, "Origin mismatch")
    challenge = client_data.get("challenge") or ""
    row = await db.pool().fetchrow(
        "DELETE FROM webauthn_challenges WHERE challenge=$1 AND user_id=$2 AND purpose='register' AND expires_at > now() RETURNING challenge",
        challenge, user["id"],
    )
    if not row:
        raise HTTPException(400, "Registration challenge expired or invalid")
    pk_id = await db.pool().fetchval(
        """INSERT INTO tenant_user_passkeys(user_id, credential_id, public_key_spki, name)
           VALUES($1, $2, $3, $4)
           ON CONFLICT (credential_id) DO NOTHING
           RETURNING id""",
        user["id"], body.credential_id, body.public_key_spki, (body.name or "Passkey").strip()[:80],
    )
    if not pk_id:
        raise HTTPException(409, "Passkey credential already registered")
    return {"id": str(pk_id), "name": body.name, "credential_id": body.credential_id}


@router.delete("/passkeys/{passkey_id}")
async def delete_passkey(passkey_id: str, user: dict = Depends(owner_auth.current_user)):
    res = await db.pool().execute(
        "DELETE FROM tenant_user_passkeys WHERE id=$1 AND user_id=$2", passkey_id, user["id"]
    )
    if res.endswith("0"):
        raise HTTPException(404, "Passkey not found")
    return {"ok": True}


class PasskeyLoginOptionsBody(BaseModel):
    email: str = Field(default="", max_length=320)


@router.post("/passkeys/login/options")
async def passkey_login_options(body: PasskeyLoginOptionsBody):
    rp_id, _ = _rp_info()
    challenge = _b64u_encode(secrets.token_bytes(32))
    allow: list[dict] = []
    user_id = None
    if body.email.strip():
        try:
            clean = owner_auth.clean_email(body.email)
            rows = await db.pool().fetch(
                "SELECT p.credential_id, p.user_id FROM tenant_user_passkeys p "
                "JOIN tenant_users u ON u.id=p.user_id WHERE u.email=$1 AND u.active",
                clean,
            )
            allow = [{"type": "public-key", "id": r["credential_id"]} for r in rows]
            if rows:
                user_id = rows[0]["user_id"]
        except ValueError:
            pass
    await db.pool().execute(
        "INSERT INTO webauthn_challenges(challenge, user_id, purpose, expires_at) "
        "VALUES($1, $2, 'authenticate', now() + make_interval(mins => $3))",
        challenge, user_id, WEBAUTHN_CHALLENGE_MINUTES,
    )
    return {
        "challenge": challenge,
        "rpId": rp_id,
        "timeout": 60000,
        "userVerification": "preferred",
        "allowCredentials": allow,
    }


class PasskeyLoginVerify(BaseModel):
    credential_id: str = Field(min_length=8, max_length=512)
    client_data_json: str = Field(min_length=16, max_length=4096)
    authenticator_data: str = Field(min_length=16, max_length=4096)
    signature: str = Field(min_length=16, max_length=4096)


def _verify_assertion_signature(public_key_spki_b64u: str, auth_data: bytes, client_data_raw: bytes, signature: bytes) -> bool:
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
    except ImportError as exc:
        raise HTTPException(503, "Passkey signature verification requires cryptography package") from exc
    signed_payload = auth_data + hashlib.sha256(client_data_raw).digest()
    pub = serialization.load_der_public_key(_b64u_decode(public_key_spki_b64u))
    try:
        if isinstance(pub, ec.EllipticCurvePublicKey):
            pub.verify(signature, signed_payload, ec.ECDSA(hashes.SHA256()))
        elif isinstance(pub, rsa.RSAPublicKey):
            pub.verify(signature, signed_payload, padding.PKCS1v15(), hashes.SHA256())
        else:
            return False
        return True
    except Exception:
        return False


@router.post("/passkeys/login/verify")
async def passkey_login_verify(body: PasskeyLoginVerify, request: Request):
    ip = request.client.host if request.client else "unknown"
    if not await owner_auth.allow_login_attempt(ip, "passkey", body.credential_id[:24]):
        raise HTTPException(429, "Too many passkey attempts")
    try:
        client_data_raw = _b64u_decode(body.client_data_json)
        client_data = json.loads(client_data_raw.decode("utf-8"))
        auth_data = _b64u_decode(body.authenticator_data)
        sig = _b64u_decode(body.signature)
    except Exception:
        raise HTTPException(400, "Malformed WebAuthn assertion") from None
    if client_data.get("type") != "webauthn.get":
        raise HTTPException(400, "Unexpected WebAuthn ceremony type")
    rp_id, expected_origin = _rp_info()
    if (client_data.get("origin") or "").rstrip("/") != expected_origin.rstrip("/"):
        raise HTTPException(400, "Origin mismatch")
    challenge = client_data.get("challenge") or ""
    ch = await db.pool().fetchrow(
        "DELETE FROM webauthn_challenges WHERE challenge=$1 AND purpose='authenticate' AND expires_at > now() RETURNING challenge",
        challenge,
    )
    if not ch:
        raise HTTPException(401, "Authentication challenge expired or invalid")
    if len(auth_data) < 37:
        raise HTTPException(400, "Truncated authenticatorData")
    rp_hash = auth_data[:32]
    flags = auth_data[32]
    sign_count = struct.unpack(">I", auth_data[33:37])[0]
    if not hmac.compare_digest(rp_hash, hashlib.sha256(rp_id.encode("utf-8")).digest()):
        raise HTTPException(401, "RP ID mismatch")
    if not (flags & 0x01):  # User Present (UP)
        raise HTTPException(401, "User presence required")
    pk = await db.pool().fetchrow(
        "SELECT p.id, p.user_id, p.public_key_spki, p.sign_count, u.email, u.role, t.slug "
        "FROM tenant_user_passkeys p "
        "JOIN tenant_users u ON u.id=p.user_id "
        "JOIN tenants t ON t.id=u.tenant_id "
        "WHERE p.credential_id=$1 AND u.active",
        body.credential_id,
    )
    if not pk:
        raise HTTPException(401, "Unknown passkey")
    if sign_count > 0 and pk["sign_count"] > 0 and sign_count <= pk["sign_count"]:
        raise HTTPException(401, "Passkey counter rollback detected")
    if not _verify_assertion_signature(pk["public_key_spki"], auth_data, client_data_raw, sig):
        raise HTTPException(401, "Invalid passkey signature")
    await db.pool().execute(
        "UPDATE tenant_user_passkeys SET sign_count=$2, last_used_at=now() WHERE id=$1",
        pk["id"], max(sign_count, pk["sign_count"]),
    )
    return await owner_auth.issue_session_for_user(
        pk["user_id"], pk["email"], pk["role"], pk["slug"],
    )
