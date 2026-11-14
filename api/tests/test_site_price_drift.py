"""The published price must match the plan data, and GST must never be an add-on again.

On 2026-11-15 the plan data was changed to USD 250/month but the hard-coded cards still said
$400 and the yearly blurb still reasoned from the old numbers ("12 months at USD $250 is USD
$4,800"). Prices live in two places, so they need a check that compares them.
"""
import importlib.util
import pathlib

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "vps" / "healthcheck.py"
_spec = importlib.util.spec_from_file_location("concierge_healthcheck_prices", SCRIPT)
healthcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(healthcheck)

PLANS = 'monthly: { price: 250, stripeLink: "" },\n  yearly: { price: 2700, stripeLink: "" }'
CARDS = ('<p class="price"><span class="currency">USD</span> $250<small>/ month</small></p>'
         '<p class="price"><span class="currency">USD</span> $2,700<small>/ year</small></p>')


def test_matching_cards_and_plans_are_clean():
    assert healthcheck.site_price_drift(CARDS, PLANS) == []


def test_a_stale_monthly_card_is_reported():
    stale = CARDS.replace("$250", "$400", 1)
    problems = healthcheck.site_price_drift(stale, PLANS)
    assert problems and "monthly card says $400" in problems[0]


def test_a_stale_yearly_card_is_reported():
    stale = CARDS.replace("$2,700", "$4,080")
    problems = healthcheck.site_price_drift(stale, PLANS)
    assert problems and "yearly card says $4080" in problems[0]


def test_any_gst_wording_comes_back_as_a_problem():
    problems = healthcheck.site_price_drift(
        CARDS, PLANS,
        {"/pricing": "Prices in USD, including GST.", "/terms": "Prices in USD."})
    assert problems == ["/pricing mentions GST; the site must not discuss it"]


def test_a_page_without_cards_does_not_invent_problems():
    assert healthcheck.site_price_drift("<p>no prices here</p>", PLANS) == []
