#!/usr/bin/env python3
"""Securely set a SocialSync Meta App Secret in the *local staging* env file.

Run on the authorized Mac.hub terminal. Input is hidden and never printed.
No production or customer settings are changed.
"""
from __future__ import annotations

import getpass
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".private" / "oauth-staging" / "social.env"


def main() -> int:
    if not ENV.exists() or ENV.is_symlink():
        print("ERROR: staging social environment is missing or unsafe; no changes made.")
        return 1
    if ENV.stat().st_mode & 0o077:
        print("ERROR: staging environment permissions are too broad; no changes made.")
        return 1
    value = getpass.getpass("Paste SocialSync App Secret (hidden), then press Return: ").strip()
    if not re.fullmatch(r"[A-Za-z0-9]{16,256}", value):
        print("ERROR: invalid secret format; no changes made.")
        return 1

    original = ENV.read_text(encoding="utf-8").splitlines()
    existing = [line for line in original if line.startswith("SOCIAL_FACEBOOK_CLIENT_SECRET=")]
    if len(existing) > 1:
        print("ERROR: duplicate Meta secret settings; no changes made.")
        return 1
    replacement = f"SOCIAL_FACEBOOK_CLIENT_SECRET={value}"
    updated = []
    found = False
    for line in original:
        if line.startswith("SOCIAL_FACEBOOK_CLIENT_SECRET="):
            updated.append(replacement)
            found = True
        else:
            updated.append(line)
    if not found:
        updated.append(replacement)

    fd, temporary = tempfile.mkstemp(prefix=".social-secret-", dir=ENV.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write("\n".join(updated) + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, ENV)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("SocialSync App Secret saved securely for staging. Publishing remains disabled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
