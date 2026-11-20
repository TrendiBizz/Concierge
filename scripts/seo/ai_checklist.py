#!/usr/bin/env python3
"""AI-search readiness audit for the site's own HTML pages.

Scores every page in `website/` against the checklist items that a machine can verify, so the monthly SEO audit
has a repeatable AI-visibility number per page. It reads files only: no network, no writes outside `--out`.

What is scored, and what is not
-------------------------------
Each check is one of:
  * automatic  - answered from the HTML (headings, tables, lists, JSON-LD, dates, link targets, alt text).
  * heuristic  - a keyword or length rule that suggests the item is covered. Labelled as such in the report; it
                 can be wrong in either direction, so read it as a prompt for review.
  * manual     - needs a person (first-party data, original research, expert interviews, "is this actually the
                 best answer"). Listed once, never scored, so a page never earns marks for things nobody checked.

The score is passed / (passed + failed) over automatic and heuristic items only. It is a triage number for
comparing pages month to month, not a prediction of citations. Nothing here promises a ranking or a mention.

Usage
-----
    python3 scripts/seo/ai_checklist.py                      # table to stdout
    python3 scripts/seo/ai_checklist.py --out reports/ai    # also write <date>.csv and <date>.md
    python3 scripts/seo/ai_checklist.py --today 2026-11-20   # fixed date for freshness (tests, reruns)
    python3 scripts/seo/ai_checklist.py --fail-under 60      # exit 1 if any commercial page scores below 60
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "website"
FRESH_DAYS = 30
QUESTION_STARTS = ("what", "how", "why", "when", "who", "which", "can", "does", "do", "is", "are", "should", "will")
SOCIAL_HOSTS = ("linkedin.com", "x.com", "twitter.com", "facebook.com", "youtube.com", "instagram.com", "tiktok.com")

# Items that need a person. Reported once per page set, never scored.
MANUAL_ITEMS = (
    "First-party or proprietary data is present and real",
    "Original research, surveys or named expert interviews",
    "First-hand experience or a case-specific teardown",
    "Customer quotes are genuine and attributable",
    "Every claim has a source a reader can open",
    "The direct answer is actually correct and complete",
    "Named, ownable framework (coined term) is used consistently",
)

SKIP_FILES = {"404.html"}


class Page(HTMLParser):
    """Collects the structure the checks need in one pass."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.canonical = ""
        self.jsonld_raw: list[str] = []
        self.headings: list[tuple[str, str]] = []
        self.paragraphs: list[str] = []
        self.counts = {"table": 0, "ul": 0, "ol": 0, "img": 0, "img_alt": 0, "video": 0, "time": 0}
        self.links: list[str] = []
        self.text_parts: list[str] = []
        self._buf: list[str] | None = None
        self._tag = ""
        self._in_jsonld = False
        self._skip = 0
        self._in_main = False
        self._seen_main = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag in ("script", "style", "noscript"):
            self._skip += 1
            self._in_jsonld = tag == "script" and a.get("type") == "application/ld+json"
            if self._in_jsonld:
                self.jsonld_raw.append("")
            return
        if tag == "main":
            self._in_main = self._seen_main = True
        if tag == "meta" and a.get("name"):
            self.meta[a["name"].lower()] = a.get("content", "")
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href", "")
        if tag in self.counts:
            self.counts[tag] += 1
        if tag == "iframe" and re.search(r"youtube|vimeo", a.get("src", ""), re.I):
            self.counts["video"] += 1
        if tag == "img" and "alt" in a:  # alt="" marks a decorative image and is correct
            self.counts["img_alt"] += 1
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in ("h1", "h2", "h3", "p", "title") and not self._skip:
            self._buf, self._tag = [], tag

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)
            self._in_jsonld = False
            return
        if tag == "main":
            self._in_main = False
        if self._buf is not None and tag == self._tag:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if tag == "title":
                self.title = text
            elif tag == "p":
                if text and (self._in_main or not self._seen_main):
                    self.paragraphs.append(text)
            elif text:
                self.headings.append((tag, text))
            self._buf, self._tag = None, ""

    def handle_data(self, data: str) -> None:
        if self._in_jsonld and self.jsonld_raw:
            self.jsonld_raw[-1] += data
            return
        if self._skip:
            return
        self.text_parts.append(data)
        if self._buf is not None:
            self._buf.append(data)


