#!/usr/bin/env python3
"""Check that product sources are owned by Concierge and not introduced into the public site.

With --website-root, report legacy product files in the website repository.
The transitional --allow-legacy flag permits old, tracked copies during safe
cutover, but never allows new product additions there.
"""
from __future__ import annotations
import argparse
import subprocess
from pathlib import Path

PRODUCT_PREFIXES = (
    "concierge-stack/agent/",
    "concierge-stack/social-service/",
    "concierge-stack/socialsync/",
    "concierge-stack/hermes/",
    "concierge-stack/livekit/",
)
REQUIRED_PATHS = (
    "concierge-stack/agent/agent.py",
    "concierge-stack/social-service/Cargo.toml",
    "concierge-stack/social-service/src/main.rs",
    "concierge-stack/docker-compose.voice.yml",
    "concierge-stack/backup.sh",
    "concierge-stack/restore-test.sh",
)

def git_files(path: Path, *args: str) -> set[str]:
    return set(filter(None, subprocess.check_output(
        ["git", "-C", str(path), "ls-files", "-z", *args]
    ).decode().split("\0")))

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--website-root", type=Path)
    parser.add_argument("--allow-legacy", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    missing = [name for name in REQUIRED_PATHS if not (root / name).is_file()]
    if missing:
        print("Missing Concierge-owned product files:", *missing, sep="\n  ")
        return 1
    if args.website_root:
        website = args.website_root.resolve()
        tracked = git_files(website)
        leaked = sorted(p for p in tracked if p.startswith(PRODUCT_PREFIXES))
        if leaked:
            if not args.allow_legacy:
                print("Product files remain tracked in website:", *leaked, sep="\n  ")
                return 1
            print(f"TRANSITION ONLY: {len(leaked)} legacy website product paths remain tracked")
            # Reject newly staged additions to forbidden site paths.
            added = subprocess.check_output(
                ["git", "-C", str(website), "diff", "--cached", "--name-only",
                 "--diff-filter=A", "-z"]
            ).decode().split("\0")
            new_leaks = [p for p in added if p.startswith(PRODUCT_PREFIXES)]
            if new_leaks:
                print("New website product files prohibited:", *new_leaks, sep="\n  ")
                return 1
    print("Concierge repository ownership check passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
