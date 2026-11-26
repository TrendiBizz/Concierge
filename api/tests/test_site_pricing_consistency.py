"""One Concierge price everywhere (USD $199/month, set in website/products.js; SEO is $499).

2026-11-25: a QA record quoted "USD $400/month" and the question 'does pricing disagree?' had to be
answered by hand. Retired prices ($250 until 2026-11-24, and the never-live $400) must not return
to the site, llms.txt, the API greeting, or the settings file.
"""
import pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[2]
RETIRED = re.compile(r"(USD ?\$?|\$) ?(250|400|750)(?![0-9,.])(\s*(/|a|per)\s*month)?")

def _files():
    yield from (ROOT / "website").glob("*.html")
    for name in ("llms.txt", "products.js"):
        yield ROOT / "website" / name
    yield ROOT / "api" / "app" / "a2ui.py"
    yield ROOT / "concierge-stack" / "agent" / "agent.py"  # live chat widget prompt

def test_no_retired_concierge_price_is_published():
    bad = []
    for f in _files():
        for m in RETIRED.finditer(f.read_text(encoding="utf-8", errors="ignore")):
            if m.group(3) or m.group(1).startswith("USD"):
                bad.append(f"{f.name}: {m.group(0)}")
    assert not bad, bad

def test_the_price_in_settings_matches_the_pages():
    settings = (ROOT / "website" / "products.js").read_text(encoding="utf-8")
    assert re.search(r"monthly:\s*\{\s*price:\s*199", settings)
    for name in ("pricing.html", "ai-office-cost.html", "llms.txt"):
        assert "$199" in (ROOT / "website" / name).read_text(encoding="utf-8"), name
