"""The renamed /ai-receptionist* pages must redirect, and the health check must notice if they stop.

website.mjs once cached _redirects at start, so a deploy that added the rules left the old URLs 404
until the container restarted. The file, the health check list and the loader are pinned here.
"""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("concierge_healthcheck_redirects", ROOT / "scripts/vps/healthcheck.py")
healthcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(healthcheck)


def _rules():
    rules = {}
    for line in (ROOT / "website/_redirects").read_text().splitlines():
        parts = line.split()
        if len(parts) == 3 and not line.startswith("#"):
            rules[parts[0]] = (parts[1], parts[2])
    return rules


def test_every_renamed_page_redirects_with_and_without_slash_and_html():
    rules = _rules()
    for old, new in healthcheck.RENAMED_PAGES.items():
        for variant in (old, old + "/", old + ".html"):
            assert rules.get(variant) == (new, "301"), variant


def test_money_pages_use_the_new_urls_only():
    assert not [p for p in healthcheck.MONEY_PAGES if "receptionist" in p and p != "/virtual-receptionist"]
    for new in healthcheck.RENAMED_PAGES.values():
        assert new in healthcheck.MONEY_PAGES or new == "/how-does-an-ai-office-work"


def test_site_pages_fails_when_an_old_url_does_not_redirect(monkeypatch):
    monkeypatch.setattr(healthcheck, "http", lambda *a, **k: (200, b"<html></html>", 0.0))
    monkeypatch.setattr(healthcheck, "page_quality", lambda *_a, **_k: [])
    monkeypatch.setattr(healthcheck, "redirect_of", lambda url, timeout=10.0: (404, ""))
    result = healthcheck.check_site_pages()
    assert result[0]["status"] != "ok" and "/ai-receptionist" in result[0]["detail"]


def test_site_pages_passes_when_old_urls_redirect(monkeypatch):
    wanted = {}
    for old, new in healthcheck.RENAMED_PAGES.items():
        wanted[old] = wanted[old + "/"] = new
    monkeypatch.setattr(healthcheck, "http", lambda *a, **k: (200, b"<html></html>", 0.0))
    monkeypatch.setattr(healthcheck, "page_quality", lambda *_a, **_k: [])
    monkeypatch.setattr(healthcheck, "redirect_of",
                        lambda url, timeout=10.0: (301, wanted[url[len(healthcheck.SITE):]]))
    assert healthcheck.check_site_pages()[0]["status"] == "ok"


def test_website_server_rereads_redirects_when_the_file_changes():
    source = (ROOT / "scripts/vps/website.mjs").read_text()
    assert "mtimeMs" in source and "await loadRedirects()" in source


def test_removed_pages_are_410_gone():
    """Deliberately removed pages answer 410 Gone (not 404) so search engines drop them."""
    source = (ROOT / "scripts/vps/website.mjs").read_text()
    assert "code===410" in source and "status=410" in source
    rules = {}
    for line in (ROOT / "website/_redirects").read_text().splitlines():
        parts = line.split()
        if parts and not parts[0].startswith("#"):
            rules[parts[0]] = parts[1:]
    for slug in ("trendi-vs-smith-ai", "trendi-vs-goodcall", "trendi-vs-upfirst"):
        for variant in (f"/{slug}", f"/{slug}/", f"/{slug}.html"):
            assert rules.get(variant, [None, None])[-1] == "410", variant
        assert not (ROOT / f"website/{slug}.html").exists()
