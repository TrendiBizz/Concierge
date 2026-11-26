#!/usr/bin/env python3
"""The website's technical SEO contract, as one runnable check.

Why this exists
---------------
The site is 40 hand-written pages published by `scripts/vps/deploy-site.sh`. Nothing structural
watched them: the health check tested 16 commercial pages for copy length and canonical, and the
sitemap was edited by hand. On 2026-11-15 that gap was measured — a bulk rewrite had shipped
"worldwide" into legal pages, the sitemap carried a malformed `<url>` line and a URL with no
`lastmod`, a 1,043-word guide was left `noindex` and missing from the sitemap entirely, and 21
AppleDouble `._*` files had been committed to the web root.

This module is the guard the growth plan needs: one place that knows what a correct page looks
like, whether the sitemap matches reality, and which URLs changed so IndexNow can be pinged.

Commands
--------
    python3 scripts/seo/site_seo.py check              # audit the source tree; exit 1 on defects
    python3 scripts/seo/site_seo.py sitemap --write    # rebuild website/sitemap.xml from the pages
    python3 scripts/seo/site_seo.py sitemap            # print what the sitemap should be (no write)
    python3 scripts/seo/site_seo.py ping --changed-in <git-ref>
                                                       # tell IndexNow which pages changed since a commit
    python3 scripts/seo/site_seo.py ping --all         # submit every sitemap URL once

The check is intentionally strict about the things that quietly cost rankings — a missing
canonical, an accidental `noindex`, a sitemap that disagrees with the files — and deliberately
quiet about things that are editorial, like whether a page is good.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE_ROOT = REPO_ROOT / "website"
SITEMAP = SITE_ROOT / "sitemap.xml"
INDEXNOW_KEY_FILE = SITE_ROOT / "indexnow-key.json"
SITE = "https://trendibizz.com"

# Pages that are deliberately excluded from search. Everything else is expected to be reachable,
# canonical and listed in the sitemap.
NOINDEX_ALLOWED = {"404.html", "concierge-welcome.html"}
DESCRIPTION_LIMIT = 160
TITLE_UNIQUE = True

HTML_SUFFIXES = (".html",)


def page_url(rel: str) -> str:
    """The URL a source file is served at. index.html is the site root; a nested index.html is the directory."""
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("/index.html")]
    return "/" + rel[: -len(".html")]


def iter_pages(root: Path = SITE_ROOT) -> list[Path]:
    pages = []
    for path in sorted(root.rglob("*.html")):
        if path.name.startswith("._"):
            continue
        pages.append(path)
    return pages


def _meta(html: str, name: str) -> str | None:
    match = re.search(rf'<meta content="([^"]*)" name="{re.escape(name)}"', html)
    if match:
        return match.group(1)
    return None


def ld_json_blocks(html: str) -> list[dict]:
    blocks = []
    for match in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            blocks.append(json.loads(match.group(1)))
        except ValueError:
            blocks.append({"_invalid": True})
    return blocks


def date_modified(html: str) -> str | None:
    """The newest dateModified published in the page's structured data."""
    best: str | None = None
    for block in ld_json_blocks(html):
        stack = [block]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                value = node.get("dateModified") or node.get("datePublished")
                if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    if best is None or value > best:
                        best = value
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return best


def internal_links(html: str) -> set[str]:
    links = set()
    for match in re.finditer(r'href="([^"]+)"', html):
        href = match.group(1)
        if href.startswith("/") and not href.startswith("//"):
            links.add(href.split("#", 1)[0].split("?", 1)[0])
        elif href.startswith(SITE):
            links.add(href[len(SITE):] or "/")
    return links


def redirect_sources(root: Path = SITE_ROOT) -> set[str]:
    """Paths that are not files but are served by website/_redirects.

    `/concierge/sign-in` is a 302 to the portal and has no file behind it. A link checker that
    ignores _redirects reports a healthy redirect as a broken link, and then the real broken links
    get lost in the noise.
    """
    path = root / "_redirects"
    if not path.is_file():
        return set()
    sources = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("/"):
            sources.add(parts[0])
    return sources


def resolves(root: Path, url: str, redirects: set[str] | None = None) -> bool:
    """Does an absolute site path correspond to a file we publish (or a redirect we serve)?"""
    if redirects is None:
        redirects = redirect_sources(root)
    if url in ("", "/"):
        return (root / "index.html").exists()
    if url in redirects or url.rstrip("/") + "/" in redirects:
        return True
    target = url.lstrip("/")
    if (root / target).is_file():
        return True
    if (root / (target + ".html")).is_file():
        return True
    if (root / target / "index.html").is_file():
        return True
    return False