def _walk(node: object):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def parse_jsonld(raw: list[str]) -> tuple[list[dict], int]:
    nodes: list[dict] = []
    bad = 0
    for blob in raw:
        try:
            nodes.extend(n for n in _walk(json.loads(blob)) if isinstance(n, dict))
        except ValueError:
            bad += 1
    return nodes, bad


def _types(nodes: list[dict]) -> set[str]:
    out: set[str] = set()
    for n in nodes:
        t = n.get("@type")
        out.update(t if isinstance(t, list) else [t] if isinstance(t, str) else [])
    return out


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


@dataclass
class Result:
    page: str
    checks: dict[str, tuple[str, bool]] = field(default_factory=dict)  # name -> (kind, passed)
    notes: list[str] = field(default_factory=list)
    noindex: bool = False

    def add(self, name: str, kind: str, passed: bool) -> None:
        self.checks[name] = (kind, bool(passed))

    @property
    def passed(self) -> int:
        return sum(1 for _, ok in self.checks.values() if ok)

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def score(self) -> int:
        return round(100 * self.passed / self.total) if self.total else 0

    @property
    def failed(self) -> list[str]:
        return [n for n, (_, ok) in self.checks.items() if not ok]


def audit_html(name: str, html: str, today: date) -> Result:
    p = Page()
    p.feed(html)
    nodes, bad_ld = parse_jsonld(p.jsonld_raw)
    types = _types(nodes)
    text = re.sub(r"\s+", " ", " ".join(p.text_parts))
    para_words = [len(x.split()) for x in p.paragraphs]
    h = [t for tag, t in p.headings if tag in ("h2", "h3")]
    r = Result(name, noindex="noindex" in p.meta.get("robots", "").lower())

    # On-page components
    r.add("Structured data (JSON-LD) present and valid", "auto", bool(nodes) and bad_ld == 0)
    r.add("FAQ section (FAQPage schema or FAQ heading)", "auto",
          "FAQPage" in types or any(re.search(r"\bfaq\b|frequently asked|common questions", x, re.I) for x in h))
    r.add("Comparison table or table of facts", "auto", p.counts["table"] > 0)
    r.add("Bullet or numbered lists", "auto", p.counts["ul"] + p.counts["ol"] > 0)
    r.add("Specific numbers in the body (5 or more)", "heuristic", len(re.findall(r"\d[\d,.]*", text)) >= 5)
    r.add("Images have an alt attribute (empty is fine for decorative)", "auto", p.counts["img"] == 0 or p.counts["img_alt"] == p.counts["img"])
    r.add("Video present", "auto", p.counts["video"] > 0 or "youtube.com" in html or "<video" in html)
    r.add("Links to social profiles (links or sameAs)", "auto",
          any(any(s in link for s in SOCIAL_HOSTS) for link in p.links) or any("sameAs" in n for n in nodes))
    r.add("Author or publisher named (schema author/publisher or byline)", "auto",
          any(k in n for n in nodes for k in ("author", "publisher")) or bool(re.search(r"\bby [A-Z][a-z]+", text)))

    # How the copy reads
    qh = sum(1 for x in h if x.endswith("?") or x.lower().startswith(QUESTION_STARTS))
    r.add("Question-style headings (a third or more of H2/H3)", "heuristic", bool(h) and qh / len(h) >= 1 / 3)
    lead = next((w for w in para_words if w >= 8), None)  # skips one-line eyebrow labels
    r.add("Answer-first: first real paragraph is 60 words or less", "heuristic", lead is not None and lead <= 60)
    long_share = sum(1 for w in para_words if w > 100) / len(para_words) if para_words else 1
    r.add("Short paragraphs (median 60 words or less, under 10% over 100)", "heuristic",
          bool(para_words) and statistics.median(para_words) <= 60 and long_share < 0.10)
    r.add("Enough sections to answer related questions (5 or more H2)", "auto",
          sum(1 for tag, _ in p.headings if tag == "h2") >= 5)

    # Freshness
    dm = next((d for n in nodes if (d := _parse_date(n.get("dateModified")))), None)
    r.add("Dates published (datePublished, dateModified or a time element)", "auto",
          any("datePublished" in n or "dateModified" in n for n in nodes) or p.counts["time"] > 0)
    r.add(f"Updated within {FRESH_DAYS} days", "auto", dm is not None and 0 <= (today - dm).days <= FRESH_DAYS)
    if dm is None:
        r.notes.append("no dateModified in JSON-LD")

    # Query fan-out context buckets (keyword prompts, not proof)
    low = text.lower()
    r.add("Explains cost or pricing", "heuristic", bool(re.search(r"\$|price|pricing|cost|per month|budget", low)))
    r.add("Explains timeline or setup", "heuristic", bool(re.search(r"\bweeks?\b|\bdays?\b|how long|setup|set up|onboard", low)))
    r.add("States limits, risks or who it is not for", "heuristic",
          bool(re.search(r"not included|can't|cannot|won't|limit|risk|not for|not right for", low)))
    r.add("Compares options or alternatives", "heuristic", bool(re.search(r"\bvs\.?\b|compare|alternative|versus|instead of", low)))

    # Technical basics that gate everything above
    r.add("Single H1", "auto", sum(1 for tag, _ in p.headings if tag == "h1") == 1)
    r.add("Title and meta description", "auto", bool(p.title) and bool(p.meta.get("description")))
    r.add("Canonical set and page is indexable", "auto",
          bool(p.canonical) and "noindex" not in p.meta.get("robots", "").lower())
    return r


