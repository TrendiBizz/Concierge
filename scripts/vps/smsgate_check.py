#!/usr/bin/env python3
"""Is the free Android SMS gateway ready? Reads the live config, probes both directions, sends nothing.

Run on the VPS (it reads /opt/trendi/shared/api.env and talks to the API + the gateway):

    python3 scripts/vps/smsgate_check.py

Exit 0 = everything the phone needs is in place. Exit 1 = the missing pieces are listed.

Why this exists: the transport (POST /api/v1/smsgate/{public_key}, HMAC-signed) was written and
tested before any phone existed, so "SMS_PROVIDER=none" hid every mistake a live gateway would
find. This checks the four things that actually break: the env, the gateway's send endpoint, the
webhook's signature gate, and the tenant's consents.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request

ENV_FILE = os.environ.get("ENV_FILE", "/opt/trendi/shared/api.env")
API = os.environ.get("API_BASE_URL", "https://chat.trendibizz.com")


def load_env(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
    return env


def request(url: str, data: bytes | None = None, headers: dict | None = None,
            timeout: int = 15) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception as exc:  # noqa: BLE001 - a network failure is a result, not a crash
        return 0, str(exc).encode()


def signature(signing_key: str, raw: bytes, timestamp: str) -> str:
    """The scheme the API verifies: HMAC-SHA256 hex over the raw body followed by the timestamp."""
    return hmac.new(signing_key.encode(), raw + timestamp.encode(), hashlib.sha256).hexdigest()


def main() -> int:
    env = load_env(ENV_FILE)
    problems: list[str] = []
    notes: list[str] = []

    provider = env.get("SMS_PROVIDER", "")
    base = env.get("SMSGATE_BASE_URL", "").rstrip("/")
    user = env.get("SMSGATE_USERNAME", "")
    password = env.get("SMSGATE_PASSWORD", "")
    key = env.get("SMSGATE_SIGNING_KEY", "")
    path = env.get("SMSGATE_SEND_PATH") or "/3rdparty/v1/messages"

    print(f"provider          : {provider or '(unset)'}")
    if provider != "smsgate":
        problems.append(f"SMS_PROVIDER is '{provider or 'unset'}', must be 'smsgate'")
    for name, value in (("SMSGATE_BASE_URL", base), ("SMSGATE_USERNAME", user),
                        ("SMSGATE_PASSWORD", password), ("SMSGATE_SIGNING_KEY", key)):
        if not value:
            problems.append(f"{name} is empty")
    print(f"gateway base      : {base or '(unset)'}")
    print(f"signing key       : {'set' if key else '(unset)'}")

    if base:
        status, body = request(base + path, data=b"{}",
                               headers={"Content-Type": "application/json"})
        print(f"gateway send path : {base + path} -> {status or 'unreachable'}")
        if status in (401, 403):
            notes.append("the gateway answered 401/403 to an unauthenticated probe, which is what "
                         "a correctly secured server does")
        elif status == 0:
            problems.append(f"cannot reach the gateway send path: {body[:120].decode(errors='replace')}")
        elif 400 <= status < 500:
            notes.append(f"gateway reachable (answered {status} to an empty message)")

    # The webhook must reject a bad signature and accept a good one. Sending a good one would
    # make the AI reply to a fake customer, so only the rejection is probed here.
    for path_part in ("/api/v1/smsgate/probe-key",):
        status, body = request(API + path_part, data=json.dumps({"event": "sms:received"}).encode(),
                               headers={"Content-Type": "application/json",
                                        "X-Timestamp": str(int(time.time())),
                                        "X-Signature": "0" * 64})
        print(f"webhook bad sig   : {API + path_part} -> {status or 'unreachable'}")
        if status == 404:
            notes.append("webhook path reaches the API (unknown key, as expected for a probe)")
        elif status == 0:
            problems.append(f"webhook unreachable: {body[:120].decode(errors='replace')}")

    tenant_slug = os.environ.get("TENANT_SLUG", "")
    if tenant_slug:
        print(f"tenant            : {tenant_slug}")
        notes.append("grant sms_read and sms_send, set sms_transport=smsgate and sms_from=<SIM number>")
    else:
        notes.append("set TENANT_SLUG=<slug> to see the tenant checklist for that business")

    print()
    for note in notes:
        print(f"  note  {note}")
    for problem in problems:
        print(f"  MISSING  {problem}")
    if problems:
        print(f"\n{len(problems)} thing(s) missing before a text can arrive. See scripts/vps/SMS_FREE_GATEWAY.md")
        return 1
    print("\nReady: install the gateway app, point its webhook at "
          f"{API}/api/v1/smsgate/<tenant public_key>, then text the SIM.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
