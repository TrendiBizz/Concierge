import hmac
import secrets
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request
from fastapi.responses import HTMLResponse

from .config import get_settings

# Content-Security-Policy profiles for HTML and API responses served by Concierge.
# None of these allow 'unsafe-inline' or 'unsafe-eval' in script-src.
STUDIO_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'wasm-unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "media-src 'self' blob: data:; "
    "connect-src 'self' blob:; "
    "worker-src 'self' blob:; "
    "manifest-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'"
)

STRICT_DOC_CSP = (
    "default-src 'none'; "
    "style-src 'unsafe-inline'; "
    "img-src 'self' data:; "
    "form-action 'self'; "
    "base-uri 'none'; "
    "object-src 'none'; "
    "frame-ancestors 'none'"
)

DEMO_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "connect-src 'self' https://api.x.ai wss://api.x.ai; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'"
)

API_CSP = "default-src 'none'; frame-ancestors 'none'"

DEFAULT_PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=()"
DEMO_PERMISSIONS_POLICY = "camera=(), microphone=(self), geolocation=()"


def html_with_script_nonce(
    raw_html: str,
    *,
    headers: dict[str, str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Serve an HTML document with a fresh per-request CSP nonce on its inline <script> tags."""
    nonce = secrets.token_urlsafe(18)
    rendered = raw_html.replace("<script>", f'<script nonce="{nonce}">')
    csp = (
        f"default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        f"style-src 'self' 'unsafe-inline'; "
        f"img-src 'self' data: blob:; "
        f"font-src 'self' data:; "
        f"media-src 'self' blob: data:; "
        f"connect-src 'self'; "
        f"worker-src 'self'; "
        f"manifest-src 'self'; "
        f"base-uri 'self'; "
        f"form-action 'self'; "
        f"object-src 'none'; "
        f"frame-ancestors 'none'"
    )
    resp_headers = {
        "Cache-Control": "no-store",
        "Content-Security-Policy": csp,
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": DEFAULT_PERMISSIONS_POLICY,
    }
    if headers:
        resp_headers.update(headers)
    return HTMLResponse(rendered, status_code=status_code, headers=resp_headers)


def apply_security_headers(path: str, response) -> None:
    """Attach clickjacking, MIME-sniff, referrer, permissions, and CSP headers consistently."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    content_type = (response.headers.get("content-type") or "").lower()
    is_html = "text/html" in content_type

    if path.startswith("/demo/"):
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", DEMO_PERMISSIONS_POLICY)
        if is_html:
            response.headers.setdefault("Content-Security-Policy", DEMO_CSP)
        return

    if path == "/studio" or path.startswith("/studio/"):
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", DEFAULT_PERMISSIONS_POLICY)
        if is_html:
            response.headers.setdefault("Content-Security-Policy", STUDIO_CSP)
        return

    if (
        path.startswith("/quote/")
        or path.startswith("/invoice/")
        or path.startswith("/receipt/")
        or path == "/privacy"
        or path.startswith("/privacy/")
        or path.startswith("/guide/")
        or path.startswith("/report/")
        or path.startswith("/api/v1/unsubscribe/")
        or path.startswith("/upload/")
    ):
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", DEFAULT_PERMISSIONS_POLICY)
        if is_html:
            response.headers.setdefault("Content-Security-Policy", STRICT_DOC_CSP)
        return

    if path in ("/owner-ui", "/onboarding", "/admin-ui") or path.startswith("/owner/") or path.startswith("/api/v1/device-sms/"):
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", DEFAULT_PERMISSIONS_POLICY)
        if is_html:
            response.headers.setdefault("Content-Security-Policy", STRICT_DOC_CSP)
        else:
            response.headers.setdefault("Content-Security-Policy", API_CSP)
        return

    if is_html:
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", DEFAULT_PERMISSIONS_POLICY)
        response.headers.setdefault("Content-Security-Policy", STRICT_DOC_CSP)


async def require_admin(request: Request = None, x_admin_token: str = Header(default="")) -> dict:
    from . import admin_operators

    operator = await admin_operators.verify_operator_token(x_admin_token)
    if operator is None:
        expected = get_settings().admin_token
        if not expected:
            raise HTTPException(status_code=503, detail="ADMIN_TOKEN is not configured")
        if not hmac.compare_digest(x_admin_token.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="Invalid admin token")
        operator = {"id": None, "name": "legacy-admin-token", "email": "", "role": "superadmin", "legacy": True}
    if request is not None:
        request.state.admin_operator = operator
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            ip = request.client.host if request.client else ""
            await admin_operators.record_audit(
                operator,
                action=f"{request.method} {request.url.path}",
                path=request.url.path,
                method=request.method,
                ip=ip,
            )
    return operator


class RateLimiter:
    """Sliding-window limiter held in process memory (fine for a single API container)."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        if len(self._hits) > 20_000:
            self._prune(now)
        return True

    def _prune(self, now: float) -> None:
        for key in [k for k, q in self._hits.items() if not q or q[-1] <= now - self.window]:
            del self._hits[key]
