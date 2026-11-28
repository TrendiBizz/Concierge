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

PLANS = 'monthly: { price: 199, stripeLink: "" },\n  yearly: { price: 2149, stripeLink: "" }'
CARDS = ('<p class="price"><span class="currency">USD</span> $199<small>/ month</small></p>'
         '<p class="price"><span class="currency">USD</span> $2,149<small>/ year</small></p>')


def test_matching_cards_and_plans_are_clean():
    assert healthcheck.site_price_drift(CARDS, PLANS) == []


def test_a_stale_monthly_card_is_reported():
    stale = CARDS.replace("$199", "$400", 1)
    problems = healthcheck.site_price_drift(stale, PLANS)
    assert problems and "monthly card says $400" in problems[0]


def test_a_stale_yearly_card_is_reported():
    stale = CARDS.replace("$2,149", "$4,080")
    problems = healthcheck.site_price_drift(stale, PLANS)
    assert problems and "yearly card says $4080" in problems[0]


def test_gst_addon_wording_comes_back_as_a_problem_while_inclusive_nz_gst_is_allowed():
    problems = healthcheck.site_price_drift(
        CARDS, PLANS,
        {"/pricing": "Prices in USD, plus GST.", "/terms": "NZ customers: 15% GST included. Outside NZ: 0% GST."})
    assert problems == ["/pricing says GST is added on top; NZ GST must be included in the price"]
    assert healthcheck.site_price_drift(
        CARDS, PLANS,
        {"/pricing": "Prices in USD. NZ customers: 15% GST included. Outside NZ: 0% GST."}) == []


def test_a_page_without_cards_does_not_invent_problems():
    assert healthcheck.site_price_drift("<p>no prices here</p>", PLANS) == []


def test_a_retired_stripe_link_is_reported():
    problems = healthcheck.site_price_drift(
        CARDS, PLANS, {"/pricing": '<a href="https://buy.stripe.com/28E8wRbntdSjcsQg7RcEw03">Buy</a>'})
    assert problems == ["/pricing links to retired Stripe link 28E8wRbntdSjcsQg7RcEw03"]
    old_250 = healthcheck.site_price_drift(
        CARDS, PLANS, {"/products.js": 'stripeLink: "https://buy.stripe.com/dRm7sM6GzeDz9he3UA04802"'})
    assert old_250 == ["/products.js links to retired Stripe link dRm7sM6GzeDz9he3UA04802"]


def test_a_non_answer_tax_faq_is_reported_and_a_real_answer_is_not():
    faq = "<summary>Do prices include tax?</summary><p>Prices are in USD. </p>"
    assert healthcheck.site_price_drift(CARDS, PLANS, {"/pricing": faq}) == [
        "/pricing tax FAQ is a non-answer; it must say prices include tax"]
    good = faq.replace(
        "Prices are in USD. ",
        "Yes — the price shown is the full amount you pay, and prices include tax. Prices are in USD.",
    )
    assert healthcheck.site_price_drift(CARDS, PLANS, {"/pricing": good}) == []
