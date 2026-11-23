"""The website's technical SEO contract must be enforced by a check that can actually fail.

Measured 2026-11-15 before this existed: the sitemap was hand-edited (one malformed `<url>` line, a
URL with no `lastmod`), 13 `lastmod` values disagreed with the pages they described, a 1,043-word
guide (`/glossary`) was `noindex` and missing from the sitemap entirely, 11 pages published no date
at all, and 21 AppleDouble `._*` files were committed to the web root. Nothing watched any of it.

These tests cover three layers: the source-tree audit (`scripts/seo/site_seo.py`), the live check
(`check_site_seo` in the health check), and the wiring that makes them run without anyone
remembering to.
"""
import importlib.util
import json
import pathlib
import re
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SITE = REPO / "website"


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


site_seo = load("concierge_site_seo", REPO / "scripts" / "seo" / "site_seo.py")
healthcheck = load("concierge_healthcheck_seo", REPO / "scripts" / "vps" / "healthcheck.py")

KEY = "0123456789abcdef0123456789abcdef"


def page(url: str, *, title: str = "Page title", description: str | None = None,
         canonical: str | None = None, robots: str = "index, follow", date: str = "2026-11-01",
         h1: str = "<h1>Heading</h1>", body: str = "", ld: bool = True) -> str:
    description = description or f"Description for {url}."
    canonical_link = (f'<link href="{canonical or site_seo.SITE + url}" rel="canonical"/>'
                      if canonical is not False else "")
    data = ""
    if ld:
        data = (f'<script type="application/ld+json">{{"@context":"https://schema.org","@graph":['
                f'{{"@type":"WebPage","url":"{site_seo.SITE + url}","dateModified":"{date}"}}]}}</script>')
    return (f'<html><head><title>{title}</title>'
            f'<meta content="{robots}" name="robots"/>'
            f'<meta content="{description}" name="description"/>'
            f'<meta content="https://trendibizz.com/brand/og-image.png" property="og:image"/>'
            f'{canonical_link}{data}</head><body><main>{h1}{body}</main></body></html>')


ROBOTS = """User-agent: Googlebot
Allow: /

User-agent: Bingbot
Allow: /

User-agent: OAI-SearchBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Claude-SearchBot
Allow: /

User-agent: GPTBot
Allow: /

User-agent: CCBot
Allow: /

User-agent: Bytespider
Disallow: /

User-agent: ClaudeBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: Applebot-Extended
Allow: /

User-agent: Amazonbot
Allow: /

User-agent: *
Allow: /

Sitemap: https://trendibizz.com/sitemap.xml
"""


def make_site(tmp: pathlib.Path, pages: dict[str, str] | None = None, robots: str = ROBOTS) -> pathlib.Path:
    root = tmp / "website"
    root.mkdir()
    pages = pages if pages is not None else {
        "index.html": page("/", title="Home"),
        "about.html": page("/about", title="About"),
    }
    for name, html in pages.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(html, encoding="utf-8")
    (root / "robots.txt").write_text(robots, encoding="utf-8")
    (root / "indexnow-key.json").write_text(json.dumps(
        {"key": KEY, "keyLocation": f"https://trendibizz.com/{KEY}.txt"}), encoding="utf-8")
    (root / f"{KEY}.txt").write_text(KEY, encoding="utf-8")
    (root / "sitemap.xml").write_text(site_seo.build_sitemap(root), encoding="utf-8")
    return root


def rewrite(root: pathlib.Path, name: str, html: str) -> None:
    (root / name).write_text(html, encoding="utf-8")


def test_a_clean_site_tree_passes(tmp_path):
    root = make_site(tmp_path)
    assert site_seo.audit(root) == []


def test_the_real_site_tree_passes_its_own_contract():
    """The committed site must satisfy the gate that the deploy script enforces."""
    problems = site_seo.audit(SITE)
    assert problems == [], "site_seo.py check would refuse to deploy:\n" + "\n".join(problems)


def test_a_missing_canonical_is_reported(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="About", canonical=False))
    assert any("about.html: no canonical link" in p for p in site_seo.audit(root))


