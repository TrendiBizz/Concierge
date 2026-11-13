"""Tenant-scoped owner authentication. Opaque tokens are stored only as SHA-256 hashes.
No invitations or recovery tokens are emailed automatically.
"""
import hashlib
import hmac
import re
import secrets

from fastapi import Header, HTTPException
from . import db
from .config import get_settings

ROLES = {"viewer": 0, "editor": 1, "owner": 2}
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ITERATIONS = 600_000

# An account opened from a one-click link never sets a password. The column is NOT NULL and
# verify_password rejects anything that is not a pbkdf2 digest, so a marker is enough: no
# password can ever match it. The customer never sees a password field again.
NO_PASSWORD = "no-password"
# A one-click session lasts long enough that a customer does not sign in again each visit.
SESSION_DAYS = 30


def invitation_link(token: str) -> str:
    # Fragment is never sent to the server or included in HTTP access logs.
    return get_settings().onboarding_url + "#invite=" + token


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password: str) -> str:
    if len(password) < 12 or len(password) > 256:
        raise ValueError("Password must contain 12-256 characters")
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256:{ITERATIONS}:{salt.hex()}:{derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        kind, rounds, salt, expected = stored.split(":")
        if kind != "pbkdf2_sha256":
            return False
        computed = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(computed, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def clean_email(email: str) -> str:
    value = email.strip().lower()
    if len(value) > 320 or not EMAIL.fullmatch(value):
        raise ValueError("Invalid email")
    return value


async def make_invite(tenant_id, email: str, role: str, purpose: str = "invite") -> str:
    if role not in ROLES or purpose not in ("invite", "recovery"):
        raise ValueError("Invalid role or purpose")
    email = clean_email(email)
    token = secrets.token_urlsafe(32)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            if purpose == "recovery":
                user = await conn.fetchrow("SELECT role FROM tenant_users WHERE tenant_id=$1 AND email=$2 AND active", tenant_id, email)
                if not user:
                    raise ValueError("Active user not found")
                role = user["role"]
            await conn.execute(
                "UPDATE tenant_invites SET used_at=now() WHERE tenant_id=$1 AND email=$2 AND purpose=$3 AND used_at IS NULL",
                tenant_id, email, purpose,
            )
            await conn.execute(
                "INSERT INTO tenant_invites(tenant_id,email,role,purpose,token_hash,expires_at) "
                "VALUES($1,$2,$3,$4,$5,now()+interval '24 hours')",
                tenant_id, email, role, purpose, digest(token),
            )
    return token


async def owner_link(tenant_id, email: str) -> dict:
    """Give an operator a working link for a client's owner, whether or not one exists yet.

    `recovery` deliberately refuses to invent a user. That is right for "I lost my password" and
    wrong for the operator's real first step — creating a client and handing the owner their way in.
    On 13 Nov a brand-new tenant answered "Active user not found" and the owner could not be given
    access at all, so onboarding could not start.
    """
    email = clean_email(email)
    user = await db.pool().fetchrow(
        "SELECT role FROM tenant_users WHERE tenant_id=$1 AND email=$2 AND active", tenant_id, email)
    if user:
        token = await make_invite(tenant_id, email, user["role"], "recovery")
        return {"token": token, "purpose": "recovery", "role": user["role"]}
    token = await make_invite(tenant_id, email, "owner", "invite")
    return {"token": token, "purpose": "invite", "role": "owner"}


async def redeem(token: str, password: str) -> dict:
    pwd = password_hash(password)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            invitation = await conn.fetchrow(
                "SELECT i.*,t.slug AS tenant_slug FROM tenant_invites i "
                "JOIN tenants t ON t.id=i.tenant_id "
                "WHERE i.token_hash=$1 AND i.used_at IS NULL "
                "AND i.expires_at>now() FOR UPDATE OF i", digest(token),
            )
            if not invitation:
                raise ValueError("Invalid or expired invitation")
            existing = await conn.fetchrow(
                "SELECT id FROM tenant_users WHERE tenant_id=$1 AND email=$2",
                invitation["tenant_id"], invitation["email"],
            )
            if invitation["purpose"] == "recovery" and not existing:
                raise ValueError("Account no longer exists")
            if invitation["purpose"] == "invite" and existing:
                raise ValueError("Account already exists")
            if existing:
                await conn.execute(
                    "UPDATE tenant_users SET password_hash=$2, active=true WHERE id=$1",
                    existing["id"], pwd,
                )
                user_id = existing["id"]
                await conn.execute("DELETE FROM tenant_sessions WHERE user_id=$1", user_id)
            else:
                user_id = await conn.fetchval(
                    "INSERT INTO tenant_users(tenant_id,email,role,password_hash) "
                    "VALUES($1,$2,$3,$4) RETURNING id",
                    invitation["tenant_id"], invitation["email"], invitation["role"], pwd,
                )
            await conn.execute("UPDATE tenant_invites SET used_at=now() WHERE id=$1", invitation["id"])
    return {"email": invitation["email"], "role": invitation["role"],
            "slug": invitation["tenant_slug"]}


async def accept_invite(token: str) -> dict:
    """Sign someone in from their one-click link; no password is created or asked for.

    The link is single use and expires in 24 hours. It arrives in the URL *fragment*, so a mail
    scanner that pre-fetches the message cannot consume it: only the browser's JavaScript POST
    redeems it, and the token never appears in a server access log.
    """
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            invitation = await conn.fetchrow(
                "SELECT i.*,t.slug AS tenant_slug FROM tenant_invites i "
                "JOIN tenants t ON t.id=i.tenant_id "
                "WHERE i.token_hash=$1 AND i.used_at IS NULL "
                "AND i.expires_at>now() FOR UPDATE OF i", digest(token),
            )
            if not invitation:
                raise ValueError("Invalid or expired link")
            existing = await conn.fetchrow(
                "SELECT id FROM tenant_users WHERE tenant_id=$1 AND email=$2",
                invitation["tenant_id"], invitation["email"],
            )
            if invitation["purpose"] == "recovery" and not existing:
                raise ValueError("Account no longer exists")
            if invitation["purpose"] == "invite" and existing:
                raise ValueError("Account already exists")
            if existing:
                user_id = existing["id"]
                await conn.execute("UPDATE tenant_users SET active=true WHERE id=$1", user_id)
                await conn.execute("DELETE FROM tenant_sessions WHERE user_id=$1", user_id)
            else:
                user_id = await conn.fetchval(
                    "INSERT INTO tenant_users(tenant_id,email,role,password_hash) "
                    "VALUES($1,$2,$3,$4) RETURNING id",
                    invitation["tenant_id"], invitation["email"], invitation["role"], NO_PASSWORD,
                )
            await conn.execute("UPDATE tenant_invites SET used_at=now() WHERE id=$1", invitation["id"])
            session = secrets.token_urlsafe(32)
            await conn.execute(
                "INSERT INTO tenant_sessions(user_id,token_hash,expires_at) "
                "VALUES($1,$2,now()+make_interval(days=>$3::int))",
                user_id, digest(session), SESSION_DAYS,
            )
    return {"access_token": session, "token_type": "bearer",
            "expires_in": SESSION_DAYS * 86400, "email": invitation["email"],
            "role": invitation["role"], "slug": invitation["tenant_slug"]}


async def account_emails(email: str) -> list[dict]:
    """Every active account for one address. Usually one; never assume it."""
    rows = await db.pool().fetch(
        "SELECT u.tenant_id,u.email,u.role,t.slug,t.name FROM tenant_users u "
        "JOIN tenants t ON t.id=u.tenant_id WHERE u.email=$1 AND u.active",
        clean_email(email),
    )
    return [dict(row) for row in rows]


async def allow_login_attempt(ip: str, slug: str, email: str) -> bool:
    """Atomic shared-DB throttle, per IP and per (IP,tenant,email) pair.

    Count attempts even on success; never trust forwarded IP headers.
    A database failure fails closed rather than bypassing the limiter.
    """
    identities = ("ip:" + ip, "identity:" + ip + ":" + slug.lower() + ":" + email.lower())
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            for identity in identities:
                key = digest(identity)
                attempts = await conn.fetchval(
                    """INSERT INTO owner_login_limits(key_hash,attempts,window_until)
                       VALUES ($1,1,now()+interval '5 minutes')
                       ON CONFLICT (key_hash) DO UPDATE SET
                         attempts=CASE WHEN owner_login_limits.window_until<=now()
                           THEN 1 ELSE owner_login_limits.attempts+1 END,
                         window_until=CASE WHEN owner_login_limits.window_until<=now()
                           THEN now()+interval '5 minutes'
                           ELSE owner_login_limits.window_until END
                       RETURNING attempts""", key,
                )
                if attempts > 8:
                    return False
    return True


async def login_for_tenant(slug: str, email: str, password: str) -> str | None:
    email = clean_email(email)
    user = await db.pool().fetchrow(
        "SELECT u.id,u.password_hash FROM tenant_users u JOIN tenants t ON t.id=u.tenant_id "
        "WHERE t.slug=$1 AND u.email=$2 AND u.active", slug, email,
    )
    if not user or not verify_password(password, user["password_hash"]):
        return None
    token = secrets.token_urlsafe(32)
    await db.pool().execute(
        "INSERT INTO tenant_sessions(user_id,token_hash,expires_at) "
        "VALUES($1,$2,now()+interval '12 hours')", user["id"], digest(token),
    )
    return token


async def current_user(authorization: str = Header(default="")) -> dict:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 256:
        raise HTTPException(401, "Bearer authentication required")
    row = await db.pool().fetchrow(
        "SELECT u.id,u.tenant_id,u.email,u.role,t.slug,t.name "
        "FROM tenant_sessions s JOIN tenant_users u ON u.id=s.user_id "
        "JOIN tenants t ON t.id=u.tenant_id "
        "WHERE s.token_hash=$1 AND s.expires_at>now() AND u.active",
        digest(token),
    )
    if not row:
        raise HTTPException(401, "Session expired or invalid")
    return dict(row)


def require_role(user: dict, role: str) -> None:
    if ROLES[user["role"]] < ROLES[role]:
        raise HTTPException(403, "Insufficient permissions")


async def logout(token: str) -> None:
    await db.pool().execute("DELETE FROM tenant_sessions WHERE token_hash=$1", digest(token))
