#!/usr/bin/env python3
"""Who was invited and has never signed in: the call list, not a report.

Usage (on the box):
    python3 scripts/vps/pending_invites.py            # list everyone still pending
    python3 scripts/vps/pending_invites.py --json     # machine-readable

Reads ADMIN_TOKEN from the environment, then falls back to /opt/trendi/shared/api.env, so it can
be run from cron or by hand without exporting anything. The question it answers is deliberately
"has this person signed in", not "did they open the email": an open is fetched by privacy proxies
and security scanners, a sign-in is a fact.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ENV_FILE = "/opt/trendi/shared/api.env"
API = os.environ.get("API_BASE", "http://127.0.0.1:8000")


def admin_token() -> str:
    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if token:
        return token
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("ADMIN_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    sys.exit(f"ADMIN_TOKEN not set and {ENV_FILE} is unreadable")


def fetch(path: str, token: str):
    request = urllib.request.Request(API + path, headers={"X-Admin-Token": token})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    rows = fetch("/admin/pending-invites", admin_token())
    if "--json" in sys.argv:
        print(json.dumps(rows, indent=2, default=str))
        return 0
    if not rows:
        print("Every invited owner has signed in.")
        return 0
    print(f"{len(rows)} owner(s) invited and never signed in:\n")
    for row in rows:
        print(f"  {row['slug']:24} {row['email']:38} invited {str(row['invited_at'])[:10]}"
              f"  last email {str(row.get('last_email_sent') or '-')[:16]}"
              f"  engaged {str(row.get('last_engaged') or '-')[:16]}")
    print("\nNext: re-invite with POST /admin/tenants/<slug>/owner-invite, then phone them.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"API refused the request: {exc.code} {exc.read()[:200]!r}") from None
    except urllib.error.URLError as exc:
        raise SystemExit(f"could not reach {API}: {exc.reason}") from None