def test_a_canonical_pointing_at_another_page_is_reported(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="About", canonical=site_seo.SITE + "/elsewhere"))
    problems = site_seo.audit(root)
    assert any("about.html: canonical is" in p for p in problems)


def test_an_accidental_noindex_is_reported(tmp_path):
    """The /glossary defect: a full guide excluded from search with no decision behind it."""
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="About", robots="noindex, follow"))
    assert any("about.html: noindex" in p for p in site_seo.audit(root))


def test_a_googlebot_noindex_under_an_index_robots_meta_is_reported(tmp_path):
    """/research/ai-crawler-blocking-2026 and /glossary, 15 Nov 2026: robots said index, googlebot said noindex."""
    root = make_site(tmp_path)
    html = page("/about", title="About").replace(
        '<meta content="index, follow" name="robots"/>',
        '<meta content="index, follow" name="robots"/><meta content="noindex, follow" name="googlebot"/>')
    rewrite(root, "about.html", html)
    problems = site_seo.audit(root)
    assert any("about.html: robots metas disagree" in p for p in problems), problems


def test_a_bingbot_noindex_under_an_index_robots_meta_is_reported(tmp_path):
    """Bing's own crawler meta is obeyed too, and it feeds ChatGPT search."""
    root = make_site(tmp_path)
    html = page("/about", title="About").replace(
        '<meta content="index, follow" name="robots"/>',
        '<meta content="index, follow" name="robots"/><meta content="noindex, follow" name="bingbot"/>')
    rewrite(root, "about.html", html)
    problems = site_seo.audit(root)
    assert any("about.html: robots metas disagree" in p for p in problems), problems


def test_a_crawler_specific_noindex_is_allowed_where_noindex_is_the_policy(tmp_path):
    root = make_site(tmp_path, pages={
        "index.html": page("/", title="Home"),
        "404.html": page("/404", title="Not found", robots="noindex, follow").replace(
            "</head>", '<meta content="noindex, nofollow" name="googlebot"/></head>'),
    })
    assert not any("googlebot" in p for p in site_seo.audit(root))


def test_the_allowed_noindex_pages_must_stay_noindex(tmp_path):
    root = make_site(tmp_path, pages={
        "index.html": page("/", title="Home"),
        "404.html": page("/404", title="Not found", robots="index, follow"),
    })
    assert any("404.html: expected noindex" in p for p in site_seo.audit(root))


def test_a_page_without_a_date_is_reported(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="About", ld=False))
    assert any("about.html: no dateModified" in p for p in site_seo.audit(root))


def test_a_future_date_is_reported(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="About", date="2999-01-01"))
    assert any("in the future" in p for p in site_seo.audit(root))


def test_a_broken_internal_link_is_reported(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="About",
                                     body='<p><a href="/gone">gone</a></p>'))
    assert any("link /gone has no target file" in p for p in site_seo.audit(root))


def test_a_link_served_by_redirects_is_accepted(tmp_path):
    """`/concierge/sign-in` is a 302 to the portal. It is a healthy link, not a broken one."""
    root = make_site(tmp_path)
    (root / "_redirects").write_text("/concierge/sign-in https://concierge.trendibizz.com/owner-ui 302\n",
                                     encoding="utf-8")
    rewrite(root, "about.html", page("/about", title="About",
                                     body='<p><a href="/concierge/sign-in">Sign in</a></p>'))
    assert site_seo.audit(root) == []


def test_duplicate_titles_are_reported(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="Home"))
    assert any("title duplicates" in p for p in site_seo.audit(root))


def test_a_snippet_that_would_be_cut_is_reported(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="About", description="x" * 170))
    assert any("description 170 chars" in p for p in site_seo.audit(root))


def test_a_sitemap_that_omits_a_page_is_reported(tmp_path):
    root = make_site(tmp_path)
    (root / "sitemap.xml").write_text(
        site_seo.build_sitemap(root).replace("<url><loc>https://trendibizz.com/about</loc>"
                                             "<lastmod>2026-11-01</lastmod></url>", ""),
        encoding="utf-8")
    assert any("sitemap missing" in p for p in site_seo.audit(root))


