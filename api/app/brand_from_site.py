"""Propose a business's brand from its own public website.

The onboarding redesign asks the customer for two typed fields (website, own
mobile) and does the reading itself. This module is the "read" half: given a
public site it returns a *proposal* — name, logo as a PNG data URI, accent
colour, contact line, social accounts, the site platform, and the timezone and
dialling country implied by the site.

Rules this module keeps:

* It only reads public pages, through :class:`public_fetch.PublicClient`
  (HTTPS, same host, public IPs only), and never follows a link off the site.
* It writes nothing. No database, no tenant, no consent. The owner reviews the
  proposal and saves it themselves.
* Anything it is unsure about is returned as a note for the review screen
  rather than guessed silently.

Logos are frequently SVG. Our media pipeline composes raster images, so an SVG
is rendered to a transparent PNG here (resvg through the ``resvg_py`` wheel,
which needs no system libraries and executes no scripts). The brand store keeps
a ``data:image/`` string of at most 400,000 characters, so the stored PNG is
capped well below that. An SVG that draws its wordmark with live ``<text>``
needs a font on the server; where none is bundled the render can come back
blank, so those are reported with ``text_font_risk`` and the touch icon and
``og:image`` are offered alongside for the customer to choose.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx

from .crawler import USER_AGENT

# The brand store column holds a data: URI up to 400,000 characters. Base64
# inflates by 4/3, so the raw PNG must stay under ~290 KB.
MAX_STORED_LOGO_BYTES = 290_000
MAX_IMAGE_BYTES = 2_000_000
MAX_HTML_BYTES = 3_000_000
LOGO_PIXELS = 512
FETCH_TIMEOUT = 12.0

DEFAULT_ACCENT = "#c8f560"

# TLD -> (country calling code, IANA timezone). Only entries we are happy to
# propose without further evidence; the review screen always shows them.
_TLD_GEO = {
    "nz": ("64", "Pacific/Auckland"),
    "au": ("61", "Australia/Sydney"),
    "uk": ("44", "Europe/London"),
    "ie": ("353", "Europe/Dublin"),
    "ca": ("1", "America/Toronto"),
    "us": ("1", "America/New_York"),
    "za": ("27", "Africa/Johannesburg"),
    "sg": ("65", "Asia/Singapore"),
    "in": ("91", "Asia/Kolkata"),
}

_COUNTRY_ISO = {
    "NZ": ("64", "Pacific/Auckland"),
    "AU": ("61", "Australia/Sydney"),
    "GB": ("44", "Europe/London"),
    "UK": ("44", "Europe/London"),
    "IE": ("353", "Europe/Dublin"),
    "CA": ("1", "America/Toronto"),
    "US": ("1", "America/New_York"),
    "ZA": ("27", "Africa/Johannesburg"),
    "SG": ("65", "Asia/Singapore"),
    "IN": ("91", "Asia/Kolkata"),
}

SOCIAL_HOSTS = (
    ("facebook", ("facebook.com", "fb.com")),
    ("instagram", ("instagram.com",)),
    ("linkedin", ("linkedin.com",)),
    ("tiktok", ("tiktok.com",)),
    ("youtube", ("youtube.com", "youtu.be")),
    ("x", ("twitter.com", "x.com")),
    ("pinterest", ("pinterest.",)),
    ("threads", ("threads.net",)),
)

_SHARE_MARKERS = ("/sharer", "/share", "/intent/tweet", "/pin/create", "/submit?url")

_TAG_ATTRS_KEEP = ("src", "href", "content", "rel", "alt", "class", "id", "name",
                   "property", "type", "sizes")


@dataclass
class Image:
    url: str
    alt: str = ""
    classes: str = ""
    identifier: str = ""
    in_header: bool = False
    source: str = ""  # "header", "json-ld", "touch-icon", "og-image", "page"


@dataclass
class SiteScan:
    url: str
    title: str = ""
    metas: dict[str, str] = field(default_factory=dict)
    icons: list[str] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    json_ld: list[dict] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    socials: dict[str, str] = field(default_factory=dict)
    body_hints: str = ""


class _Scanner(HTMLParser):
    """One pass over the page: metas, icons, images, JSON-LD, contacts, socials."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metas: dict[str, str] = {}
        self.title = ""
        self.icons: list[str] = []
        self.images: list[Image] = []
        self.json_ld_raw: list[str] = []
        self.emails: list[str] = []
        self.phones: list[str] = []
        self.socials: dict[str, str] = {}
        self._stack: list[str] = []
        self._in_title = False
        self._in_ld = False
        self._ld_buffer: list[str] = []
        self._text: list[str] = []

    # -- helpers -----------------------------------------------------------
    def _in_headerish(self) -> bool:
        return any(tag in ("header", "nav") for tag in self._stack)

    def handle_starttag(self, tag, attrs):
        values = {name: (value or "") for name, value in attrs}
        self._stack.append(tag)

        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (values.get("property") or values.get("name") or "").strip().lower()
            content = values.get("content", "").strip()
            if key and content and key not in self.metas:
                self.metas[key] = content
        elif tag == "link":
            rel = values.get("rel", "").lower()
            href = values.get("href", "").strip()
            if href and any(word in rel for word in ("icon", "apple-touch")):
                self.icons.append(href)
        elif tag == "img":
            src = values.get("src", "").strip()
            if src:
                self.images.append(Image(
                    url=src,
                    alt=values.get("alt", "").strip(),
                    classes=values.get("class", ""),
                    identifier=values.get("id", ""),
                    in_header=self._in_headerish(),
                    source="header" if self._in_headerish() else "page",
                ))
        elif tag == "script" and values.get("type", "").lower() == "application/ld+json":
            self._in_ld = True
            self._ld_buffer = []
        elif tag == "a":
            href = values.get("href", "").strip()
            if href:
                self._anchor(href)
        elif tag in ("h1", "address", "p", "footer"):
            self._stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_ld:
            self._in_ld = False
            self.json_ld_raw.append("".join(self._ld_buffer))
        # tolerate unclosed tags: drop back to the nearest matching one
        if tag in self._stack:
            while self._stack and self._stack.pop() != tag:
                pass

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_ld:
            self._ld_buffer.append(data)
        if len(self._text) < 4000:
            stripped = data.strip()
            if stripped:
                self._text.append(stripped)

    # -- link classification ----------------------------------------------
    def _anchor(self, href: str) -> None:
        low = href.lower()
        if low.startswith("mailto:"):
            address = href[7:].split("?")[0].strip()
            if re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", address):
                self.emails.append(address)
        elif low.startswith("tel:"):
            number = href[4:].strip()
            if number:
                self.phones.append(number)
        elif any(marker in low for marker in _SHARE_MARKERS):
            return
        else:
            host = (urlsplit(href).hostname or "").lower()
            for name, domains in SOCIAL_HOSTS:
                if host and any(host == d or host.endswith("." + d.rstrip(".")) or d in host
                                for d in domains):
                    self.socials.setdefault(name, href)
                    break


