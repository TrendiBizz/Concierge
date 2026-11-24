#!/usr/bin/env python3
"""Test customer accounts "Test 1".."Test 3" for outside onboarding testers.

Usage (on the box, via admin API on 127.0.0.1; reads ADMIN_TOKEN like pending_invites.py):
    python3 scripts/vps/test_tenants.py create                      # idempotent: make test-1..test-3
    python3 scripts/vps/test_tenants.py invite 1 [--email a@b.com]  # fresh single-use link, 24h, NOT emailed
    python3 scripts/vps/test_tenants.py delete                      # remove test-1..test-3 and their data

Nothing here sends mail, SMS or calls: invitations are minted with send_email=false and the link is
printed for the operator to hand to a tester. Links expire after 24 hours, so mint one when the
tester is ready. Tenants carry no site_url, billing or real data. The default owner email is a
reserved example.com address; pass --email when the tester wants their own login identity.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ENV_FILE = "/opt/trendi/shared/api.env"
API = os.environ.get("API_BASE", "http://127.0.0.1:8000")
SLUGS = {1: "test-1", 2: "test-2", 3: "test-3"}


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


def call(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"X-Admin-Token": admin_token()}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def existing() -> set[str]:
    return {row["slug"] for row in call("GET", "/admin/tenants")}


def create() -> None:
    have = existing()
    for number, slug in SLUGS.items():
        if slug in have:
            print(f"exists   {slug}")
            continue
        tenant = call("POST", "/admin/tenants", {"name": f"Test {number}", "slug": slug})
        print(f"created  {tenant['slug']}  ({tenant['name']})")


def invite(number: int, email: str | None) -> None:
    slug = SLUGS[number]
    if slug not in existing():
        sys.exit(f"{slug} does not exist; run: test_tenants.py create")
    email = email or f"test{number}@example.com"
    result = call("POST", f"/admin/tenants/{slug}/owner-invitations",
                  {"email": email, "role": "owner", "send_email": False})
    print(f"{slug}  owner {email}\n{result['invitation_url']}\n(single-use, expires in {result['expires_in_hours']}h)")


def delete() -> None:
    have = existing()
    for slug in SLUGS.values():
        if slug in have:
            call("DELETE", f"/admin/tenants/{slug}")
            print(f"deleted  {slug}")


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("create", "invite", "delete"):
        print(__doc__)
        return 2
    if argv[0] == "create":
        create()
    elif argv[0] == "delete":
        delete()
    else:
        if len(argv) < 2 or not argv[1].isdigit() or int(argv[1]) not in SLUGS:
            print("usage: test_tenants.py invite 1|2|3 [--email addr]")
            return 2
        email = argv[argv.index("--email") + 1] if "--email" in argv[2:] else None
        invite(int(argv[1]), email)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"API refused the request: {exc.code} {exc.read()[:200]!r}") from None
    except urllib.error.URLError as exc:
        raise SystemExit(f"could not reach {API}: {exc.reason}") from None