def test_a_stale_sitemap_lastmod_is_reported(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="About", date="2026-11-15"))
    assert any("sitemap lastmod for https://trendibizz.com/about" in p for p in site_seo.audit(root))


def test_a_visible_date_that_disagrees_with_the_schema_is_reported(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="About", date="2026-11-01",
                                     body='<p class="fine" data-updated="2026-11-15">Updated</p>'))
    assert any("visible date 2026-11-15" in p for p in site_seo.audit(root))


def test_appledouble_files_are_reported(tmp_path):
    root = make_site(tmp_path)
    (root / "._index.html").write_bytes(b"\x00\x05\x16\x07")
    assert any("AppleDouble" in p for p in site_seo.audit(root))


def test_a_robots_file_that_blocks_google_is_reported(tmp_path):
    root = make_site(tmp_path, robots=ROBOTS.replace("User-agent: Googlebot\nAllow: /",
                                                     "User-agent: Googlebot\nDisallow: /"))
    assert any("robots.txt: Googlebot is blocked" in p for p in site_seo.audit(root))


def test_a_blocked_bytespider_that_stopped_being_blocked_is_reported(tmp_path):
    root = make_site(tmp_path, robots=ROBOTS.replace("User-agent: Bytespider\nDisallow: /", ""))
    assert any("training crawler Bytespider is not blocked" in p for p in site_seo.audit(root))


def test_an_ai_crawler_that_gets_blocked_again_is_reported(tmp_path):
    root = make_site(tmp_path, robots=ROBOTS.replace("User-agent: GPTBot\nAllow: /", "User-agent: GPTBot\nDisallow: /"))
    assert any("robots.txt: GPTBot is blocked" in p for p in site_seo.audit(root))


def test_the_sitemap_is_deterministic_and_starts_with_the_homepage(tmp_path):
    root = make_site(tmp_path)
    first = site_seo.build_sitemap(root)
    assert first == site_seo.build_sitemap(root)
    assert first.index("https://trendibizz.com/</loc>") < first.index("/about</loc>")


def test_noindex_pages_are_left_out_of_the_sitemap(tmp_path):
    root = make_site(tmp_path, pages={
        "index.html": page("/", title="Home"),
        "404.html": page("/404", title="Not found", robots="noindex, follow"),
    })
    assert "/404" not in site_seo.build_sitemap(root)


def test_an_unsubmittable_key_file_is_reported(tmp_path):
    root = make_site(tmp_path)
    (root / f"{KEY}.txt").write_text("a different key", encoding="utf-8")
    assert any("does not contain the key" in p for p in site_seo.audit(root))


def test_indexnow_payload_names_the_changed_urls(monkeypatch):
    sent = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        sent["body"] = json.loads(request.data.decode())
        sent["url"] = request.full_url
        return Response()

    monkeypatch.setattr(site_seo.urllib.request, "urlopen", fake_urlopen)
    status = site_seo.ping_indexnow(["https://trendibizz.com/about"])
    assert status == 200
    assert sent["url"] == "https://api.indexnow.org/indexnow"
    assert sent["body"]["urlList"] == ["https://trendibizz.com/about"]
    data = json.loads((SITE / "indexnow-key.json").read_text())
    assert sent["body"]["key"] == data["key"]
    assert sent["body"]["keyLocation"] == data["keyLocation"]