def scan(html: str, url: str) -> SiteScan:
    """Parse a fetched page into the facts the proposal is built from."""
    scanner = _Scanner()
    try:
        scanner.feed(html)
        scanner.close()
    except Exception:  # malformed HTML must never abort a proposal
        pass

    result = SiteScan(
        url=url,
        title=re.sub(r"\s+", " ", scanner.title).strip()[:200],
        metas=scanner.metas,
        icons=scanner.icons,
        images=scanner.images,
        emails=list(dict.fromkeys(scanner.emails)),
        phones=list(dict.fromkeys(scanner.phones)),
        socials=scanner.socials,
        body_hints=" ".join(scanner._text)[:4000],
    )
    for raw in scanner.json_ld_raw:
        for block in _json_ld_blocks(raw):
            result.json_ld.append(block)
            _absorb_json_ld(block, result)
    return result


def _json_ld_blocks(raw: str) -> list[dict]:
    """Every object in a JSON-LD script, unwrapping @graph where present."""
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return []
    blocks: list[dict] = []
    pending = [payload]
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, dict):
            if "@graph" in item and isinstance(item["@graph"], list):
                pending.extend(item["@graph"])
            blocks.append(item)
    return blocks[:20]


def _first_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "url", "@id"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
    if isinstance(value, list) and value:
        return _first_text(value[0])
    return ""


