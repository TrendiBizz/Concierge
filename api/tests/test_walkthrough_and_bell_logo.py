"""Guards for Jo's 23 Nov bell-logo rule and the redesigned 'See Concierge in action' walkthrough."""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
WEBSITE = ROOT / "website"

ARROW_SVG_FRAGMENTS = (
    "M149 31l17-17",
    "M14 34l20-20",
    "m-13 0h13v13",
    "m-16 0h16v16",
)


def test_no_purple_arrow_logo_remains_in_live_brand_or_app_files():
    targets = [
        WEBSITE / "brand" / "logo-refresh.svg",
        WEBSITE / "brand" / "logo-horizontal.svg",
        WEBSITE / "brand" / "logo-horizontal-dark.svg",
        WEBSITE / "brand" / "mark-refresh.svg",
        WEBSITE / "brand" / "logo-symbol.svg",
        ROOT / "api" / "static" / "owner.html",
        ROOT / "web" / "portal" / "public" / "install.html",
        WEBSITE / "index.html",
        WEBSITE / "concierge.html",
        WEBSITE / "seo.html",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for frag in ARROW_SVG_FRAGMENTS:
            assert frag not in text, f"{path.relative_to(ROOT)} still contains arrow fragment {frag!r}"
        assert 'class="assistant-mark">↗<' not in text, f"{path.relative_to(ROOT)} still uses arrow assistant-mark"


def test_brand_svgs_use_concierge_bell_tile():
    for name in ("logo-refresh.svg", "logo-horizontal.svg", "logo-horizontal-dark.svg", "mark-refresh.svg", "logo-symbol.svg"):
        text = (WEBSITE / "brand" / name).read_text(encoding="utf-8")
        assert 'fill="#7142d6"' in text, name
        assert "M22 68 A28 28 0 0 1 78 68 Z" in text, f"{name} missing bell dome path"
        assert 'cx="39" cy="57"' in text and 'cx="50" cy="57"' in text and 'cx="61" cy="57"' in text, (
            f"{name} missing three dots inside bell"
        )


def test_crm_and_workflows_use_bell_favicon_not_emoji():
    for app in ("crm", "workflows"):
        html = (ROOT / app / "web" / "index.html").read_text(encoding="utf-8")
        assert "data:image/svg+xml" not in html, f"{app}/web/index.html still has inline emoji favicon"
        assert '/favicon.svg?v=20261124' in html, f"{app}/web/index.html missing bell favicon link"
        svg = (ROOT / app / "web" / "favicon.svg").read_text(encoding="utf-8")
        assert "M22 68 A28 28 0 0 1 78 68 Z" in svg, f"{app}/web/favicon.svg is not the bell tile"
        server_js = (ROOT / app / "server" / "server.js").read_text(encoding="utf-8")
        assert "'.svg': 'image/svg+xml'" in server_js, f"{app}/server/server.js missing .svg MIME type"


def test_walkthrough_accessibility_wording_and_bell_icon():
    js = (WEBSITE / "refresh.js").read_text(encoding="utf-8")
    css = (WEBSITE / "refresh.css").read_text(encoding="utf-8")
    assert not re.search(r"\bjamie\b", js, re.I), "walkthrough must not include personal names"
    assert not re.search(r"\bfree\b", js, re.I), "walkthrough must not use the word 'free'"
    assert "ArrowRight" in js and "ArrowLeft" in js and "Home" in js and "End" in js
    assert "prefers-reduced-motion" in js and "prefers-reduced-motion" in css
    assert "Ⅱ Pause walkthrough" in js

    for page_name, expected_steps in (("index.html", 10), ("concierge.html", 11)):
        html = (WEBSITE / page_name).read_text(encoding="utf-8")
        assert f'data-steps="{expected_steps}"' in html, page_name
        assert 'src="/brand/mark-refresh.svg?v=20261124"' in html, page_name
        assert 'role="tablist"' in html and 'role="tabpanel"' in html, page_name
        assert "Illustrative example · No live customer data" in html, page_name
        assert not re.search(r"<aside[^>]*class=\"walkthrough\"[^>]*>.*?style=", html), (
            f"{page_name} walkthrough must not use inline style attributes (CSP style-src 'self')"
        )