def audit_site(site: Path, today: date) -> list[Result]:
    out = []
    for f in sorted(site.glob("*.html")):
        if f.name in SKIP_FILES:
            continue
        out.append(audit_html(f.name, f.read_text(encoding="utf-8", errors="replace"), today))
    return out


def noindex(r: Result) -> bool:
    return r.noindex


def markdown(results: list[Result], today: date) -> str:
    lines = [f"# AI-search checklist, {today.isoformat()}", "",
             f"{len(results)} pages. Score = passed / (automatic + heuristic items). Triage only; no ranking is implied.", "",
             "| Page | Score | Failed items |", "|---|---|---|"]
    for r in sorted(results, key=lambda x: x.score):
        lines.append(f"| {r.page} | {r.score} | {'; '.join(r.failed) or 'none'} |")
    misses: dict[str, int] = {}
    for r in results:
        for n in r.failed:
            misses[n] = misses.get(n, 0) + 1
    lines += ["", "## Most common gaps", ""]
    lines += [f"- {n}: {c} of {len(results)} pages" for n, c in sorted(misses.items(), key=lambda x: -x[1])[:8]]
    lines += ["", "## Manual review (never scored)", ""] + [f"- {m}" for m in MANUAL_ITEMS]
    return "\n".join(lines) + "\n"


def write_outputs(results: list[Result], out: Path, today: date) -> None:
    out.mkdir(parents=True, exist_ok=True)
    names = list(results[0].checks) if results else []
    with open(out / f"{today.isoformat()}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["page", "score"] + names)
        for r in results:
            w.writerow([r.page, r.score] + ["pass" if r.checks[n][1] else "fail" for n in names])
    (out / f"{today.isoformat()}.md").write_text(markdown(results, today), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", type=Path, default=SITE)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--today", type=date.fromisoformat, default=date.today())
    ap.add_argument("--fail-under", type=int)
    args = ap.parse_args(argv)
    results = audit_site(args.site, args.today)
    if not results:
        print(f"no pages found in {args.site}", file=sys.stderr)
        return 2
    print(markdown(results, args.today))
    if args.out:
        write_outputs(results, args.out, args.today)
    if args.fail_under is not None:
        low = [r for r in results if r.score < args.fail_under and not noindex(r)]
        if low:
            print(f"FAIL: {len(low)} indexable page(s) under {args.fail_under}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