def audit(root: Path = SITE_ROOT) -> list[str]:
    """Every structural SEO defect in the source tree, as human-readable strings."""
    problems: list[str] = []
    pages = iter_pages(root)
    if not pages:
        return [f"no pages under {root}"]

    seen_titles: dict[str, str] = {}
    seen_descriptions: dict[str, str] = {}
    indexable: dict[str, str] = {}  # url -> page rel

    for path in pages:
        rel = path.relative_to(root).as_posix()
        html = path.read_text(encoding="utf-8", errors="replace")
        url = page_url(rel)

        # 1. Canonical must exist, be absolute, and be this page's own URL. Pages excluded from
        #    search are exempt: a canonical on a noindex page is noise, not a signal.
        canonical = re.search(r'<link href="([^"]+)" rel="canonical"', html)
        if not canonical and rel not in NOINDEX_ALLOWED:
            problems.append(f"{rel}: no canonical link")
        elif canonical:
            expected = SITE + url
            if canonical.group(1) != expected:
                problems.append(f"{rel}: canonical is {canonical.group(1)!r}, expected {expected!r}")

        # 2. noindex must be deliberate.
        #    Google and Bing obey their own crawler-specific meta (googlebot, bingbot) as well as the
        #    generic one, and the most restrictive wins. Reading only name="robots" let /glossary and
        #    the crawler study ship "index" to everyone and "noindex" to Googlebot (found 15 Nov 2026).
        robots_metas = re.findall(r'<meta content="([^"]*)" name="(robots|googlebot|bingbot)"', html)
        noindex = any("noindex" in content for content, _ in robots_metas)
        if robots_metas and len({"noindex" in c for c, _ in robots_metas}) > 1:
            problems.append(f"{rel}: robots metas disagree: " + ", ".join(f"{n}={c!r}" for c, n in robots_metas))
        if noindex and rel not in NOINDEX_ALLOWED:
            problems.append(f"{rel}: noindex, but it is not on the allowed list")
        if not noindex and rel in NOINDEX_ALLOWED:
            problems.append(f"{rel}: expected noindex but none found")

        # 3. One h1, a title and a snippet that will not be cut off.
        h1s = len(re.findall(r"<h1[ >]", html))
        if h1s != 1:
            problems.append(f"{rel}: {h1s} h1 tags")
        title = re.search(r"<title>(.*?)</title>", html, re.S)
        if not title or not title.group(1).strip():
            problems.append(f"{rel}: no title")
        else:
            clean_title = title.group(1).strip()
            if TITLE_UNIQUE:
                if clean_title in seen_titles:
                    problems.append(f"{rel}: title duplicates {seen_titles[clean_title]}")
                seen_titles[clean_title] = rel
        description = _meta(html, "description")
        if not description:
            problems.append(f"{rel}: no meta description")
        elif len(description) > DESCRIPTION_LIMIT:
            problems.append(f"{rel}: description {len(description)} chars (limit {DESCRIPTION_LIMIT})")
        elif not noindex and description in seen_descriptions:
            # A duplicated snippet makes two pages compete for one result.
            problems.append(f"{rel}: description duplicates {seen_descriptions[description]}")
        else:
            seen_descriptions[description] = rel

        # 4. lastmod honesty: the page must publish a date the sitemap can copy.
        modified = date_modified(html)
        if not modified and not noindex:
            problems.append(f"{rel}: no dateModified/datePublished in structured data")
        if modified:
            try:
                parsed = dt.date.fromisoformat(modified)
            except ValueError:
                problems.append(f"{rel}: dateModified {modified!r} is not a date")
            else:
                if parsed > dt.date.today():
                    problems.append(f"{rel}: dateModified {modified} is in the future")

        # 5. Internal links must land on a published file.
        for link in sorted(internal_links(html)):
            if link.startswith("#") or not link:
                continue
            if not resolves(root, link):
                problems.append(f"{rel}: link {link} has no target file")

        # 5b. The visible "last updated" line must agree with the structured data, or the page is
        #     telling readers one thing and search engines another.
        visible = re.search(r'data-updated="(\d{4}-\d{2}-\d{2})"', html)
        if visible and modified and visible.group(1) != modified:
            problems.append(f"{rel}: visible date {visible.group(1)} but dateModified {modified}")

        # 5c. Structured data has to be real JSON. A broken @graph silently removes every rich
        #     result the page was eligible for, and nothing else notices.
        blocks = ld_json_blocks(html)
        if any(isinstance(block, dict) and block.get("_invalid") for block in blocks):
            problems.append(f"{rel}: structured data is not valid JSON")
        elif not noindex and not blocks:
            problems.append(f"{rel}: no JSON-LD structured data")

        # 5d. Every image declares alt — empty is a deliberate choice, absent is an omission.
        for tag in re.findall(r"<img\b[^>]*>", html):
            if " alt=" not in tag:
                problems.append(f"{rel}: image without an alt attribute: {tag[:70]}")

        # 5e. Headings are an outline; a jump from h1 to h3 tells a crawler a level is missing.
        previous = None
        for level in (int(found) for found in re.findall(r"<h([1-6])[ >]", html)):
            if previous is not None and level > previous + 1:
                problems.append(f"{rel}: heading jumps from h{previous} to h{level}")
                break
            previous = level

        # 5f. Sharing needs an absolute image; a relative one is dropped by most crawlers.
        og_image = None
        for tag in re.findall(r"<meta\b[^>]*>", html):
            if 'property="og:image"' in tag:
                found = re.search(r'content="([^"]+)"', tag)
                og_image = found.group(1) if found else None
        if not noindex and (not og_image or not og_image.startswith("https://")):
            problems.append(f"{rel}: og:image must be an absolute https URL")

        if not noindex:
            indexable[url] = rel

    # 6. The sitemap is generated data: it must equal the indexable page set, both directions.
    expected = build_sitemap(root)
    sitemap_path = root / "sitemap.xml"
    if not sitemap_path.exists():
        problems.append("website/sitemap.xml is missing")
    else:
        current = sitemap_path.read_text(encoding="utf-8")
        if normalise_sitemap(current) != normalise_sitemap(expected):
            problems.extend(compare_sitemaps(current, expected, indexable))

    # 7. No AppleDouble junk in the web root: macOS resource forks were committed 21 times.
    for path in sorted(root.rglob("._*")):
        problems.append(f"{path.relative_to(root).as_posix()}: AppleDouble file committed to the site")

    # 8. The IndexNow key published on the site must be the key the scripts will send.
    data = load_indexnow_key(root)
    key_file = root / f"{data.get('key')}.txt"
    if not key_file.is_file():
        problems.append(f"IndexNow key file {key_file.name} is missing")
    elif key_file.read_text(encoding="utf-8").strip() != data.get("key"):
        problems.append(f"IndexNow key file {key_file.name} does not contain the key")

    # 9. robots.txt is a policy, not a preference: search and AI-search crawlers must keep access
    #    and training crawlers must stay blocked. One bad deploy here removes the site from search.
    problems.extend(robots_problems(root))

    # 10. A page that publishes original data has to be findable and its data has to be downloadable.
    #     The 2026 crawler research was the site's best link asset and nothing linked to it.
    problems.extend(living_data_problems(root))
    return problems


