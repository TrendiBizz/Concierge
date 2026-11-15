"""The GEO daily check must notice real page changes, not Cloudflare's per-request noise.

Measured 2026-11-16: `/cdn-cgi/challenge-platform/...ray=<random>` is injected into every HTML
response, so the old `len(text)` fingerprint differed on every fetch. Two consecutive runs
(2026-11-15: 39/39 pages "changed", 2026-11-16: 43/43) reported the whole site as changed and
re-submitted every URL to IndexNow daily — a signal Bing is entitled to read as spam.
"""
import importlib.util
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


geo = load("concierge_geo_daily", REPO / "scripts" / "seo" / "geo-daily.py")


def served(ray: str, *, body: str = "<p>Reception answers 24/7.</p>",
           modified: str = "2026-11-15") -> str:
    """A page as the browser actually receives it: content plus Cloudflare's challenge script."""
    return (
        '<!doctype html><html><head><script type="application/ld+json">'
        f'{{"@type":"WebPage","dateModified":"{modified}"}}'
        "</script></head><body>"
        f"{body}"
        "<script>!function(){if(document.currentScript)"
        "{(function(){var b=document.createElement('script');"
        "b.nonce='{CSP_NONCE}';b.innerHTML=\"window.__CF$cv$params={r:'" + ray + "',t:'x'}\";"
        "document.head.appendChild(b);var u='/cdn-cgi/challenge-platform/scripts/jsd/main.js"
        "?ray=" + ray + "',a=document.createElement('script');a.src=u;"
        "document.head.appendChild(a)})();}}();</script></body></html>"
    )


def test_fingerprint_ignores_the_cloudflare_challenge_script():
    """Cloudflare injects the challenge script only on *some* responses, so the same page can
    arrive with or without it, and with a different ray token each time."""
    clean = served("a5b02818dae9d993").split("<script>!function()")[0] + "</body></html>"
    assert "<script>!function()" not in clean
    assert geo.fingerprint(clean) == geo.fingerprint(served("a5b02818dae9d993"))
    assert geo.fingerprint(clean) == geo.fingerprint(served("a5b0281b28cd1c5c"))


def test_fingerprint_notices_a_real_content_change():
    before = geo.fingerprint(served("a5b02818dae9d993"))
    after = geo.fingerprint(
        served("a5b02818dae9d993", body="<p>Reception answers 24/7, including holidays.</p>"))
    assert before != after, "edited page content must still count as changed"


def test_fingerprint_notices_a_new_date_modified():
    old = geo.fingerprint(served("a5b02818dae9d993", modified="2026-11-01"))
    new = geo.fingerprint(served("a5b02818dae9d993", modified="2026-11-16"))
    assert old != new
    assert new.endswith(":2026-11-16"), "the page's own dateModified must be carried in the state"
