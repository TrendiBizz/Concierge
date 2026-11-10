"""Best-effort content scanning: Rspamd spam score and ClamAV antivirus.

Failures return None and never block or hide a message. Results only add risk
flags; the human-review boundary is unchanged.
"""
import asyncio
import base64
import socket
import struct

import httpx

from .config import get_settings

MAX_SCAN_BYTES = 200_000
SPAM_HIGH = 6.0
SPAM_MEDIUM = 4.0


def classify(scan: dict | None) -> tuple[str, list[str]]:
    """Map scanner output to a risk floor and flags. Pure; no I/O."""
    if not scan:
        return "low", []
    flags: list[str] = []
    risk = "low"
    if scan.get("virus"):
        flags.append("virus")
        risk = "high"
    score = scan.get("spam_score")
    if isinstance(score, (int, float)):
        if score >= SPAM_HIGH:
            flags.append("spam_high")
            risk = "high"
        elif score >= SPAM_MEDIUM:
            flags.append("spam_medium")
            risk = "medium" if risk == "low" else risk
    return risk, flags


async def scan(raw_b64: str) -> dict | None:
    if not raw_b64:
        return None
    try:
        raw = base64.b64decode(raw_b64)
    except ValueError:
        return None
    if not raw or len(raw) > MAX_SCAN_BYTES:
        return None
    settings = get_settings()
    result: dict = {"virus": None, "spam_score": None, "action": None}
    if settings.rspamd_url:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(settings.rspamd_url, content=raw)
                if response.status_code == 200:
                    data = response.json()
                    result["spam_score"] = data.get("score")
                    result["action"] = data.get("action")
        except (httpx.HTTPError, ValueError):
            pass
    if settings.clamav_host:
        try:
            result["virus"] = await asyncio.to_thread(
                _clamav, raw, settings.clamav_host, settings.clamav_port)
        except OSError:
            pass
    if result["virus"] is None and result["spam_score"] is None:
        return None
    return result


def _clamav(raw: bytes, host: str, port: int) -> str | None:
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall(b"zINSTREAM\0")
        for offset in range(0, len(raw), 4096):
            chunk = raw[offset:offset + 4096]
            sock.sendall(struct.pack("!I", len(chunk)) + chunk)
        sock.sendall(struct.pack("!I", 0))
        response = b""
        while True:
            part = sock.recv(4096)
            if not part:
                break
            response += part
            if b"\0" in part or b"\n" in part:
                break
    text = response.decode("utf-8", "replace").strip("\0 \r\n")
    return text if "FOUND" in text else None