def _absorb_json_ld(block: dict, result: SiteScan) -> None:
    logo = _first_text(block.get("logo"))
    if logo:
        result.images.append(Image(url=logo, source="json-ld"))
    image = _first_text(block.get("image"))
    if image and not logo:
        result.images.append(Image(url=image, source="json-ld"))
    phone = _first_text(block.get("telephone"))
    if phone:
        result.phones.append(phone)
    email = _first_text(block.get("email"))
    if email and "@" in email:
        result.emails.append(email.removeprefix("mailto:"))
    same_as = block.get("sameAs")
    for entry in (same_as if isinstance(same_as, list) else [same_as]):
        if not isinstance(entry, str):
            continue
        host = (urlsplit(entry).hostname or "").lower()
        for name, domains in SOCIAL_HOSTS:
            if host and any(host == d or host.endswith("." + d.rstrip(".")) or d in host
                            for d in domains):
                result.socials.setdefault(name, entry)


# ---------------------------------------------------------------------------
# Choosing what to look at


def _same_site(url: str, site_host: str) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return not host or host == site_host


def logo_candidates(page: SiteScan, site_host: str) -> list[Image]:
    """Ordered logo candidates, best first.

    JSON-LD ``logo`` is authoritative when present, then anything marked as a
    logo in the header, then the touch icon, then ``og:image``. Off-site URLs
    are dropped: the public fetcher refuses them by design.
    """
    scored: list[tuple[int, Image]] = []
    for image in page.images:
        url = image.url
        if url.startswith("data:"):
            if "image/" in url[:30]:
                scored.append((_score(image, image.source), image))
            continue
        if not _same_site(url, site_host):
            continue
        if urlsplit(url).scheme not in ("http", "https", ""):
            continue
        scored.append((_score(image, image.source), image))
    for href in page.icons:
        if href.startswith("data:") or _same_site(href, site_host):
            scored.append((_score(Image(url=href, source="touch-icon"), "touch-icon"),
                           Image(url=href, source="touch-icon")))
    og = page.metas.get("og:image", "")
    if og and (og.startswith("data:") or _same_site(og, site_host)):
        scored.append((_score(Image(url=og, source="og-image"), "og-image"),
                       Image(url=og, source="og-image")))

    seen: set[str] = set()
    ordered: list[Image] = []
    for _, image in sorted(scored, key=lambda pair: -pair[0]):
        if image.url not in seen:
            seen.add(image.url)
            ordered.append(image)
    return ordered[:6]


def _score(image: Image, source: str) -> int:
    hint = f"{image.url} {image.alt} {image.classes} {image.identifier}".lower()
    score = {"json-ld": 100, "header": 60, "touch-icon": 50, "og-image": 30}.get(source, 10)
    if "logo" in hint:
        score += 25
    if image.in_header:
        score += 10
    if hint.endswith((".svg", ".svg?", ".svg#")) or ".svg" in hint:
        score += 15
    if any(word in hint for word in ("banner", "hero", "photo", "slider", "background")):
        score -= 30
    if "apple-touch" in hint:
        score += 10
    return score


# ---------------------------------------------------------------------------
# Turning bytes into a stored PNG


def _is_svg(content: bytes) -> bool:
    head = content[:400].lstrip().lower()
    return head.startswith(b"<svg") or (b"<svg" in head and head.startswith(b"<?xml"))


