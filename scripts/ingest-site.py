#!/usr/bin/env python3
"""Load the text of the Concierge website pages into the chat assistant's knowledge base.

  python3 scripts/ingest-site.py [--site DIR] [--slug concierge] [--dry-run]

Reads each .html page, keeps the visible text (drops navigation, footer, scripts, styles), and posts it to the
local API's /admin/tenants/<slug>/ingest-text. Re-running replaces each page's entry, so it is safe to repeat
after the site text changes. Legal pages (privacy, terms, cookies) are skipped on purpose: they are lawyer
drafts and the assistant should not paraphrase them.
The admin token is read from the running API container and never printed.
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

SKIP_PAGES = {"privacy", "terms", "cookies"}
DROP_TAGS = {"script", "style", "nav", "footer", "svg", "noscript", "head", "button", "form"}
BLOCK_TAGS = {"p", "div", "section", "article", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr", "table"}


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth_skip = 0
        self.parts = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in DROP_TAGS and tag != "head":
            self.depth_skip += 1
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in DROP_TAGS and tag != "head" and self.depth_skip:
            self.depth_skip -= 1
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.depth_skip:
            self.parts.append(data)


def page_text(path):
    p = Text()
    p.feed(path.read_text(encoding="utf-8", errors="ignore"))
    body = "".join(p.parts)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in body.splitlines()]
    out, prev = [], ""
    for ln in lines:
        if ln and ln != prev:
            out.append(ln)
        prev = ln
    return p.title.strip(), "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=str(Path.home() / "Downloads/concierge-build/concierge-site"))
    ap.add_argument("--slug", default="concierge")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    token = ""
    if not a.dry_run:
        token = subprocess.run(["docker", "exec", "concierge-api-1", "printenv", "ADMIN_TOKEN"],
                               capture_output=True, text=True, check=True).stdout.strip()
        if not token:
            sys.exit("Could not read the admin token from the API container.")

    pages = sorted(Path(a.site).glob("*.html"))
    total_chunks = 0
    for f in pages:
        label = f.stem
        if label in SKIP_PAGES:
            print(f"skip   {label} (legal)")
            continue
        title, text = page_text(f)
        if len(text) < 80:
            print(f"skip   {label} (no text)")
            continue
        if a.dry_run:
            print(f"would  {label}: {len(text)} chars, title={title!r}")
            continue
        req = urllib.request.Request(
            f"{a.api}/admin/tenants/{a.slug}/ingest-text",
            data=json.dumps({"label": label, "title": title or label, "text": text[:199000]}).encode(),
            headers={"content-type": "application/json", "X-Admin-Token": token},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as r:
            n = json.load(r).get("chunks", 0)
        total_chunks += n
        print(f"loaded {label}: {len(text)} chars -> {n} chunks")
    if not a.dry_run:
        print(f"done: {total_chunks} chunks")


if __name__ == "__main__":
    main()
