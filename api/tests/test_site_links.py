"""The site sends customers to the Studio and links to final addresses, not redirects.

Audit 2026-11-16: 87 links pointed at the old `/owner-ui` sign-in while the Studio is the sign-in,
and 7 outbound documentation links (Google, the RFC, Perplexity, OpenAI, Facebook) answered with a
redirect, so each page depended on a third party's old URL forever.
"""

import pathlib

SITE = pathlib.Path(__file__).resolve().parents[2] / "website"
TEXT = (".html", ".js", ".txt", ".json", ".xml", "_redirects")


def site_files():
    for path in SITE.rglob("*"):
        if path.is_file() and path.name.endswith(TEXT):
            yield path, path.read_text(encoding="utf-8", errors="ignore")


def test_no_page_sends_a_customer_to_the_old_sign_in():
    stale = [str(p.relative_to(SITE)) for p, text in site_files() if "concierge.trendibizz.com/owner-ui" in text]
    assert stale == [], f"still pointing at /owner-ui: {stale}"


def test_the_sign_in_links_land_on_the_studio():
    redirects = (SITE / "_redirects").read_text()
    assert "https://concierge.trendibizz.com/studio/" in redirects
    assert "https://concierge.trendibizz.com/studio/" in (SITE / "contact.html").read_text()


def test_outbound_links_use_the_final_address_not_a_redirect():
    moved = ("developers.google.com/search/docs/crawling-indexing/overview-google-crawlers",
             "developers.google.com/search/docs/crawling-indexing/robots/robots_txt",
             "developers.google.com/search/docs/crawling-indexing/google-common-crawlers",
             "rfc-editor.org/rfc/rfc9309", "docs.perplexity.ai/guides/bots",
             "platform.openai.com/docs/bots", "facebook.com/profile.php?id=")
    hits = [(str(p.relative_to(SITE)), m) for p, text in site_files() for m in moved if m in text]
    assert hits == [], f"links that redirect: {hits[:5]}"