def _svg_has_text(svg: str) -> bool:
    return "<text" in svg.lower()


def rasterise_svg(svg_text: str, pixels: int = LOGO_PIXELS,
                  font: str | None = None) -> bytes | None:
    """Render an SVG to PNG bytes, or None when no renderer is available.

    ``resvg_py`` is a pure wheel with no system libraries; it draws from the
    SVG alone and never fetches anything, so a hostile SVG cannot reach the
    network. Measured on 13 Nov against resvg_py 0.5.0: ``width`` scales the
    render while keeping the aspect ratio. ``font`` names the family to use
    when the SVG does not name one that exists.
    """
    try:
        import resvg_py  # noqa: PLC0415 - optional dependency, imported on use
    except Exception:  # noqa: BLE001 - absence is expected on a slim image
        return None
    options: dict = {"width": pixels}
    if font:
        options.update(font_family=font, sans_serif_family=font)
    for kwargs in (options, {}):
        try:
            rendered = resvg_py.svg_to_bytes(svg_string=svg_text, **kwargs)
        except TypeError:
            continue
        except Exception:  # noqa: BLE001 - a malformed SVG must not raise at the owner
            return None
        if isinstance(rendered, (bytes, bytearray)) and rendered[:8] == b"\x89PNG\r\n\x1a\n":
            return bytes(rendered)
        return None
    return None


# The family bundled in the API image. Liberation Sans is metric-compatible with
# Arial, so an Arial-named wordmark keeps its width and weight.
BUNDLED_LOGO_FONT = os.environ.get("BRAND_LOGO_FONT", "Liberation Sans")


def substitute_fonts(svg_text: str, family: str = BUNDLED_LOGO_FONT) -> str:
    """Point every font-family in the SVG at the one family the image ships.

    Measured behaviour of resvg: it resolves an exact family and does **not**
    fall back. A logo drawn with ``<text font-family="Arial,...">`` therefore
    renders with its wordmark missing rather than approximating it. Naming a
    bundled family is what makes the words appear at all.
    """
    return re.sub(
        r'(font-family\s*[:=]\s*)("[^"]*"|\'[^\']*\'|[^;"\'>]+)',
        lambda match: match.group(1) + '"' + family + '"',
        svg_text,
        flags=re.I,
    )


def _opaque_pixels(png: bytes) -> int:
    """How much ink a render put down; used to tell a blank render from a real one."""
    try:
        from PIL import Image as PILImage  # noqa: PLC0415

        with PILImage.open(io.BytesIO(png)) as opened:
            histogram = opened.convert("RGBA").getchannel("A").histogram()
        return sum(histogram[11:])
    except Exception:  # noqa: BLE001
        return 0


def render_logo_svg(svg_text: str, pixels: int = LOGO_PIXELS) -> tuple[bytes | None, bool]:
    """Render the SVG, preferring a substituted font when it draws more of the logo.

    Returns ``(png, substituted)``. A logo whose text is already converted to
    paths is untouched and renders exactly; one drawn with live text renders
    through the bundled family and is reported as substituted so the review
    screen can tell the owner the lettering is close, not identical.
    """
    direct = rasterise_svg(svg_text, pixels)
    if not _svg_has_text(svg_text):
        return direct, False
    try:
        substituted = rasterise_svg(substitute_fonts(svg_text), pixels, font=BUNDLED_LOGO_FONT)
    except Exception:  # noqa: BLE001
        return direct, False
    if substituted is None:
        return direct, False
    if direct is None:
        return substituted, True
    if _opaque_pixels(substituted) > _opaque_pixels(direct):
        return substituted, True
    return direct, False


