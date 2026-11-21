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


def page(*, body: str = "<p>Reception answers 24/7.</p>", modified: str = "2026-11-15") -> str:
    """The page as we deploy it, before Cloudflare touches the response."""
    return (
        '<!doctype html><html><head><script type="application/ld+json">'
        f'{{"@type":"WebPage","dateModified":"{modified}"}}'
        "</script></head><body>"
        f"{body}"
        "</body></html>"
    )


def served(ray: str, *, body: str = "<p>Reception answers 24/7.</p>",
           modified: str = "2026-11-15", csp_nonce: str = "q0ZiStVEcQdM9g==",
           include_challenge: bool = True) -> str:
    """The same page as the browser receives it: content plus Cloudflare's per-request additions."""
    challenge = (
        "<script>!function(){if(document.currentScript)"
        "{(function(){var b=document.createElement('script');"
        "b.nonce='{CSP_NONCE}';b.innerHTML=\"window.__CF$cv$params={r:'" + ray + "',t:'x'}\";"
        "document.head.appendChild(b);var u='/cdn-cgi/challenge-platform/scripts/jsd/main.js"
        "?ray=" + ray + "',a=document.createElement('script');a.src=u;"
        "document.head.appendChild(a)})();}}();</script>"
    )
    # Cloudflare Web Analytics beacon plus a CSP-styled element, each stamped with a fresh
    # per-request nonce (seen live from 2026-11-21).
    beacon = (
        '<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js/vce70182"'
        ' integrity="sha512-UKNk8GbxkABx" nonce="' + csp_nonce + '"'
        ' data-cf-beacon=\'{"version":"2024","rayId":"' + ray + '"}\'></script>'
        f'<style nonce="{csp_nonce}">body{{color:#111}}</style>'
    )
    base = page(body=body, modified=modified).removesuffix("</body></html>")
    return base + (challenge if include_challenge else "") + beacon + "</body></html>"



def test_fingerprint_ignores_the_cloudflare_analytics_nonce():
    """Cloudflare stamps a new CSP nonce on its beacon and styles on every request. Hashing it
    made all 44 pages look changed on 2026-11-21 and 2026-11-22 and re-pinged IndexNow daily."""
    first = geo.fingerprint(served("a5b02818dae9d993", csp_nonce="q0ZiStVEcQdM9g=="))
    second = geo.fingerprint(served("a5b02818dae9d993", csp_nonce="B+DhXGOJbgOcsj+F4dcgVw=="))
    assert first == second


def test_fingerprint_ignores_a_fresh_ray_and_nonce_together():
    a = geo.fingerprint(served("a5b02818dae9d993", csp_nonce="aaa111=="))
    b = geo.fingerprint(served("a5b0281b28cd1c5c", csp_nonce="bbb222=="))
    assert a == b


def test_csp_nonce_stripping_keeps_a_real_style_change_visible():
    a = geo.fingerprint(served("a5b02818dae9d993", body="<p>Reception answers 24/7.</p>"))
    b = geo.fingerprint(served("a5b02818dae9d993", body="<p>Reception answers 24/7, holidays too.</p>"))
    assert a != b



def test_fingerprint_ignores_the_cloudflare_challenge_script():
    """Cloudflare injects the challenge script only on *some* responses, so the same page can
    arrive with or without it, and with a different ray token each time."""
    clean = served("a5b02818dae9d993", include_challenge=False)
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
