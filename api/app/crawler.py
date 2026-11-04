"""Polite same-site crawler. Only crawl sites you own or have the owner's permission to index.

It honours robots.txt, uses the sitemap when present, and extracts readable text with
trafilatura. Pages that render their content with JavaScript will come back nearly empty;
for those, paste the content in via the /ingest-text endpoint or add a headless-browser
crawler (see README, "Add-ons").
"""

import asyncio
import re
from collections import deque
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura

USER_AGENT = "ConciergeBot/1.0 (indexing at the site owner's request)"
SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".zip", ".gz",
    ".mp4", ".mp3", ".mov", ".avi", ".css", ".js", ".json", ".xml", ".woff", ".woff2",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
)
MAX_HTML_BYTES = 3_000_000
MIN_TEXT_CHARS = 80


@dataclass
class Page:
    url: str
    title: str
    text: str


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.hrefs.append(value)


def host_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def normalize(url: str, base: str | None = None) -> str | None:
    """Absolute http(s) URL without fragment or query string, or None if not crawlable."""
    if base:
        url = urljoin(base, url)
    url, _ = urldefrag(url.strip())
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    path = parts.path or "/"
    if path.lower().endswith(SKIP_EXTENSIONS):
        return None
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, "", ""))


def extract_links(html: str, base_url: str) -> list[str]:
    parser = _LinkParser()
    try:
        parser.feed(html)
    except Exception:  # malformed HTML must never abort a crawl
        pass
    out: list[str] = []
    for href in parser.hrefs:
        normalized = normalize(href, base_url)
        if normalized:
            out.append(normalized)
    return out


def extract_page(url: str, html: str) -> Page | None:
    text = trafilatura.extract(html, url=url, include_tables=True, favor_recall=True) or ""
    text = text.strip()
    if len(text) < MIN_TEXT_CHARS:
        return None
    title = ""
    try:
        meta = trafilatura.extract_metadata(html)
        title = (meta.title or "") if meta else ""
    except Exception:
        title = ""
    if not title:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
    return Page(url=url, title=title[:200], text=text)


class Robots:
    def __init__(self, text: str | None) -> None:
        self._parser: RobotFileParser | None = None
        if text:
            self._parser = RobotFileParser()
            self._parser.parse(text.splitlines())

    def allowed(self, url: str) -> bool:
        if self._parser is None:
            return True
        return self._parser.can_fetch(USER_AGENT, url)


async def _load_robots(client: httpx.AsyncClient, base: str) -> Robots:
    try:
        resp = await client.get(urljoin(base, "/robots.txt"))
        if resp.status_code == 200:
            return Robots(resp.text)
    except httpx.HTTPError:
        pass
    return Robots(None)


async def _sitemap_urls(client: httpx.AsyncClient, base: str, limit: int) -> list[str]:
    found: list[str] = []
    to_visit = [urljoin(base, "/sitemap.xml")]
    visited: set[str] = set()
    while to_visit and len(found) < limit and len(visited) < 6:
        sitemap = to_visit.pop(0)
        if sitemap in visited:
            continue
        visited.add(sitemap)
        try:
            resp = await client.get(sitemap)
        except httpx.HTTPError:
            continue
        if resp.status_code != 200:
            continue
        # Regex rather than an XML parser: sitemaps are untrusted input.
        for loc in re.findall(r"<loc>\s*(.*?)\s*</loc>", resp.text, re.S):
            loc = loc.replace("&amp;", "&")
            if loc.lower().endswith(".xml"):
                to_visit.append(loc)
            else:
                normalized = normalize(loc)
                if normalized:
                    found.append(normalized)
    return found[:limit]


async def _fetch(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        resp = await client.get(url)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    if "html" not in resp.headers.get("content-type", "").lower():
        return None
    if len(resp.content) > MAX_HTML_BYTES:
        return None
    return resp.text


async def crawl(site_url: str, max_pages: int = 40, concurrency: int = 4, delay: float = 0.25) -> list[Page]:
    start = normalize(site_url)
    if not start:
        raise ValueError(f"Not a crawlable URL: {site_url}")
    host = host_of(start)

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=15.0
    ) as client:
        robots = await _load_robots(client, start)
        seeds = [start] + [
            u for u in await _sitemap_urls(client, start, max_pages * 3) if host_of(u) == host
        ]

        queue: deque[str] = deque(dict.fromkeys(seeds))
        seen: set[str] = set(queue)
        pages: list[Page] = []

        while queue and len(pages) < max_pages:
            batch: list[str] = []
            while queue and len(batch) < concurrency:
                candidate = queue.popleft()
                if robots.allowed(candidate):
                    batch.append(candidate)
            if not batch:
                continue

            htmls = await asyncio.gather(*(_fetch(client, u) for u in batch))
            for url, html in zip(batch, htmls):
                if html is None:
                    continue
                page = await asyncio.to_thread(extract_page, url, html)
                if page:
                    pages.append(page)
                if len(seen) < max_pages * 10:
                    for link in extract_links(html, url):
                        if host_of(link) == host and link not in seen:
                            seen.add(link)
                            queue.append(link)
            await asyncio.sleep(delay)

        return pages[:max_pages]
