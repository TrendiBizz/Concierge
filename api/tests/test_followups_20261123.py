"""Guards for the 23 Nov 2026 follow-ups: social posting is core, and the USD $250 price includes everything."""
import pathlib
import re

SITE = pathlib.Path(__file__).resolve().parents[2] / "website"
INCLUDES = ("phone number", "voicemail", "social posting")
PRICED_PAGES = ["concierge.html", "pricing.html", "ai-office.html", "ai-office-nz.html", "ai-office-cost.html", "terms.html", "llms.txt"]


def text(name):
    return (SITE / name).read_text(encoding="utf-8")


def test_social_posting_is_core_not_optional_on_concierge():
    t = text("concierge.html")
    assert "Optional: social post approvals" not in t
    assert "OPTIONAL, SEPARATE FROM THE RECEPTIONIST" not in t
    assert '<a href="#social">Social posting</a>' in t  # jump nav
    assert "<span>✓ Social posting</span>" in t  # hero chips
    assert "social posting with your approval" in t.lower()  # JSON-LD + FAQ
    for page in ("pricing.html", "ai-office.html"):
        assert "ocial posting" in text(page), page


def test_price_includes_everything_and_names_separate_products():
    for name in PRICED_PAGES:
        low = text(name).lower()
        for needle in INCLUDES:
            assert needle in low, (name, needle)
        assert "no extras" in low or "no extra charge" in low, name
        assert "separate products, priced separately" in low or "priced separately" in low, name


def test_phone_number_question_answers_yes_included():
    t = text("ai-office-cost.html")
    assert re.search(r'"name":"Does it include a phone number\?","acceptedAnswer":\{"@type":"Answer","text":"Yes\. Your business phone number is included', t)
    assert "Is there a setup fee?" in t and "Setup is included in the USD $250 a month" in t


def test_no_free_word_in_priced_pages():
    for name in PRICED_PAGES:
        assert not re.search(r"\bfree\b", text(name), re.I), name
