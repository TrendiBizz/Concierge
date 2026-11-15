"""The missed-call calculator must be arithmetically right and wired to the page it claims to be.

Why this exists: the calculator's whole value is that a business can trust the number and quote it
in a proposal. A tool that quietly miscalculates, or whose page and script have drifted apart, is
worse than no tool — it produces a confident wrong figure with our name on it.

The arithmetic lives in `website/tools/missed-call-cost-calculator.js` and is exercised through
Node, so the test runs the same code the browser does rather than a Python re-implementation that
could drift from it. The page test cross-checks that every element id the script reaches for exists.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
JS = REPO / "website" / "tools" / "missed-call-cost-calculator.js"
PAGE = REPO / "website" / "tools" / "missed-call-cost-calculator.html"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is required to exercise the calculator")


def run_js(script: str):
    """Run a snippet with the calculator module in scope and return its JSON result."""
    prelude = f"const calc = require({json.dumps(str(JS))});\n"
    result = subprocess.run([NODE, "-e", prelude + script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_weekly_monthly_and_yearly_figures_agree():
    """8 missed calls a week, $1,800 a job, 35% close: $5,040/wk, $21,840/mo, $262,080/yr."""
    result = run_js("""
      const r = calc.calculate({missedPerWeek: 8, jobValue: 1800, conversionPct: 35});
      console.log(JSON.stringify(r));
    """)
    assert result["lostPerWeek"] == pytest.approx(5040)
    assert result["lostPerMonth"] == pytest.approx(8 * 1800 * 0.35 * 52 / 12)
    assert result["lostPerYear"] == pytest.approx(262080)
    assert result["callsPerMonth"] == pytest.approx(8 * 52 / 12)


def test_the_month_is_a_calendar_month_not_four_weeks():
    """4.33 weeks a month, because 4 weeks × 12 = 48 weeks and the year would be short by a month."""
    weeks = run_js("console.log(JSON.stringify(calc.WEEKS_PER_MONTH));")
    assert weeks == pytest.approx(52 / 12)


def test_an_empty_form_produces_zero_rather_than_nan():
    result = run_js("console.log(JSON.stringify(calc.calculate({})));")
    assert result["lostPerMonth"] == 0
    assert result["lostPerYear"] == 0


def test_nonsense_input_is_clamped_instead_of_producing_a_wild_figure():
    result = run_js("""
      console.log(JSON.stringify(calc.calculate({missedPerWeek: -4, jobValue: -100, conversionPct: 400})));
    """)
    assert result["lostPerMonth"] == 0
    assert result["conversionPct"] == 100


def test_input_typed_with_separators_still_parses():
    result = run_js("""
      console.log(JSON.stringify(calc.calculate({missedPerWeek: '1,200', jobValue: '$1,800', conversionPct: '35%'})));
    """)
    assert result["missedPerWeek"] == 1200
    assert result["jobValue"] == 1800
    assert result["conversionPct"] == 35


def test_money_is_formatted_with_separators_and_a_currency():
    result = run_js("""
      console.log(JSON.stringify({
        plain: calc.money(21840),
        zero: calc.money(0),
        negative: calc.money(-1234.5),
        other: calc.money(1000, '$')
      }));
    """)
    assert result["plain"] == "21,840"
    assert result["zero"] == "0"
    assert result["negative"] == "-1,234"
    assert result["other"] == "$1,000"


def test_a_share_link_round_trips_the_calculation():
    result = run_js("""
      const q = calc.toQuery({missedPerWeek: 9, jobValue: 2500, conversionPct: 40, trade: 'plumber'});
      console.log(JSON.stringify({query: q, parsed: calc.fromQuery('?' + q)}));
    """)
    assert result["query"] == "missed=9&value=2500&close=40&trade=plumber"
    assert result["parsed"] == {"missedPerWeek": 9, "jobValue": 2500, "conversionPct": 40, "trade": "plumber"}


def test_a_hostile_share_link_is_not_executed_or_reflected():
    """The query string is read as numbers, never as markup; the trade label is length-capped."""
    result = run_js("""
      const p = calc.fromQuery('?missed=<script>alert(1)</script>&value=1e400&close=abc&trade=' + 'x'.repeat(200));
      console.log(JSON.stringify(p));
    """)
    assert result["missedPerWeek"] == 0
    assert result["conversionPct"] == 0
    assert len(result["trade"]) == 40


def test_every_element_the_script_uses_exists_on_the_page():
    """The classic failure: a renamed id leaves the output silently stuck at zero."""
    script = JS.read_text()
    page = PAGE.read_text()
    ids = set(re.findall(r"getElementById\('([^']+)'\)", script))
    assert ids, "the script looks for no page elements at all"
    missing = sorted(identifier for identifier in ids if f'id="{identifier}"' not in page)
    assert missing == [], f"the calculator script looks for ids the page does not have: {missing}"


def test_the_page_cannot_run_inline_script():
    """The site's CSP has no 'unsafe-inline'; an inline handler would fail in production only."""
    page = PAGE.read_text()
    inline = [tag for tag in re.findall(r"<script[^>]*>", page) if "src=" not in tag and "ld+json" not in tag]
    assert inline == []
    assert 'src="/tools/missed-call-cost-calculator.js"' in page


def test_the_page_states_what_it_leaves_out():
    """A calculator that only says "potential revenue" is a sales tactic. The limits are the product."""
    page = PAGE.read_text()
    for phrase in ("deliberately leaves out", "revenue, not profit", "close rate",
                   "example, not an average"):
        assert phrase.lower() in page.lower(), phrase


def test_the_page_is_substantial_and_correctly_indexed():
    page = PAGE.read_text()
    assert page.count("<h1") == 1
    assert '<link href="https://trendibizz.com/tools/missed-call-cost-calculator" rel="canonical"/>' in page
    words = len(re.findall(r"[A-Za-z0-9']+", re.sub(r"<[^>]+>", " ", page[page.find("<main"):page.find("</main>")])))
    assert words > 800, f"only {words} words in main content"
    assert '"FAQPage"' in page and '"WebApplication"' in page


def test_the_calculator_is_in_the_sitemap_and_linked_from_the_site():
    sitemap = (REPO / "website" / "sitemap.xml").read_text()
    assert "https://trendibizz.com/tools/missed-call-cost-calculator" in sitemap
    sources = [path.name for path in (REPO / "website").glob("*.html")
               if 'href="/tools/missed-call-cost-calculator"' in path.read_text(errors="replace")]
    assert len(sources) >= 3, f"only linked from {sources}"
    assert "missed-call-cost-calculator" in (REPO / "website" / "llms.txt").read_text()