def living_data_problems(root: Path = SITE_ROOT) -> list[str]:
    problems = []
    links_by_target: dict[str, list[str]] = {}
    for path in iter_pages(root):
        rel = path.relative_to(root).as_posix()
        for link in internal_links(path.read_text(encoding="utf-8", errors="replace")):
            links_by_target.setdefault(link.rstrip("/"), []).append(rel)

    for path in iter_pages(root):
        rel = path.relative_to(root).as_posix()
        html = path.read_text(encoding="utf-8", errors="replace")
        for block in ld_json_blocks(html):
            dataset = find_type(block, "Dataset")
            if not dataset:
                continue
            distribution = dataset.get("distribution") if isinstance(dataset, dict) else None
            downloads = distribution if isinstance(distribution, list) else [distribution] if distribution else []
            if not downloads:
                problems.append(f"{rel}: Dataset has no distribution (nothing to download)")
            for download in downloads:
                url = str((download or {}).get("contentUrl") or "")
                if not url.startswith(SITE):
                    problems.append(f"{rel}: Dataset contentUrl is not on this site")
                elif not resolves(root, url[len(SITE):]):
                    problems.append(f"{rel}: Dataset contentUrl {url[len(SITE):]} has no file")
            url = page_url(rel).rstrip("/")
            inbound = [source for source in links_by_target.get(url, []) if source != rel]
            if len(inbound) < 3:
                problems.append(f"{rel}: original data linked from only {len(inbound)} other page(s) "
                                "(a data page nothing links to cannot earn links)")
    return problems