def test_indexnow_with_nothing_to_say_sends_nothing(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("no request should be made when nothing changed")

    monkeypatch.setattr(site_seo.urllib.request, "urlopen", explode)
    assert site_seo.ping_indexnow([]) == 0


def test_changed_urls_reads_changed_pages_from_git():
    """IndexNow must be told about pages that changed, not about every page every deploy."""
    result = subprocess.run(["git", "-C", str(REPO), "log", "--format=%H", "-3", "--", "website/index.html"],
                            capture_output=True, text=True)
    commits = result.stdout.split()
    if len(commits) < 2:
        pytest.skip("need at least two commits touching the site")
    urls = site_seo.changed_urls(commits[-1] + "^")
    assert "https://trendibizz.com/" in urls
    assert all(url.startswith("https://trendibizz.com/") for url in urls)


# --- the live check on the box -------------------------------------------------------------

def fake_http(routes: dict[str, tuple[int, bytes]]):
    def fetch(url, timeout=10.0, headers=None, method="GET", read_limit=4096):
        status, body = routes.get(url, (0, b"not found"))
        return status, body, 0.0
    return fetch


def live_site(page_html: str = page("/about", title="About"), robots: str = ROBOTS) -> dict:
    return {
        "https://trendibizz.com/robots.txt": (200, robots.encode()),
        "https://trendibizz.com/sitemap.xml": (
            200, b'<?xml version="1.0"?><urlset><url><loc>https://trendibizz.com/about</loc></url></urlset>'),
        "https://trendibizz.com/about": (200, page_html.encode()),
        "https://trendibizz.com/indexnow-key.json": (200, json.dumps({"key": KEY}).encode()),
        f"https://trendibizz.com/{KEY}.txt": (200, KEY.encode()),
    }


def test_the_live_check_passes_on_a_healthy_site(monkeypatch):
    monkeypatch.setattr(healthcheck, "http", fake_http(live_site()))
    results = healthcheck.check_site_seo()
    assert [r["status"] for r in results] == ["ok"], results


def test_the_live_check_catches_a_blocked_googlebot(monkeypatch):
    routes = live_site(robots=ROBOTS.replace("User-agent: Googlebot\nAllow: /",
                                             "User-agent: Googlebot\nDisallow: /"))
    monkeypatch.setattr(healthcheck, "http", fake_http(routes))
    results = healthcheck.check_site_seo()
    assert results[0]["status"] == "fail"
    assert "blocks googlebot" in results[0]["detail"]


def test_the_live_check_catches_a_noindex_page_in_the_sitemap(monkeypatch):
    routes = live_site(page("/about", title="About", robots="noindex, follow"))
    monkeypatch.setattr(healthcheck, "http", fake_http(routes))
    results = healthcheck.check_site_seo()
    assert results[0]["status"] == "fail"
    assert "noindex but listed in the sitemap" in results[0]["detail"]


def test_the_live_check_catches_a_wrong_canonical(monkeypatch):
    routes = live_site(page("/about", title="About", canonical="https://trendibizz.com/elsewhere"))
    monkeypatch.setattr(healthcheck, "http", fake_http(routes))
    results = healthcheck.check_site_seo()
    assert results[0]["status"] == "fail"
    assert "canonical is" in results[0]["detail"]


def test_the_live_check_catches_a_broken_indexnow_key(monkeypatch):
    routes = live_site()
    routes[f"https://trendibizz.com/{KEY}.txt"] = (200, b"wrong")
    monkeypatch.setattr(healthcheck, "http", fake_http(routes))
    results = healthcheck.check_site_seo()
    assert results[0]["status"] == "fail"
    assert "does not serve the key" in results[0]["detail"]


def test_the_live_check_is_wired_into_the_report():
    source = (REPO / "scripts" / "vps" / "healthcheck.py").read_text()
    loops = re.findall(r"for step in \(([^)]*)\)", source, re.S)
    assert any("check_site_seo" in loop for loop in loops), "site:seo is defined but never run"


def test_the_deploy_runs_the_contract_before_publishing_and_pings_afterwards():
    """Wiring is the difference between a check and a decoration."""
    script = (REPO / "scripts" / "vps" / "deploy-site.sh").read_text()
    check_at = script.index("site_seo.py\" check")
    rsync_at = script.index("rsync -a --delete")
    verify_at = script.index("verify-deploy.sh")
    ping_at = script.index("ping --changed-in")
    assert check_at < rsync_at, "the SEO contract must be checked before the site is published"
    assert verify_at < ping_at, "IndexNow should be pinged once parity is proven"
    assert "set -euo pipefail" in script


# --- the published dataset ------------------------------------------------------------------

DATASET_PAGE = ('<html><head><title>Data</title><link href="https://trendibizz.com/data" rel="canonical"/>'
                '<meta content="A short description." name="description"/>'
                '<meta content="index, follow" name="robots"/>'
                '<script type="application/ld+json">{"@context":"https://schema.org","@graph":['
                '{"@type":"WebPage","url":"https://trendibizz.com/data","dateModified":"2026-11-01"},'
                '{"@type":"Dataset","name":"D","temporalCoverage":"2026-11-01",'
                '"distribution":{"@type":"DataDownload","encodingFormat":"text/csv",'
                '"contentUrl":"https://trendibizz.com/data/data.csv"}}]}</script></head>'
                '<body><main><h1>Data</h1></main></body></html>')


def dataset_site(tmp: pathlib.Path, page_html: str = DATASET_PAGE, linkers: int = 3) -> pathlib.Path:
    pages = {"index.html": page("/", title="Home"), "data.html": page_html}
    for number in range(linkers):
        pages[f"linker{number}.html"] = page(f"/linker{number}", title=f"Linker {number}",
                                             body='<p><a href="/data">data</a></p>')
    root = make_site(tmp, pages=pages)
    (root / "data").mkdir()
    (root / "data" / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (root / "sitemap.xml").write_text(site_seo.build_sitemap(root), encoding="utf-8")
    return root


def test_a_dataset_with_nothing_to_download_is_reported(tmp_path):
    root = dataset_site(tmp_path, page_html=DATASET_PAGE.replace(
        '"distribution":{"@type":"DataDownload","encodingFormat":"text/csv",'
        '"contentUrl":"https://trendibizz.com/data/data.csv"}', '"distribution": null'))
    assert any("Dataset has no distribution" in p for p in site_seo.audit(root))


def test_a_dataset_csv_that_does_not_exist_is_reported(tmp_path):
    root = dataset_site(tmp_path, page_html=DATASET_PAGE.replace("/data/data.csv", "/data/missing.csv"))
    assert any("has no file" in p for p in site_seo.audit(root))


def test_original_data_nothing_links_to_is_reported(tmp_path):
    """The 2026 research page was the site's best link asset and no page linked to it at all."""
    root = dataset_site(tmp_path, linkers=1)
    assert any("linked from only 1 other page" in p for p in site_seo.audit(root))


def test_a_properly_linked_dataset_passes(tmp_path):
    root = dataset_site(tmp_path)
    problems = [p for p in site_seo.audit(root) if "Dataset" in p or "original data" in p]
    assert problems == []


def csv_rows(count: int) -> bytes:
    return ("header\n" + "\n".join(f"row{number}" for number in range(count))).encode()


def data_routes(collected: str, rows: int = 100, page_extra: str = "") -> dict:
    page_html = DATASET_PAGE.replace("2026-11-01", collected) + page_extra
    return {
        "https://trendibizz.com/research/ai-crawler-blocking-2026": (200, page_html.encode()),
        "https://trendibizz.com/research/ai-crawler-blocking-2026/data.csv": (200, csv_rows(rows)),
    }


def test_fresh_data_passes(monkeypatch):
    import datetime as dt
    today = dt.date.today().isoformat()
    monkeypatch.setattr(healthcheck, "http", fake_http(data_routes(today)))
    assert healthcheck.check_site_data()[0]["status"] == "ok"


def test_data_older_than_the_monthly_promise_warns(monkeypatch):
    import datetime as dt
    old = (dt.date.today() - dt.timedelta(days=60)).isoformat()
    monkeypatch.setattr(healthcheck, "http", fake_http(data_routes(old)))
    result = healthcheck.check_site_data()[0]
    assert result["status"] == "warn" and "monthly refresh" in result["detail"]


def test_data_months_stale_fails(monkeypatch):
    import datetime as dt
    old = (dt.date.today() - dt.timedelta(days=200)).isoformat()
    monkeypatch.setattr(healthcheck, "http", fake_http(data_routes(old)))
    assert healthcheck.check_site_data()[0]["status"] == "fail"


def test_a_dataset_without_a_date_fails(monkeypatch):
    routes = data_routes("2026-11-01", page_extra="")
    routes["https://trendibizz.com/research/ai-crawler-blocking-2026"] = (
        200, DATASET_PAGE.replace('"temporalCoverage":"2026-11-01",', "").encode())
    monkeypatch.setattr(healthcheck, "http", fake_http(routes))
    result = healthcheck.check_site_data()[0]
    assert result["status"] == "fail" and "temporalCoverage" in result["detail"]


def test_a_truncated_csv_fails(monkeypatch):
    monkeypatch.setattr(healthcheck, "http", fake_http(data_routes("2026-11-01", rows=3)))
    result = healthcheck.check_site_data()[0]
    assert result["status"] == "fail" and "rows" in result["detail"]


def test_the_data_check_is_wired_into_the_report():
    source = (REPO / "scripts" / "vps" / "healthcheck.py").read_text()
    loops = re.findall(r"for step in \(([^)]*)\)", source, re.S)
    assert any("check_site_data" in loop for loop in loops)


def test_host_tooling_has_a_supported_way_to_reach_the_box():
    """A change to scripts/vps used to leave verify-deploy red with no documented remedy.

    The site deploy publishes `website/` only. Host tooling is published by copying, and until this
    script existed the only way to do it was a hand-run rsync — the same undocumented step that
    produced the drifts AGENTS.md is written to prevent.
    """
    script = REPO / "scripts" / "vps" / "sync-tooling.sh"
    assert script.is_file(), "sync-tooling.sh is missing"
    assert script.stat().st_mode & 0o111, "sync-tooling.sh must be executable"
    body = script.read_text()
    assert "rsync" in body and "scripts/vps" in body
    assert "--exclude '._*'" in body and "__pycache__" in body
    assert body.rstrip().endswith('"$REPO_ROOT/scripts/vps/verify-deploy.sh"') or "verify-deploy.sh" in body
    assert "REFUSING" in body, "tooling must refuse to publish an uncommitted tree"
    agreement = (REPO / "AGENTS.md").read_text()
    assert "sync-tooling.sh" in agreement, "AGENTS.md must tell agents how to publish host tooling"


# ------------------------------------------------ the 2026-11-16 additions to the contract

def test_a_heading_that_skips_a_level_is_reported(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="About", h1="<h1>About</h1><h3>Skipped a level</h3>"))
    assert any("about.html: heading jumps from h1 to h3" in p for p in site_seo.audit(root))


def test_an_image_without_an_alt_attribute_is_reported(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="About", body='<img src="/brand/logo-refresh.svg">'))
    assert any("about.html: image without an alt attribute" in p for p in site_seo.audit(root))


