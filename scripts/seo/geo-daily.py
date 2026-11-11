#!/usr/bin/env python3
"""Daily GEO/AI-visibility check for trendibizz.com.

No ranking can be guaranteed or switched on. This checks the things that can be
measured daily and pings IndexNow for changed pages so Bing (which feeds ChatGPT
and Copilot) re-crawls quickly.

Output: QA/verification/geo-daily/YYYY-MM-DD.md (created, not overwritten).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "QA/verification/geo-daily"
STATE = ROOT / ".geo-state.json"
SITE = "https://trendibizz.com"
SITEMAP = f"{SITE}/sitemap.xml"
KEY = "3a226d049abaa3f61aeeb0b3f9a6c6b9"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/141 Safari/537.36"}
PROMPTS = [
    "AI receptionist",
    "AI receptionist cost",
    "best AI receptionist",
    "AI answering service vs human",
    "AI receptionist for small business",
    "Trendi Concierge",
]


def get(url: str, timeout: int = 25) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, b""


def bing_visibility(query: str) -> tuple[bool, int | None]:
    """Bing HTML result page: is trendibizz present, and at what result position.

    The RSS endpoint ignores these queries, so this parses the normal result list.
    """
    url = "https://www.bing.com/search?count=20&q=" + urllib.parse.quote(query)
    status, body = get(url)
    if status != 200:
        return False, None
    text = body.decode("utf-8", "replace")
    blocks = text.split('class="b_algo"')
    for position, block in enumerate(blocks[1:], 1):
        if "trendibizz" in block.lower():
            return True, position
    return "trendibizz" in text.lower(), None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    report = [f"# GEO daily check — {today}", ""]
    state = json.loads(STATE.read_text()) if STATE.exists() else {}

    # Sitemap and page health
    status, body = get(SITEMAP)
    urls = []
    if status == 200:
        try:
            root = ET.fromstring(body)
            urls = [n.text.strip() for n in root.iter() if n.tag.endswith("loc") and n.text]
        except ET.ParseError:
            pass
    report.append(f"- sitemap: HTTP {status}, {len(urls)} URLs")
    changed = []
    failures = []
    for url in urls:
        code, page = get(url)
        if code != 200:
            failures.append(f"{url} ({code})")
            continue
        text = page.decode("utf-8", "replace")
        lastmod = re.search(r'<meta[^>]+property="article:modified_time"[^>]+content="([^"]+)"', text)
        fingerprint = str(len(text)) + ":" + (lastmod.group(1) if lastmod else "")
        if state.get(url) != fingerprint:
            changed.append(url)
            state[url] = fingerprint
    report.append(f"- pages checked: {len(urls) - len(failures)}, failing: {len(failures)}")
    if failures:
        report.append("  - " + "\n  - ".join(failures))
    report.append(f"- changed since last run: {len(changed)}")

    # IndexNow for changed pages (Bing/Yandex/Seznam, feeds ChatGPT's Bing index)
    if changed:
        payload = json.dumps({
            "host": "trendibizz.com", "key": KEY,
            "keyLocation": f"{SITE}/{KEY}.txt", "urlList": changed[:100],
        }).encode()
        request = urllib.request.Request(
            "https://api.indexnow.org/indexnow", data=payload,
            headers={**UA, "Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                report.append(f"- IndexNow: HTTP {response.status} for {len(changed)} URLs")
        except Exception as error:  # noqa: BLE001
            report.append(f"- IndexNow failed: {error}")
    else:
        report.append("- IndexNow: nothing changed")

    # Bing visibility (proxy for ChatGPT/Copilot retrieval)
    for label, query in [("site:trendibizz.com", "site:trendibizz.com")] + [(p, p) for p in PROMPTS]:
        present, position = bing_visibility(query)
        report.append(f"- Bing `{label}`: {'present' if present else 'not present'}"
                      + (f", position {position}" if position else ""))

    report += ["", "## Manual AI checks (weekly)", "",
               "Ask each prompt in ChatGPT, Perplexity and Gemini; record whether Trendi is",
               "named or linked. Bing visibility above is a proxy, not the AI answer.", ""]
    (OUT / f"{today}.md").write_text("\n".join(report))
    STATE.write_text(json.dumps(state, indent=1))
    print("\n".join(report[:1] + [line for line in report if line.startswith("- ")]))
    print(f"report: {OUT / (today + '.md')}")


if __name__ == "__main__":
    main()
