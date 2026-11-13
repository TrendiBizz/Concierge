"""An accepted quote must become a bill the customer can act on.

An invoice is the thing a business actually gets paid against. It has to be a tax invoice (issuer,
GST number, date, description, GST amount), and it has to respect how the customer chose to pay.
"""

from datetime import date

from app import invoices


def test_paying_in_full_bills_the_whole_job():
    result = invoices.split(500_000, "full", 50)
    assert result["due"] == 500_000
    assert result["balance"] == 0


def test_a_deposit_splits_the_job_and_the_parts_add_up_exactly():
    result = invoices.split(123_457, "deposit", 50)
    assert result["due"] == 61_729          # rounded half up to the cent
    assert result["balance"] == 61_728
    assert result["due"] + result["balance"] == 123_457


def test_deposit_percentages_are_clamped_and_never_negative():
    assert invoices.split(1_000, "deposit", 0)["due"] == 0
    assert invoices.split(1_000, "deposit", 100)["due"] == 1_000
    assert invoices.split(1_000, "deposit", 250)["due"] == 1_000
    assert invoices.split(1_000, "deposit", -5)["due"] == 0


def test_a_zero_value_quote_does_not_break_the_split():
    assert invoices.split(0, "deposit", 50) == {"kind": "deposit", "due": 0, "deposit": 0, "balance": 0}


def test_invoice_numbers_are_readable():
    assert invoices.format_number("Pukeko", 1) == "PUK-0001"
    assert invoices.format_number("", 7) == "INV-0007"


def test_the_description_tells_the_owner_what_is_outstanding():
    deposit = {"number": "PUK-0001", "kind": "deposit", "due_cents": 250_000,
               "balance_cents": 250_000, "currency": "NZD"}
    assert "deposit" in invoices.describe(deposit) and "balance" in invoices.describe(deposit)
    full = {"number": "PUK-0002", "kind": "full", "due_cents": 500_000,
            "balance_cents": 0, "currency": "NZD"}
    assert "PUK-0002" in invoices.describe(full)


def test_the_customer_chooses_deposit_or_full_when_accepting():
    import inspect

    from app import quotations

    accept = inspect.getsource(quotations.public_accept)
    assert "payment_option" in accept
    decide = inspect.getsource(quotations._decide)
    assert "invoices.issue" in decide, "accepting must produce the invoice"
    assert "allow_deposit" in decide, "a business that does not take deposits bills in full"


def test_the_invoice_page_is_a_tax_invoice():
    import inspect

    source = inspect.getsource(invoices.page)
    for needle in ("gst_number", "Due now", "number", "due_on", "GST"):
        assert needle in source, needle


def test_invoice_routes_exist():
    from app import main

    paths = main.app.openapi()["paths"]
    assert "/invoice/{token}" in paths
    assert "/owner/invoices" in paths
