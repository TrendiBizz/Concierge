#!/usr/bin/env python3
"""Post the latest Trendi LinkedIn draft to the Trendi company page.

Drafts come from Concierge `trendi-linkedin-weekly`:
  ~/.workwatch/reports/concierge/trendi-desk/linkedin/<YYYY-MM-DD>.md

The first run needs a one-time login in the dedicated browser profile:
  scripts/social/linkedin-login.sh

Usage:
  python scripts/social/linkedin_weekly_post.py --dry-run
  python scripts/social/linkedin_weekly_post.py
  python scripts/social/linkedin_weekly_post.py --file path/to/draft.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

HOME = Path.home()
PROFILE = HOME / ".trendi-linkedin-profile"
DRAFT_DIR = HOME / ".workwatch/reports/concierge/trendi-desk/linkedin"
COMPANY_ID = "146891966"
ADMIN_URL = f"https://www.linkedin.com/company/{COMPANY_ID}/admin/feed/posts?share=true"
LOG_DIR = HOME / ".workwatch/reports/concierge/trendi-desk/linkedin"
FORBIDDEN = ("free", "guaranteed", "rank #1", "number one", "best in the world")
POSTED = LOG_DIR / ".posted.json"


def latest_draft(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    files = sorted(DRAFT_DIR.glob("*.md"))
    if not files:
        raise SystemExit(f"no draft found in {DRAFT_DIR}")
    latest = files[-1]
    age_days = (time.time() - latest.stat().st_mtime) / 86400
    if age_days > 4:
        raise SystemExit(f"latest draft is {age_days:.1f} days old; not posting a stale draft")
    return latest


def clean(text: str) -> str:
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if re.match(r"^#{1,6}\s", s):
            continue
        if re.match(r"^(status|profile|schedule|approval|source):", s, re.I):
            continue
        if s.startswith("```"):
            continue
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 \2", s)
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"\*(.+?)\*", r"\1", s)
        lines.append(s)
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return out


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def already_posted(text: str) -> bool:
    try:
        data = json.loads(POSTED.read_text())
    except (OSError, ValueError):
        return False
    return digest(text) in data


def mark_posted(text: str) -> None:
    try:
        data = json.loads(POSTED.read_text())
    except (OSError, ValueError):
        data = {}
    data[digest(text)] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    POSTED.write_text(json.dumps(data, indent=2), encoding="utf-8")


def validate(text: str) -> None:
    if not text:
        raise SystemExit("draft is empty after cleaning")
    if len(text) > 3000:
        raise SystemExit(f"draft is {len(text)} chars; LinkedIn limit is 3000")
    low = text.lower()
    for word in FORBIDDEN:
        if word in low:
            raise SystemExit(f"draft contains forbidden phrase: {word!r}")


def post(text: str, images: list[Path], *, dry_run: bool) -> str:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(PROFILE),
            channel="chrome",
            headless=False,
            viewport={"width": 1440, "height": 1000},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(ADMIN_URL, wait_until="domcontentloaded", timeout=60000)
            if "login" in page.url or "checkpoint" in page.url:
                raise SystemExit("LinkedIn session is not logged in; run scripts/social/linkedin-login.sh")

            page.wait_for_selector('div[role="dialog"]', timeout=45000)
            editor = page.locator('div[contenteditable="true"][aria="Text editor for creating content"]').first
            editor.click()
            page.keyboard.insert_text(text)
            page.wait_for_timeout(1000)

            if images:
                page.get_by_label("Add media").click()
                page.wait_for_selector('input[type="file"]', timeout=15000)
                page.set_input_files('input[type="file"]', [str(p) for p in images])
                page.get_by_role("button", name="Next", exact=True).click()
                page.wait_for_timeout(3000)

            post_btn = page.get_by_role("button", name="Post", exact=True)
            post_btn.wait_for(state="visible", timeout=15000)
            if post_btn.is_disabled():
                raise SystemExit("Post button is disabled; the composer did not accept the draft")
            if dry_run:
                return "DRY RUN: composer filled, not posted"
            post_btn.click()
            page.wait_for_selector("text=Post successful", timeout=60000)
            return "POSTED: LinkedIn showed Post successful"
        except PlaywrightTimeout as exc:
            shot = LOG_DIR / f"linkedin-error-{dt.datetime.now():%Y%m%d-%H%M%S}.png"
            try:
                page.screenshot(path=str(shot), full_page=True)
            except Exception:
                pass
            raise SystemExit(f"timed out: {exc}; screenshot: {shot}") from exc
        finally:
            context.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--images", nargs="*", default=[])
    args = ap.parse_args()

    draft = latest_draft(args.file)
    text = clean(draft.read_text(encoding="utf-8", errors="replace"))
    validate(text)
    images = [Path(p).expanduser() for p in args.images]
    print(f"draft: {draft}")
    print(f"chars: {len(text)}")
    if already_posted(text) and not args.dry_run:
        raise SystemExit("this exact draft was already posted; not posting a duplicate")
    result = post(text, images, dry_run=args.dry_run)
    if result.startswith("POSTED"):
        mark_posted(text)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
