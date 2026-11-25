#!/usr/bin/env python3
"""Audit every internal link in website/*.html: target exists, #anchor exists, no button loops.

Run: python3 scripts/seo/link_audit.py   (exit 1 on any problem)
Loop = page A has a .btn link to page B whose .btn links back to A with no form on B
(the 2026-11-25 "Scope a security review" bug: contact -> penetration-testing -> contact).
"""
import re, sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

SITE = Path(__file__).resolve().parents[2] / "website"
# Served by the API / proxy, not files in website/
DYNAMIC = ("/api/", "/studio", "/healthz", "/demo", "/onboarding")


class P(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []; self.ids = set(); self.form = False
    def handle_starttag(self, tag, a):
        a = dict(a)
        if a.get("id"): self.ids.add(a["id"])
        if a.get("name") and tag == "a": self.ids.add(a["name"])
        if tag == "form": self.form = True
        if tag == "a" and a.get("href") is not None:
            self.links.append((a["href"], "btn" in (a.get("class") or "").split()))


def resolve(path: str):
    path = path.rstrip("/") or "/index"
    for c in (SITE / (path.lstrip("/") + ".html"), SITE / path.lstrip("/"), SITE / path.lstrip("/") / "index.html"):
        if c.is_file(): return c
    return None


def main() -> int:
    pages = {}
    for f in sorted(SITE.rglob("*.html")):
        p = P(); p.feed(f.read_text(errors="ignore")); pages[f] = p
    problems, btn = [], {}
    for f, p in pages.items():
        for href, is_btn in p.links:
            if re.match(r"^(mailto:|tel:|https?:|javascript:|data:|sms:)", href) or href == "":
                continue
            u = urlsplit(href)
            tgt = f if not u.path else resolve(u.path.split("?")[0])
            if u.path and tgt is None:
                if u.path.startswith(DYNAMIC): continue
                problems.append(f"DEAD  {f.name}: {href}"); continue
            if u.fragment and tgt and tgt in pages and u.fragment not in pages[tgt].ids and u.fragment != "top":
                problems.append(f"ANCHOR {f.name}: {href} (no id on {tgt.name})")
            if is_btn and tgt and tgt != f:
                btn.setdefault(f, set()).add(tgt)
    for a, outs in btn.items():
        for b in outs:
            if a in btn.get(b, ()) and not pages[b].form and not pages[a].form:
                problems.append(f"LOOP  {a.name} <-> {b.name} (both buttons, neither has a form)")
            elif a in btn.get(b, ()) and not pages[b].form and a.name < b.name:
                problems.append(f"LOOP? {a.name} -> {b.name} -> {a.name}: {b.name} has no form")
    print(f"{len(pages)} pages checked")
    print("\n".join(problems) or "no problems")
    return 1 if problems else 0

sys.exit(main())