def find_type(node, wanted: str):
    if isinstance(node, dict):
        if node.get("@type") == wanted:
            return node
        for value in node.values():
            found = find_type(value, wanted)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = find_type(item, wanted)
            if found:
                return found
    return None



# Policy changed 2026-11-23 (Jo): the major AI crawlers are welcome so the brand can be discovered and
# cited. Only Bytespider (ignores robots.txt, very heavy crawler) stays blocked.
ROBOTS_MUST_ALLOW = ("Googlebot", "Bingbot", "OAI-SearchBot", "PerplexityBot", "Claude-SearchBot",
                     "GPTBot", "ClaudeBot", "Google-Extended", "Applebot-Extended", "CCBot", "Amazonbot")
ROBOTS_MUST_BLOCK = ("Bytespider",)


def parse_robots(text: str) -> dict[str, list[str]]:
    """agent (lowercase) -> rules for that agent, plus '*' for the default group."""
    groups: dict[str, list[str]] = {}
    agents: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, value = line.split(":", 1)
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            agent = value.lower()
            if agent not in groups:
                groups[agent] = []
            agents.append(agent)
        elif field in ("allow", "disallow") and agents:
            groups[agents[-1]].append(f"{field}: {value}")
    return groups


def robots_problems(root: Path = SITE_ROOT) -> list[str]:
    path = root / "robots.txt"
    if not path.is_file():
        return ["robots.txt is missing"]
    text = path.read_text(encoding="utf-8", errors="replace")
    groups = parse_robots(text)
    problems = []
    for agent in ROBOTS_MUST_ALLOW:
        rules = groups.get(agent.lower())
        if rules is None:
            problems.append(f"robots.txt: {agent} has no group")
        elif any(rule == "disallow: /" for rule in rules):
            problems.append(f"robots.txt: {agent} is blocked with Disallow: /")
    for agent in ROBOTS_MUST_BLOCK:
        rules = groups.get(agent.lower()) or []
        if not any(rule.startswith("disallow: /") for rule in rules):
            problems.append(f"robots.txt: training crawler {agent} is not blocked")
    if "sitemap:" not in text.lower():
        problems.append("robots.txt: no Sitemap line")
    return problems



def compare_sitemaps(current_xml: str, expected_xml: str, indexable: dict[str, str]) -> list[str]:
    current = parse_sitemap(current_xml)
    expected = parse_sitemap(expected_xml)
    problems = []
    missing = sorted(set(expected) - set(current))
    extra = sorted(set(current) - set(expected))
    if missing:
        problems.append("sitemap missing: " + ", ".join(missing[:5]))
    if extra:
        problems.append("sitemap lists a URL with no indexable page: " + ", ".join(extra[:5]))
    for url in sorted(set(current) & set(expected)):
        if current[url] != expected[url]:
            problems.append(f"sitemap lastmod for {url} is {current[url] or 'empty'}, page says {expected[url]}")
    return problems


def parse_sitemap(xml_text: str) -> dict[str, str]:
    root = ET.fromstring(xml_text)
    entries: dict[str, str] = {}
    for node in root:
        if not node.tag.endswith("url"):
            continue
        loc = lastmod = ""
        for child in node:
            if child.tag.endswith("loc"):
                loc = (child.text or "").strip()
            elif child.tag.endswith("lastmod"):
                lastmod = (child.text or "").strip()
        if loc:
            entries[loc] = lastmod
    return entries


def normalise_sitemap(xml_text: str) -> str:
    """Whitespace-insensitive comparison so a formatter cannot cause a false alarm."""
    return re.sub(r">\s+<", "><", xml_text.strip())



def rss_sitemap_lastmod(root: Path) -> str:
    """YYYY-MM-DD from rss.xml lastBuildDate, if the feed exists."""
    path = root / "rss.xml"
    if not path.is_file():
        return ""
    match = re.search(r"<lastBuildDate>([^<]+)</lastBuildDate>", path.read_text(encoding="utf-8"))
    if not match:
        return ""
    import email.utils
    try:
        return email.utils.parsedate_to_datetime(match.group(1).strip()).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return ""


