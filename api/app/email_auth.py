"""Client for the Rust email-auth sidecar (DKIM + DMARC alignment).

The sidecar verifies the raw message cryptographically. It never authorises an
action: its verdict only feeds the existing risk classification. Any failure
returns None so the header hints and quarantine behaviour still apply.
"""
import httpx

from .config import get_settings

MAX_RAW_B64 = 700_000


async def verify(raw_b64: str) -> dict | None:
    url = get_settings().email_auth_url
    if not url or not raw_b64 or len(raw_b64) > MAX_RAW_B64:
        return None
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(url, json={"raw_b64": raw_b64})
            if response.status_code != 200:
                return None
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("error"):
        return None
    return data


def merge(auth: dict | None, verified: dict) -> dict:
    """Prefer the cryptographically verified verdict over untrusted header hints."""
    merged = dict(auth or {})
    for key in ("dkim", "dmarc"):
        value = verified.get(key)
        if value in ("pass", "fail", "none"):
            merged[key] = value
    if verified.get("from"):
        merged["verified_from"] = verified["from"]
    # A passing signature whose d= domain aligns with From authenticates the
    # sender even when the domain publishes no DMARC record. Kept separate from
    # the dmarc label so `dmarc=none` is not read as "not authenticated".
    merged["aligned"] = "yes" if verified.get("aligned") else "no"
    merged["verified_by"] = "email-auth"
    return merged
