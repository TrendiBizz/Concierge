"""GET /api/robots?url=<host>: fetch a site's robots.txt for the public AI-robots checker.

Contract (pinned by website/tools/robots-ai-check.js and tests/test_robots_api.py):
  200 text/plain  body = robots.txt, headers X-Trendi-Source (final URL) and X-Trendi-Truncated ("1" if cut)
  4xx/5xx JSON    {"error": code, "message": text}; the tool treats error == "not_found" as "no file"
The server only ever requests https://<host>/robots.txt on port 443. Every hop (including redirects,
RFC 9309 s2.3.1.2: up to 5) is resolved, checked to be a public address and pinned to that address.
"""
import ipaddress
import re
from urllib.parse import urljoin, urlsplit

import httpx

from .public_fetch import public_addresses, validate_public_https_url
from .security import RateLimiter

MAX_BYTES = 512 * 1024  # the tool labels truncated output "first 512 KB"
MAX_REDIRECTS = 5
TIMEOUT = httpx.Timeout(8.0, connect=4.0)
USER_AGENT = "TrendiRobotsCheck/1.0 (+https://trendibizz.com/tools/robots-ai-check)"
limiter = RateLimiter(20, 60)  # per visitor IP per minute

_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")


class RobotsError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def clean_host(raw: str) -> str:
    """Accept 'example.com' or a URL; return a lowercase public-looking hostname or raise 400."""
    text = (raw or "").strip()
    if not text or len(text) > 300 or any(ch.isspace() or ord(ch) < 32 for ch in text):
        raise RobotsError(400, "bad_url", "Enter a site such as trendibizz.com.")
    if "://" not in text:
        text = "https://" + text.lstrip("/")
    try:
        parts = urlsplit(text)
        if parts.scheme not in ("http", "https"):
            raise ValueError("scheme")
        host = (parts.hostname or "").rstrip(".").lower()
        port = parts.port
    except ValueError:
        raise RobotsError(400, "bad_url", "Enter a site such as trendibizz.com.") from None
    if parts.username or parts.password or port not in (None, 443):
        raise RobotsError(400, "bad_url", "Only plain https sites on the default port can be checked.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        host = host.encode("idna").decode("ascii") if host and not host.isascii() else host
    else:
        raise RobotsError(400, "bad_url", "Enter a site name, not an IP address.")
    if not _HOST_RE.match(host) or host.endswith((".localhost", ".internal", ".local")):
        raise RobotsError(400, "bad_url", "Enter a site such as trendibizz.com.")
    return host


async def _get(client: httpx.AsyncClient, url: str) -> tuple[httpx.Response, bytes, bool]:
    parts = validate_public_https_url(url)
    try:
        addresses = await public_addresses(parts.hostname)
    except ValueError as error:
        raise RobotsError(422, "blocked", str(error)) from None
    target = httpx.URL(url).copy_with(host=addresses[0])
    async with client.stream(
        "GET", target, headers={"Host": parts.hostname, "User-Agent": USER_AGENT, "Accept": "text/plain, */*;q=0.5"},
        extensions={"sni_hostname": parts.hostname}, follow_redirects=False,
    ) as response:
        body, truncated = bytearray(), False
        if not response.is_redirect:
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    del body[MAX_BYTES:]
                    truncated = True
                    break
        return response, bytes(body), truncated


async def fetch_robots(raw: str, client: httpx.AsyncClient | None = None) -> tuple[str, str, bool]:
    """Return (text, final_url, truncated) or raise RobotsError."""
    host = clean_host(raw)
    url = f"https://{host}/robots.txt"
    owns = client is None
    if owns:
        client = httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False)
    try:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                response, body, truncated = await _get(client, url)
            except RobotsError:
                raise
            except ValueError as error:
                raise RobotsError(422, "blocked", str(error)) from None
            except httpx.TimeoutException:
                raise RobotsError(504, "timeout", "That site took too long to answer.") from None
            except httpx.HTTPError:
                raise RobotsError(502, "fetch_failed", "We could not reach that site.") from None
            if response.is_redirect:
                url = urljoin(url, response.headers.get("location", ""))
                continue
            if 200 <= response.status_code < 300:
                return body.decode("utf-8", errors="replace"), url, truncated
            if 400 <= response.status_code < 500:
                raise RobotsError(404, "not_found", "No robots.txt found at that site. Under RFC 9309 that means crawlers may fetch everything.")
            raise RobotsError(502, "fetch_failed", f"That site's robots.txt returned an error ({response.status_code}).")
        raise RobotsError(502, "too_many_redirects", "That site's robots.txt redirected too many times.")
    finally:
        if owns:
            await client.aclose()
