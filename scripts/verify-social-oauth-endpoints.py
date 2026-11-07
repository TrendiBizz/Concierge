#!/usr/bin/env python3
"""Read-only OAuth preflight. Never prints secrets or issues publishing requests."""
from __future__ import annotations
import argparse
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

PATH = "/owner/social/oauth/callback"
PORTAL = "/owner-ui"


def check(base: str) -> int:
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/"):
        print("FAIL: Provide only the verified public HTTPS owner API origin")
        return 2
    origin = f"https://{parsed.netloc}"
    failed = False
    for path, expected in ((PATH, "concierge-social-oauth"), (PORTAL, "social-panel")):
        address = origin + path
        try:
            request = urllib.request.Request(address, headers={"User-Agent": "Concierge-OAuth-Preflight/1.0"})
            with urllib.request.urlopen(request, timeout=8, context=ssl.create_default_context()) as response:
                body = response.read(400_000).decode("utf-8", errors="replace")
                ok = response.status == 200 and expected in body and urllib.parse.urlsplit(response.geturl()).netloc == parsed.netloc
                print(("PASS" if ok else "FAIL") + f": {path} (HTTP {response.status})")
                if not ok:
                    failed = True
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"FAIL: {path}: {type(exc).__name__} (inspect HTTPS, DNS, and deployment)")
            failed = True
    if failed:
        print("NOT READY: do not register this URL with Meta yet.")
        return 1
    print("PUBLIC ROUTES READY. Register exactly:", origin + PATH)
    print("Then test a real provider callback in Development mode, without enabling publishing.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True, help="The public https:// hostname serving Concierge owner-ui")
    return check(parser.parse_args().origin)


if __name__ == "__main__":
    sys.exit(main())
