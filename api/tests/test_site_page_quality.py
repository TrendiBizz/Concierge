"""The site's own commercial pages must stay substantial, correctly labelled and correctly located.

Measured 2026-11-15: nine money pages carried 345-531 words, ten meta descriptions ran past the
snippet length, and a bulk geo rewrite had replaced the country name with "worldwide" — the terms
read "governed by worldwide law", the privacy policy cited "the worldwide Privacy Act 2020", the
buyer guide h1 said "in worldwide" and the sample report listed a search market called worldwide.
Nothing on the box watched these pages, so the damage shipped and sat there.
"""
import importlib.util
import pathlib
import re

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "vps" / "healthcheck.py"
_spec = importlib.util.spec_from_file_location("concierge_healthcheck_pages", SCRIPT)
healthcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(healthcheck)

GOOD = ('<html><head><link href="https://trendibizz.com/x" rel="canonical"/>'
        '<meta content="A short, accurate description of this page." name="description"/></head>'
        '<body><main><h1>Title</h1>' + '<p>word</p>' * 700 + '</main></body></html>')


def test_a_healthy_page_has_no_problems():
    assert healthcheck.page_quality(GOOD) == []


def test_thin_copy_is_reported():
    thin = GOOD.replace('<p>word</p>' * 700, '<p>word</p>' * 300)
    assert any("words (floor" in p for p in healthcheck.page_quality(thin))


def test_a_long_description_is_reported():
    long_desc = GOOD.replace('A short, accurate description of this page.', 'x' * 170)
    assert any("description 170 chars" in p for p in healthcheck.page_quality(long_desc))


def test_a_missing_canonical_is_reported():
    no_canon = re.sub(r'<link[^>]*rel="canonical"/>', '', GOOD)
    assert "no canonical" in healthcheck.page_quality(no_canon)


def test_two_h1_tags_are_reported():
    two = GOOD.replace('<h1>Title</h1>', '<h1>Title</h1><h1>Another</h1>')
    assert any("2 h1 tags" in p for p in healthcheck.page_quality(two))


def test_the_broken_location_wording_is_reported():
    """The exact strings the bulk rewrite produced on the live site."""
    for bad in ("<p>governed by worldwide law</p>",
                "<p>the worldwide Privacy Act 2020</p>",
                "<h1>How to choose the best AI receptionist in worldwide</h1>",
                "<td>worldwide</td>",
                "<h2>worldwide</h2>"):
        broken = GOOD.replace('<p>word</p>', bad + '<p>word</p>', 1)
        assert "broken location wording" in healthcheck.page_quality(broken), bad


def test_the_check_is_wired_into_the_report():
    """A check that is defined but never called is worse than no check: it looks like coverage."""
    source = SCRIPT.read_text()
    loops = re.findall(r"for step in \(([^)]*)\)", source, re.S)
    assert any("check_site_pages" in loop for loop in loops), (
        "check_site_pages must be part of a report loop")


def test_the_page_check_reads_the_whole_document(monkeypatch):
    """http() truncates at 4 KB for the other checks; a page check that does the same sees only the
    <head>, which is why the first live run reported "234 words, 0 h1 tags" for a 1,090-word page."""
    import http.server
    import threading

    page = ('<html><head><title>t</title><link href="/x" rel="canonical"/>'
            '<meta content="A short and accurate description." name="description"/></head>'
            '<body><main><h1>Heading</h1>' + '<p>word word</p>' * 400 + '</main></body></html>').encode()
    thin = b'<html><body><main><h1>t</h1><p>short</p></main></body></html>'

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = thin if self.path == "/thin" else page
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(healthcheck, "SITE", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setattr(healthcheck, "MONEY_PAGES", ("/",))
        results = healthcheck.check_site_pages()
        assert results[0]["status"] == "ok", results[0]["detail"]
        monkeypatch.setattr(healthcheck, "MONEY_PAGES", ("/thin",))
        results = healthcheck.check_site_pages()
        assert results[0]["status"] == "fail"
        assert "words (floor" in results[0]["detail"]
    finally:
        server.shutdown()