def build_sitemap(root: Path = SITE_ROOT, site: str = SITE) -> str:
    """The sitemap the pages describe. Deterministic: same pages in, same XML out."""
    rows = []
    for path in iter_pages(root):
        rel = path.relative_to(root).as_posix()
        if rel in NOINDEX_ALLOWED:
            continue
        html = path.read_text(encoding="utf-8", errors="replace")
        rows.append((site + page_url(rel), date_modified(html) or ""))
    # rss.xml is a discovery file, not an HTML page, but it should be listed beside the pages it covers.
    if (root / "rss.xml").is_file():
        rows.append((site + "/rss.xml", rss_sitemap_lastmod(root)))
    rows.sort(key=lambda row: (row[0] != site + "/", row[0]))
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod in rows:
        if lastmod:
            lines.append(f"  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod></url>")
        else:
            lines.append(f"  <url><loc>{loc}</loc></url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def load_indexnow_key(root: Path = SITE_ROOT) -> dict:
    data = json.loads((root / "indexnow-key.json").read_text(encoding="utf-8"))
    if not re.fullmatch(r"[0-9a-f]{32}", str(data.get("key", ""))):
        raise SystemExit("indexnow-key.json must hold a 32-character hex key")
    return data


def changed_urls(since: str, root: Path = SITE_ROOT) -> list[str]:
    """Site URLs whose source changed between `since` and HEAD (uses git, not mtimes)."""
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--name-only", since, "HEAD", "--", "website"],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"git diff failed: {result.stderr.strip()}")
    urls = []
    for name in result.stdout.split():
        path = (REPO_ROOT / name).resolve()
        if path.suffix != ".html" or not path.is_file():
            continue
        rel = path.relative_to(root.resolve()).as_posix()
        if rel in NOINDEX_ALLOWED:
            continue
        urls.append(SITE + page_url(rel))
    return sorted(set(urls))


def ping_indexnow(urls: list[str], endpoint: str = "https://api.indexnow.org/indexnow",
                  timeout: float = 20.0) -> int:
    """POST one batch to IndexNow. Returns the HTTP status; never raises on network failure."""
    if not urls:
        print("IndexNow: nothing changed, no ping sent")
        return 0
    data = load_indexnow_key()
    payload = json.dumps({
        "host": "trendibizz.com",
        "key": data["key"],
        "keyLocation": data.get("keyLocation") or f"{SITE}/{data['key']}.txt",
        "urlList": urls,
    }).encode()
    request = urllib.request.Request(
        endpoint, data=payload,
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent": "TrendiIndexNow/2.0 (+https://trendibizz.com)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
    except urllib.error.HTTPError as error:  # a refused key is worth seeing, not hiding
        status = error.code
    except OSError as error:
        print(f"IndexNow: network failure ({type(error).__name__}); the deploy still stands")
        return 599
    print(f"IndexNow: HTTP {status} for {len(urls)} URL(s): {', '.join(urls[:5])}"
          + (" …" if len(urls) > 5 else ""))
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    p_sitemap = sub.add_parser("sitemap")
    p_sitemap.add_argument("--write", action="store_true")
    p_ping = sub.add_parser("ping")
    p_ping.add_argument("--all", action="store_true")
    p_ping.add_argument("--changed-in")
    args = parser.parse_args(argv)

    if args.command == "check":
        problems = audit()
        if problems:
            print(f"FAIL: {len(problems)} SEO defect(s) in website/", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print(f"OK: {len(iter_pages())} pages — canonical, robots, h1, snippet, dates, links, "
              f"sitemap and IndexNow key all agree")
        return 0

    if args.command == "sitemap":
        xml = build_sitemap()
        if args.write:
            SITEMAP.write_text(xml, encoding="utf-8")
            count = len(re.findall(r"<loc>", xml))
            print(f"wrote website/sitemap.xml ({count} URLs, sha256 {hashlib.sha256(xml.encode()).hexdigest()[:12]})")
        else:
            print(xml)
        return 0

    if args.command == "ping":
        if args.all:
            urls = sorted(parse_sitemap(build_sitemap()))
        elif args.changed_in:
            urls = changed_urls(args.changed_in)
        else:
            print("ping needs --all or --changed-in <git-ref>", file=sys.stderr)
            return 2
        return 0 if (not urls or 200 <= ping_indexnow(urls) < 300) else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