def test_an_empty_alt_is_a_decision_and_is_allowed(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="About", body='<img alt="" src="/brand/logo-refresh.svg">'))
    assert site_seo.audit(root) == []


def test_broken_structured_data_is_reported(tmp_path):
    root = make_site(tmp_path)
    broken = page("/about", title="About").replace(
        '</head>', '<script type="application/ld+json">{"@type": oops}</script></head>')
    rewrite(root, "about.html", broken)
    assert any("about.html: structured data is not valid JSON" in p for p in site_seo.audit(root))


def test_a_page_with_no_structured_data_is_reported(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="About", ld=False))
    assert any("about.html: no JSON-LD structured data" in p for p in site_seo.audit(root))


def test_a_duplicate_description_is_reported(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "index.html", page("/", title="Home", description="The same sentence twice."))
    rewrite(root, "about.html", page("/about", title="About", description="The same sentence twice."))
    problems = site_seo.audit(root)
    assert any("description duplicates" in p and ("about.html" in p or "index.html" in p) for p in problems), problems


def test_a_missing_absolute_og_image_is_reported(tmp_path):
    root = make_site(tmp_path)
    rewrite(root, "about.html", page("/about", title="About").replace(
        '<meta content="https://trendibizz.com/brand/og-image.png" property="og:image"/>',
        '<meta content="/brand/og-image.png" property="og:image"/>'))
    assert any("about.html: og:image must be an absolute https URL" in p for p in site_seo.audit(root))
