"""Owner sign-in routes (redeem, invite link, email code, email link, password login, install ticket).

Moved out of app/main.py unchanged; paths and behaviour are identical. main.py re-exports the
handlers and request models so existing imports (tests, tooling) keep working.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from urllib.parse import urlsplit

from .. import mailer, owner_auth

log = logging.getLogger("concierge")
router = APIRouter()


class OwnerRedeem(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=12, max_length=256)


class OwnerLogin(BaseModel):
    slug: str
    email: str
    password: str


class OwnerLinkAccept(BaseModel):
    token: str = Field(min_length=20, max_length=256)


class OwnerEmailLink(BaseModel):
    email: str = Field(max_length=320)


@router.post("/owner/auth/install-ticket")
async def owner_install_ticket(user: dict = Depends(owner_auth.current_user)):
    """The install QR for someone who is already signed in: scan, install, open, signed in."""
    token = await owner_auth.make_install_ticket(user["tenant_id"], user["email"], user["role"])
    site = urlsplit(owner_auth.get_settings().onboarding_url)
    return {"url": f"{site.scheme}://{site.netloc}/studio/install#k={token}",
            "expires_in": owner_auth.INSTALL_MINUTES * 60}


@router.post("/owner/auth/redeem")
async def owner_redeem(body: OwnerRedeem):
    try:
        return await owner_auth.redeem(body.token, body.password)
    except ValueError:
        raise HTTPException(400, "Invalid invitation or password")


@router.post("/owner/auth/invite")
async def owner_accept_invite(body: OwnerLinkAccept):
    """Redeem the one-click link: sign in, no password, no account setup form."""
    try:
        return await owner_auth.accept_invite(body.token)
    except ValueError as error:
        # Say what actually happened. Collapsing every refusal into "expired or already used" sent
        # three separate investigations chasing the wrong fault.
        friendly = {
            "Link not recognised": "That link is not complete. Ask for a new one below and it will work.",
            "This link has expired": "This link has expired. Ask for a new one below.",
            "This link has already been used": "This link has already been used. Ask for a new one below.",
            "Account no longer exists": "That account no longer exists.",
        }
        raise HTTPException(400, friendly.get(str(error), str(error) or "That link did not work.")) from None


class OwnerCodeRequest(BaseModel):
    email: str = Field(max_length=320)


class OwnerCodeVerify(BaseModel):
    email: str = Field(max_length=320)
    code: str = Field(pattern=r"^\d{6}$")


@router.post("/owner/auth/code")
async def owner_email_code(body: OwnerCodeRequest, request: Request):
    """Email a six-digit sign-in code.

    For a web app installed on a phone: the one-click link opens in Safari, not in the installed
    app, and the app has its own storage — so a link cannot sign somebody in there. A code can be
    typed where they already are. The answer never varies, so it cannot be used to discover which
    addresses have accounts.
    """
    ip = request.client.host if request.client else "unknown"
    try:
        email = owner_auth.clean_email(body.email)
    except ValueError:
        return {"ok": True}
    if not await owner_auth.allow_login_attempt(ip, "signin", email):
        raise HTTPException(429, "Too many attempts. Please try again in a few minutes.")
    issued: set[str] = set()
    accounts = await owner_auth.account_emails(email)
    sent = 0
    for account in accounts:
        try:
            code = await owner_auth.make_code(account["tenant_id"], email, account["role"], avoid=issued)
            issued.add(code)
            await mailer.send_email(
                email,
                f"Your Concierge sign-in code — {account.get('name') or 'your business'}",
                "Hello,\n\nYour Concierge sign-in code is:\n\n"
                f"    {code}\n\n"
                f"It works once and expires in {owner_auth.CODE_MINUTES} minutes. "
                "Type it into the Concierge app. If you did not ask for it, ignore this message "
                "and nothing will change.\n\n— Trendi Concierge",
                from_name="Trendi Concierge",
            )
            sent += 1
        except Exception:  # noqa: BLE001 - never reveal delivery detail to a caller
            log.exception("sign-in code could not be sent for %s", account.get("slug"))
    if accounts and not sent:
        # A known address where nothing went out must not look like success: the app would claim
        # "we emailed a code". Only reachable for an address that has an account, so it reveals
        # nothing an attacker could not already get from the 200 path being absent for unknowns.
        raise HTTPException(503, "The sign-in code could not be sent. Please try again.")
    return {"ok": True}


@router.post("/owner/auth/code/verify")
async def owner_verify_code(body: OwnerCodeVerify, request: Request):
    """Redeem the six-digit code for a session. Rate-limited, email-bound, single use, ten minutes."""
    ip = request.client.host if request.client else "unknown"
    raw_email = body.email.strip().lower()
    if not await owner_auth.allow_login_attempt(ip, "code", raw_email):
        raise HTTPException(429, "Too many attempts. Please try again in a few minutes.")
    try:
        email = owner_auth.clean_email(body.email)
    except ValueError:
        raise HTTPException(400, "That code is not right. Check the email and try again.") from None
    try:
        return await owner_auth.accept_invite(body.code, expected_email=email, expected_purpose="code")
    except ValueError as error:
        friendly = {
            "Link not recognised": "That code is not right. Check the email and try again.",
            "This link has expired": "That code has expired. Ask for a new one.",
        }
        raise HTTPException(400, friendly.get(str(error), str(error) or "That code did not work.")) from None


@router.post("/owner/auth/link")
async def owner_email_link(body: OwnerEmailLink, request: Request):
    """Email a one-click sign-in link.

    The answer never varies, so this cannot be used to discover which addresses have accounts.
    """
    ip = request.client.host if request.client else "unknown"
    try:
        email = owner_auth.clean_email(body.email)
    except ValueError:
        return {"ok": True}
    if not await owner_auth.allow_login_attempt(ip, "signin", email):
        raise HTTPException(429, "Too many attempts. Please try again in a few minutes.")
    for account in await owner_auth.account_emails(email):
        try:
            token = await owner_auth.make_invite(account["tenant_id"], email, account["role"], "recovery")
            await mailer.send_email(
                email,
                f"Your Concierge sign-in link — {account.get('name') or 'your business'}",
                "Hello,\n\nUse this private link to open your Concierge workspace. "
                "There is no password.\n\n"
                f"{owner_auth.invitation_link(token)}\n\n"
                "The link works once and expires in 24 hours. If you did not ask for it, "
                "you can ignore this message.\n\n— Trendi Concierge",
                from_name="Trendi Concierge",
            )
        except Exception:  # noqa: BLE001 - never reveal delivery detail to a caller
            log.exception("sign-in link could not be sent for %s", account.get("slug"))
    return {"ok": True}


@router.post("/owner/auth/login")
async def owner_login(body: OwnerLogin, request: Request):
    ip = request.client.host if request.client else "unknown"
    if not await owner_auth.allow_login_attempt(ip, body.slug, body.email):
        raise HTTPException(429, "Too many login attempts")
    try:
        token = await owner_auth.login_for_tenant(body.slug, body.email, body.password)
    except ValueError:
        token = None
    if token is None:
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": token, "token_type": "bearer", "expires_in": 43200}