def _fit_png(image, limit: int = MAX_STORED_LOGO_BYTES) -> bytes | None:
    """Re-encode as PNG at decreasing sizes until it fits the store's budget."""
    from PIL import Image as PILImage  # noqa: PLC0415 - Pillow is in the image

    current = image.convert("RGBA")
    for target in (LOGO_PIXELS, 384, 256, 192, 128, 96, 64):
        copy = current.copy()
        copy.thumbnail((target, target), PILImage.LANCZOS)
        buffer = io.BytesIO()
        copy.save(buffer, format="PNG", optimize=True)
        if buffer.tell() <= limit:
            return buffer.getvalue()
    return None


def rasterise_image(content: bytes, limit: int = MAX_STORED_LOGO_BYTES) -> bytes | None:
    """Any raster format Pillow reads -> a transparent PNG within ``limit``."""
    try:
        from PIL import Image as PILImage  # noqa: PLC0415

        with PILImage.open(io.BytesIO(content)) as opened:
            opened.load()
            return _fit_png(opened, limit)
    except Exception:  # noqa: BLE001 - an unreadable logo is a note, not a crash
        return None


def data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


# ---------------------------------------------------------------------------
# Accent colour


def _rgb_to_hsl(red: int, green: int, blue: int) -> tuple[float, float, float]:
    r, g, b = red / 255, green / 255, blue / 255
    high, low = max(r, g, b), min(r, g, b)
    lightness = (high + low) / 2
    if high == low:
        return 0.0, 0.0, lightness
    delta = high - low
    saturation = delta / (2 - high - low) if lightness > 0.5 else delta / (high + low)
    if high == r:
        hue = ((g - b) / delta) % 6
    elif high == g:
        hue = (b - r) / delta + 2
    else:
        hue = (r - g) / delta + 4
    return hue * 60, saturation, lightness


