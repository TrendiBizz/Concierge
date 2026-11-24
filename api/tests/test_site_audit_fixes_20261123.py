"""Site copy and funnel guards from the 23 Nov 2026 audit fixes (QA/verification/SITE_AUDIT_FIXES_2026-11-23.md)."""
import json
import pathlib
import re

SITE = pathlib.Path(__file__).resolve().parents[2] / "website"
PAGES = sorted(SITE.glob("*.html"))


def text(name):
    return (SITE / name).read_text(encoding="utf-8")


def test_setup_buttons_are_never_rewritten_into_stripe_checkout():
    js = text("main.js")
    assert "data-concierge-plan" not in js
    assert "a[data-concierge-pay]" in js
    for page in PAGES:
        assert "data-concierge-plan" not in page.read_text(encoding="utf-8"), page.name


def test_only_the_pricing_page_has_a_pay_button_and_it_is_explicit():
    holders = [p.name for p in PAGES if "data-concierge-pay" in p.read_text(encoding="utf-8")]
    assert holders == ["pricing.html"]
    assert 'href="/concierge-start' in text("pricing.html")  # setup form is the lead action


def test_stripe_links_and_prices_are_unchanged():
    products = text("products.js")
    assert "https://buy.stripe.com/eVq28s2qj9jfdxugHm04805" in products
    assert "https://buy.stripe.com/dRm7sM6GzeDz9he3UA04802" not in products
    assert "price: 199" in products and "price: 499" in products
    assert "price: 500" not in products


def test_pricing_leads_with_concierge_not_the_seo_package():
    html = text("pricing.html")
    assert "<h1>Concierge pricing" in html
    assert "chat assistant" not in html
    assert html.index("Concierge") < html.index("SEO and AI visibility")


def test_no_stale_phone_number_or_voicemail_copy():
    banned = ["cannot be created for you", "number cannot be created", "Voicemail notices are planned",
              "planned, not live", "separate terms", "own page and terms", "TRENDI LIMITED, a company",
              "including worldwide", "rents the phone number", "rented business phone number",
              "rented phone number", "number rental", "real ongoing cost", "set up for you in minutes",
              "in minutes, so you do not need to find a phone provider"]
    for page in PAGES:
        body = page.read_text(encoding="utf-8")
        for phrase in banned:
            assert phrase not in body, f"{page.name}: {phrase}"


def test_three_month_minimum_is_kept_with_implementation_reason():
    html = text("pricing.html")
    assert "3-month minimum" in html
    assert "setup, testing and implementation" in html
    assert "rents the phone number" not in html.lower()
    assert "number rental" not in html.lower()
    assert "trial" not in html.lower()


def test_integrations_listed_are_the_ones_in_code():
    code = (SITE.parent / "api" / "app" / "integrations.py").read_text(encoding="utf-8")
    assert 'PROVIDERS = ("xero", "m365", "servicem8", "tradify", "fergus")' in code
    for page in ("concierge.html", "ai-office.html", "ai-office-nz.html"):
        body = text(page)
        for name in ("ServiceM8", "Xero", "Tradify", "Fergus", "Microsoft 365", "Webhooks", "Voicemail is available now"):
            assert name in body, f"{page}: {name}"


def test_pen_testing_is_in_the_top_nav_and_concierge_is_first():
    all_pages = sorted(SITE.rglob("*.html"))
    for page in all_pages:
        nav = re.search(r'<nav aria-label="Main".*?</nav>', page.read_text(encoding="utf-8"), re.S)
        if nav:
            assert 'href="/penetration-testing"' in nav.group(0), page.relative_to(SITE)
            assert nav.group(0).index("/concierge") < nav.group(0).index("/seo"), page.relative_to(SITE)
    assert 'id="svc-pen"' in text("index.html")


def test_seo_plan_price_is_499_everywhere():
    banned = ("USD $500", "$500 / month", "$500 per month", "$500 a month", "$500 deposit",
              '"price":"500"', "500.00 USD")
    for path in list(SITE.rglob("*.html")) + [SITE / "llms.txt", SITE / "chatgpt-products.csv", SITE / "products.js"]:
        body = path.read_text(encoding="utf-8")
        for phrase in banned:
            assert phrase not in body, f"{path.relative_to(SITE)}: {phrase}"
    assert "USD $499" in text("pricing.html") and "USD $499" in text("seo.html")
    assert "499.00 USD" in text("chatgpt-products.csv")


def test_terms_is_one_standard_document():
    html = text("terms.html")
    for needle in ("one standard set of terms", "AI use and accuracy", "Privacy Act 2020",
                   "SMS and email messaging", "Minimum terms and cancellation", "Referral partners"):
        assert needle in html
    assert "separate terms" not in html.lower()


def test_visible_last_updated_matches_the_machine_date():
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December"]
    for page in list(PAGES) + sorted((SITE / "tools").glob("*.html")):
        body = page.read_text(encoding="utf-8")
        for date, shown in re.findall(r'data-updated="(\d{4}-\d\d-\d\d)"[^<]*?Last updated (\d{1,2} \w+ \d{4})', body):
            y, m, d = date.split("-")
            assert shown == f"{int(d)} {months[int(m) - 1]} {y}", page.name


def test_llms_txt_has_no_duplicate_urls_and_schema_area_served_has_no_duplicates():
    urls = re.findall(r"\]\((https://[^)]+)\)", text("llms.txt"))
    assert len(urls) == len(set(urls))
    for page in PAGES:
        for raw in re.findall(r'"areaServed":(\[[^\]]*\])', page.read_text(encoding="utf-8")):
            names = [x.lower() if isinstance(x, str) else x.get("name", "").lower() for x in json.loads(raw)]
            assert len(names) == len(set(names)), page.name


def test_ai_crawlers_are_allowed_in_robots_txt():
    robots = text("robots.txt")
    for agent in ("GPTBot", "ClaudeBot", "Google-Extended"):
        assert re.search(rf"User-agent: {agent}\nAllow: /", robots)


def test_html_is_edge_cacheable_and_deploy_purges():
    assert "s-maxage=3600" in text("_headers")
    deploy = (SITE.parent / "scripts" / "vps" / "deploy-site.sh").read_text(encoding="utf-8")
    assert "purge_cache" in deploy

