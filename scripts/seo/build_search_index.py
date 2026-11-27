#!/usr/bin/env python3
"""Build website/ui/search-index.json for the Cmd-K site search (website/ui/trendi-ui.js commandMenu).

Only pages listed in website/sitemap.xml are indexed, so noindex and draft pages never show up in search.
Label = the page <title> without the " | Trendi" suffix; keywords = the meta description words.

  python3 scripts/seo/build_search_index.py          # write the index
  python3 scripts/seo/build_search_index.py --check  # exit 1 if the committed index is stale
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parents[2] / "website"
OUT = SITE / "ui" / "search-index.json"
ORIGIN = "https://trendibizz.com"

GROUPS = (
    ("/tools/", "Free tool"),
    ("/news", "News"),
    ("/research", "Research"),
    ("/trendi-vs-", "Compare"),
    ("-alternative", "Compare"),
)


def group_for(path: str) -> str:
    for marker, name in GROUPS:
        if marker in path:
            return name
    return "Page"


def source_for(path: str) -> Path:
    rel = path.strip("/")
    if not rel:
        return SITE / "index.html"
    direct = SITE / f"{rel}.html"
    return direct if direct.exists() else SITE / rel / "index.html"


def build() -> dict:
    locs = re.findall(r"<loc>([^<]+)</loc>", (SITE / "sitemap.xml").read_text(encoding="utf-8"))
    pages = []
    for loc in locs:
        path = loc[len(ORIGIN):] or "/"
        if re.search(r"\.(xml|txt|json)$", path):
            continue  # feeds and machine files are not pages
        src = source_for(path)
        if not src.exists():
            raise SystemExit(f"sitemap lists {path} but {src} is missing")
        text = src.read_text(encoding="utf-8")
        title = re.search(r"<title>([^<]*)</title>", text)
        desc = re.search(r'<meta(?=[^>]*\bname="description")[^>]*\bcontent="([^"]*)"', text)
        label = html.unescape(title.group(1) if title else path).split(" | ")[0].strip()
        words = sorted(set(re.findall(r"[a-z0-9]{4,}", html.unescape(desc.group(1)).lower()))) if desc else []
        pages.append({"label": label, "href": path, "group": group_for(path), "keywords": words[:24]})
    return {"generated_from": "website/sitemap.xml", "pages": pages}


def main() -> int:
    data = json.dumps(build(), ensure_ascii=False, indent=1) + "\n"
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != data:
            print("search-index.json is stale: run python3 scripts/seo/build_search_index.py", file=sys.stderr)
            return 1
        print("search-index.json up to date")
        return 0
    OUT.write_text(data, encoding="utf-8")
    print(f"wrote {OUT.relative_to(SITE.parent)} ({data.count('\"href\"')} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