def accent_from_png(png: bytes) -> str | None:
    """The dominant saturated, non-neutral colour of the finished logo.

    Colours are weighted by coverage and by saturation, and neutrals (near
    white, near black, greys) are ignored so a logo on a white card yields its
    brand colour rather than the card. This is deliberately the logo's colour
    and not ``theme-color``: that is usually the page background.
    """
    try:
        from PIL import Image as PILImage  # noqa: PLC0415

        with PILImage.open(io.BytesIO(png)) as opened:
            small = opened.convert("RGBA")
            small.thumbnail((96, 96), PILImage.LANCZOS)
            pixels = small.load()
            width, height = small.size
    except Exception:  # noqa: BLE001
        return None

    buckets: dict[tuple[int, int, int], list[int]] = {}
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha < 200:
                continue
            _, saturation, lightness = _rgb_to_hsl(red, green, blue)
            if saturation < 0.25 or lightness < 0.12 or lightness > 0.88:
                continue
            # Coarse buckets so anti-aliased edges vote with the solid colour;
            # the bucket's exact colours are averaged so the result is the real
            # brand colour and not a rounded-off approximation of it.
            key = (red // 16 * 16, green // 16 * 16, blue // 16 * 16)
            totals = buckets.setdefault(key, [0, 0, 0, 0])
            totals[0] += 1
            totals[1] += red
            totals[2] += green
            totals[3] += blue
    if not buckets:
        return None

    def weight(item):
        key, (count, red, green, blue) = item
        _, saturation, _ = _rgb_to_hsl(red // count, green // count, blue // count)
        return count * (0.35 + saturation)

    _, (count, red, green, blue) = max(buckets.items(), key=weight)
    return f"#{round(red / count):02x}{round(green / count):02x}{round(blue / count):02x}"


def accent_from_svg(svg: str) -> str | None:
    """Fallback: the most saturated fill/stroke colour written in the SVG."""
    found: list[tuple[float, str]] = []
    for value in re.findall(r'(?:fill|stroke)\s*[:=]\s*"?(#[0-9A-Fa-f]{6}|#[0-9A-Fa-f]{3})', svg):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        red, green, blue = (int(digits[i:i + 2], 16) for i in (0, 2, 4))
        _, saturation, lightness = _rgb_to_hsl(red, green, blue)
        if saturation >= 0.25 and 0.12 <= lightness <= 0.88:
            found.append((saturation * (1 - abs(lightness - 0.5)), "#" + digits.lower()))
    if not found:
        return None
    return max(found)[1]


# ---------------------------------------------------------------------------
# Platform, geography, contacts


def detect_platform(page: SiteScan, html: str) -> dict:
    generator = page.metas.get("generator", "")
    low = html.lower()
    signals: list[str] = []
    kind = "other"

    if "wordpress" in generator.lower() or "/wp-content/" in low or "/wp-includes/" in low:
        kind = "wordpress"
        signals.append("wp-content" if "/wp-content/" in low else "generator")
    elif "shopify" in generator.lower() or "cdn.shopify.com" in low:
        kind = "shopify"
    elif "wix.com" in generator.lower() or "wixstatic.com" in low:
        kind = "wix"
    elif "squarespace" in generator.lower() or "squarespace.com" in low:
        kind = "squarespace"
    elif "webflow" in generator.lower() or "data-wf-site" in low:
        kind = "webflow"

    elementor = "elementor" in low
    if elementor:
        signals.append("elementor")
    return {
        "kind": kind,
        "generator": generator[:120],
        "elementor": elementor,
        "install_hint": {
            "wordpress": "Install on my site",
            "shopify": "Install on my site",
            "wix": "Install on my site",
            "webflow": "Email this to my web person",
            "squarespace": "Email this to my web person",
            "other": "Email this to my web person",
        }.get(kind, "Email this to my web person"),
        "signals": signals,
    }


_NZ_HINTS = (
    "new zealand", "aotearoa", "auckland", "wellington", "christchurch", "hamilton",
    "tauranga", "dunedin", "queenstown", "palmerston north", "napier", "hastings",
    "nelson", "rotorua", "invercargill", "whangarei", "porirua", "lower hutt", "upper hutt",
)


def infer_geo(page: SiteScan, html: str) -> dict:
    """Timezone and dialling country the site itself implies.

    The platform defaults are wrong for New Zealand (global country code ``1``,
    timezone ``America/Chicago``), so a site's own evidence overrides them. The
    evidence, strongest first: a structured address, a ``+64`` phone, New
    Zealand wording on the page, then the domain.
    """
    country_iso = ""
    for block in page.json_ld:
        address = block.get("address")
        if isinstance(address, dict):
            candidate = str(address.get("addressCountry", "")).strip().upper()
            if candidate:
                country_iso = candidate[:2]
    if not country_iso:
        match = re.search(r'"addressCountry"\s*:\s*"([A-Za-z]{2})"', html)
        if match:
            country_iso = match.group(1).upper()

    if country_iso in _COUNTRY_ISO:
        code, zone = _COUNTRY_ISO[country_iso]
        return {"country_code": code, "timezone": zone,
                "source": "address", "country_iso": country_iso}

    if any(normalise_phone(number).startswith("+64") for number in page.phones):
        return {"country_code": "64", "timezone": "Pacific/Auckland",
                "source": "phone number", "country_iso": "NZ"}

    haystack = f"{page.body_hints} {html[:200000]}".lower()
    if any(hint in haystack for hint in _NZ_HINTS):
        return {"country_code": "64", "timezone": "Pacific/Auckland",
                "source": "page wording", "country_iso": "NZ"}

    host = (urlsplit(page.url).hostname or "").lower()
    tld = host.rsplit(".", 1)[-1] if "." in host else ""
    if tld in _TLD_GEO:
        code, zone = _TLD_GEO[tld]
        return {"country_code": code, "timezone": zone,
                "source": "top-level domain", "country_iso": country_iso or tld.upper()}
    return {"country_code": "", "timezone": "", "source": "unknown", "country_iso": ""}


def normalise_phone(value: str) -> str:
    """Readable international-ish form; keeps a leading + when the site had one."""
    text = re.sub(r"^tel:", "", value.strip(), flags=re.I)
    digits = re.sub(r"[^\d+]", "", text)
    if not digits:
        return ""
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith("+"):
        return digits
    return digits


def contact_line(phones: list[str], emails: list[str]) -> dict:
    phone = next((p for p in (normalise_phone(value) for value in phones) if p), "")
    email = next((e for e in emails if e), "")
    return {"phone": phone, "email": email, "line": phone or email}


# ---------------------------------------------------------------------------
# The proposal


async def _read_site(url: str) -> tuple[str, str, list[tuple[str, bytes]]]:
    """Fetch the homepage and the logo candidates, all through PublicClient."""
    from .public_fetch import PublicClient  # noqa: PLC0415 - avoids a cycle at import

    parts = urlsplit(url)
    site_host = (parts.hostname or "").lower().removeprefix("www.")
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=False,
        timeout=FETCH_TIMEOUT,
        trust_env=False,
    ) as transport:
        client = PublicClient(transport, parts.hostname)
        response = await client.get(url)
        if response.status_code != 200:
            raise ValueError("That website did not answer with a page we can read")
        if len(response.content) > MAX_HTML_BYTES:
            raise ValueError("That page is too large to read")
        html = response.text

        page = scan(html, url)
        fetched: list[tuple[str, bytes]] = []
        for image in logo_candidates(page, site_host)[:4]:
            if image.url.startswith("data:"):
                inline = _decode_data_uri(image.url)
                if inline:
                    fetched.append((image.url[:64], inline))
                continue
            absolute = image.url if image.url.startswith("http") else _absolute(image.url, url)
            if not absolute:
                continue
            try:
                asset = await client.get(absolute)
            except (ValueError, httpx.HTTPError, OSError):
                continue
            if asset.status_code != 200 or not asset.content:
                continue
            if len(asset.content) > MAX_IMAGE_BYTES:
                continue
            fetched.append((absolute, asset.content))
    return html, site_host, fetched


def _absolute(href: str, base: str) -> str | None:
    from urllib.parse import urljoin  # noqa: PLC0415

    joined = urljoin(base, href.strip())
    parts = urlsplit(joined)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return joined


def _decode_data_uri(uri: str) -> bytes | None:
    try:
        header, _, payload = uri.partition(",")
        if ";base64" not in header:
            return None
        return base64.b64decode(payload, validate=True)
    except Exception:  # noqa: BLE001
        return None


def _logo_from(html: str, fetched: list[tuple[str, bytes]]) -> dict:
    """Pick the best candidate that yields a usable PNG, plus the alternatives."""
    alternatives: list[dict] = []
    chosen: dict | None = None
    chosen_accent: str | None = None

    for source, content in fetched:
        note = ""
        text_risk = False
        substituted = False
        png: bytes | None = None
        is_svg = _is_svg(content)
        svg_text = ""
        if is_svg:
            try:
                svg_text = content.decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                svg_text = ""
            text_risk = _svg_has_text(svg_text)
            png, substituted = render_logo_svg(svg_text)
            if png is None:
                note = "We could not draw this logo on our servers."
        else:
            png = rasterise_image(content)
            if png is None:
                note = "This image could not be read."

        if png is None:
            alternatives.append({"source": source, "why": note or "No usable image was found."})
            continue

        # The accent is taken from the logo we actually keep, never from a
        # candidate that failed to render or was passed over.
        accent = accent_from_png(png)
        if accent is None and is_svg:
            accent = accent_from_svg(svg_text)

        entry = {
            "source": source,
            "data": data_uri(png),
            "bytes": len(png),
            "rendered_from_svg": is_svg,
        }
        if text_risk:
            entry["text_font_risk"] = True
            entry["font_substituted"] = substituted
            entry["note"] = (
                "Your logo draws its words as text; we redrew them in a close match to "
                "your site's font. Check the preview looks right, or choose another image."
                if substituted else
                "This logo draws its words as text, and our servers have no matching font, "
                "so the preview may not look like your site. You can keep it, or choose "
                "another image below."
            )
        alternatives.append(entry)
        if chosen is None:
            chosen = entry
            chosen_accent = accent

    return {"logo": chosen, "alternatives": alternatives[:4], "accent": chosen_accent}


def _name(page: SiteScan) -> str:
    for key in ("og:site_name", "application-name", "apple-mobile-web-app-title"):
        value = page.metas.get(key, "").strip()
        if value:
            return value[:120]
    for block in page.json_ld:
        for key in ("name", "legalName"):
            value = block.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:120]
    if page.title:
        # "Trendi | Web design Auckland" -> "Trendi"
        head = re.split(r"\s[|–—·:-]\s", page.title)[0].strip()
        return (head or page.title)[:120]
    return ""


