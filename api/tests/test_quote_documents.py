"""A quotation handed to a customer must be a document, not a price on a screen.

Before this, a quote had no reference, no validity date, and the page never said who issued it or
their GST number — unusable as a legal NZ quotation and impossible to discuss on the phone.
"""

from datetime import date, timedelta

from app import billing


def test_references_are_readable_and_sortable():
    assert billing.format_reference("Pukeko", 1) == "PUKE-0001"
    assert billing.format_reference("Q", 12) == "Q-0012"
    assert billing.format_reference("", 3) == "Q-0003"


def test_a_reference_survives_a_junk_prefix():
    assert billing.format_reference("puke ko!!", 7) == "PUKE-0007"


def test_validity_defaults_to_thirty_days():
    assert billing.valid_until({}) == date.today() + timedelta(days=30)
    assert billing.valid_until({"quote_valid_days": 7}) == date.today() + timedelta(days=7)


def test_validity_is_clamped_to_something_sane():
    assert billing.valid_until({"quote_valid_days": 0}) == date.today() + timedelta(days=1)
    assert billing.valid_until({"quote_valid_days": 9999}) == date.today() + timedelta(days=365)


def test_an_expired_quote_is_recognised():
    yesterday = date.today() - timedelta(days=1)
    assert billing.is_expired(yesterday) is True
    assert billing.is_expired(date.today()) is False
    assert billing.is_expired(None) is False


def test_the_issuer_block_prints_only_what_exists():
    full = billing.details({"name": "Pukeko Construction", "gst_number": "123-456-789",
                            "business_address": "12 Main Rd", "business_phone": "09 123 4567"})
    assert full["name"] == "Pukeko Construction"
    assert full["gst_number"] == "123-456-789"
    empty = billing.details({})
    assert empty["gst_number"] == "" and empty["name"] == ""


def test_the_public_page_carries_reference_validity_and_terms():
    import inspect

    from app import quotations

    source = inspect.getsource(quotations.public_quote)
    for needle in ("reference", "valid_until", "issuer_html", "issuer['terms']"):
        assert needle in source, needle


def test_acceptance_is_refused_once_the_quote_expires():
    import inspect

    from app import quotations

    assert "is_expired" in inspect.getsource(quotations._decide)