async def suggest(website: str) -> dict:
    """Everything the review screen needs for one website. Reads only; writes nothing."""
    url = normalise_site(website)
    html, site_host, fetched = await _read_site(url)
    page = scan(html, url)
    brand = _logo_from(html, fetched)

    accent = brand["accent"]
    accent_source = "logo"
    if not accent:
        theme = page.metas.get("theme-color", "").strip()
        if re.fullmatch(r"#[0-9A-Fa-f]{6}", theme):
            accent, accent_source = theme.lower(), "theme-color"

    geo = infer_geo(page, html)
    platform = detect_platform(page, html)
    contact = contact_line(page.phones, page.emails)

    notes: list[str] = []
    logo = brand["logo"]
    if logo is None:
        if brand["alternatives"]:
            notes.append("We found a logo on your site but could not turn it into an image. "
                         "Upload your own, or leave it and we will use your initials.")
        else:
            notes.append("We could not find a logo. Upload your own, or leave it and we "
                         "will use your initials.")
    elif logo.get("text_font_risk"):
        if logo.get("font_substituted"):
            notes.append("Your logo's lettering was redrawn in a close match to your site's "
                         "font. Check the preview looks right, or pick another image.")
        else:
            notes.append("The logo's lettering is drawn as text, so the preview may differ "
                         "from your site. Check it looks right, or pick another image.")
    if not accent:
        accent, accent_source = DEFAULT_ACCENT, "default"
        notes.append("We could not tell your brand colour. Pick one below.")
    if accent_source == "theme-color":
        notes.append("We could only read the page's theme colour, which is often the "
                     "background. Please confirm or change it.")
    if not geo["timezone"]:
        notes.append("We could not tell your timezone from the site. Choose one.")
    if not contact["line"]:
        notes.append("No phone or email was visible on the home page.")
    if not page.socials:
        notes.append("No social accounts were linked from the home page.")

    return {
        "website": url,
        "name": _name(page),
        "logo": logo,
        "logo_alternatives": brand["alternatives"],
        "accent": accent,
        "accent_source": accent_source,
        "contact": contact,
        "socials": page.socials,
        "platform": platform,
        "timezone": geo["timezone"],
        "country_code": geo["country_code"],
        "geo_source": geo["source"],
        "notes": notes,
        "host": site_host,
    }


def normalise_site(website: str) -> str:
    """Accept ``trendibizz.com`` or a full address; return the https URL to read."""
    value = (website or "").strip()
    if not value:
        raise ValueError("Enter your website address, for example yourbusiness.co.nz")
    if "://" not in value:
        value = "https://" + value
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Enter your website address, for example yourbusiness.co.nz")
    if parts.username or parts.password or parts.port not in (None, 443, 80):
        raise ValueError("Enter your website address, for example yourbusiness.co.nz")
    if "." not in parts.hostname:
        raise ValueError("Enter your website address, for example yourbusiness.co.nz")
    return "https://" + parts.hostname.lower().removeprefix("www.") + (parts.path or "/")
