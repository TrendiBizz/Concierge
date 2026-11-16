"""The quotation system: arithmetic, lifecycle, and the document the customer receives.

The old quotes module could add up lines and print a page. These tests pin the parts that make it a
professional document instead: a per-line unit and discount, a job discount, tax on the discounted
amount, frozen terms, a walk-in customer with no enquiry behind them, a lifecycle that tells
"approved" apart from "delivered", and an acceptance record.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import fastapi
import pytest
from pydantic import ValidationError

from app import quotations

LEAD = UUID("11111111-1111-4111-8111-111111111111")
TENANT = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"


def draft(lines=None, **overrides):
    payload = {
        "lead_id": LEAD,
        "title": "Workshop cladding",
        "currency": "NZD",
        "tax_basis_points": 1500,
        "lines": lines or [{"description": "Cladding", "quantity": "10",
                            "unit_price_cents": 10000}],
    }
    payload.update(overrides)
    return quotations.QuoteDraft(**payload)


# ------------------------------------------------------------------------------- arithmetic

def test_a_line_discount_reduces_only_its_own_line():
    totals = quotations.calculate(draft(lines=[
        {"description": "Cladding", "quantity": "10", "unit_price_cents": 10000,
         "discount_basis_points": 1000},
        {"description": "Scaffold", "quantity": "1", "unit_price_cents": 50000},
    ]))
    assert totals.lines[0]["gross_cents"] == 100000
    assert totals.lines[0]["line_discount_cents"] == 10000
    assert totals.lines[0]["amount_cents"] == 90000
    assert totals.lines[1]["amount_cents"] == 50000
    assert totals.subtotal_cents == 140000


def test_the_job_discount_comes_off_before_tax():
    totals = quotations.calculate(draft(
        discount_basis_points=500,
        lines=[{"description": "Job", "quantity": "1", "unit_price_cents": 200000}]))
    assert totals.subtotal_cents == 200000
    assert totals.discount_cents == 10000
    assert totals.tax_cents == 28500       # 15% of 190000, not of 200000
    assert totals.total_cents == 218500


def test_the_printed_parts_add_up_to_the_printed_total():
    totals = quotations.calculate(draft(
        discount_basis_points=333,
        lines=[{"description": "A", "quantity": "3.5", "unit_price_cents": 12345,
                "discount_basis_points": 250},
               {"description": "B", "quantity": "1", "unit_price_cents": 999}]))
    assert totals.subtotal_cents == sum(line["amount_cents"] for line in totals.lines)
    assert totals.total_cents == (totals.subtotal_cents - totals.discount_cents
                                  + totals.tax_cents)


def test_half_up_rounding_not_bankers_rounding():
    # 1.5 x 333 = 499.5 -> 500. Python's round() would give 500 here but 498.5 would go to 498.
    totals = quotations.calculate(draft(lines=[
        {"description": "Half", "quantity": "1.5", "unit_price_cents": 333}]))
    assert totals.lines[0]["amount_cents"] == 500
    # 1.5 x 249 = 373.5 -> 374, where round() would give 374 too, so use 2.5 x 99 = 247.5 -> 248.
    totals = quotations.calculate(draft(lines=[
        {"description": "Half", "quantity": "2.5", "unit_price_cents": 99}]))
    assert totals.lines[0]["amount_cents"] == 248


def test_a_hundred_percent_line_discount_is_allowed_but_not_more():
    line = {"description": "Free", "quantity": "1", "unit_price_cents": 500,
            "discount_basis_points": 10000}
    totals = quotations.calculate(draft(lines=[line]))
    assert totals.lines[0]["amount_cents"] == 0
    with pytest.raises(ValidationError):
        draft(lines=[{**line, "discount_basis_points": 10001}])


def test_absurd_totals_are_refused():
    with pytest.raises(fastapi.HTTPException):
        quotations.calculate(draft(lines=[
            {"description": "Everything", "quantity": "100000", "unit_price_cents": 100_000_000}]))


# ------------------------------------------------------------------------------- validation

def test_a_quote_needs_a_customer_or_an_enquiry():
    with pytest.raises(ValidationError):
        quotations.QuoteDraft(title="Nobody", currency="NZD",
                              lines=[{"description": "x", "quantity": "1", "unit_price_cents": 1}])


def test_a_walk_in_customer_needs_no_enquiry():
    body = quotations.QuoteDraft(title="Driveway", currency="NZD",
                                 customer={"name": "Hana", "email": "hana@example.com"},
                                 lines=[{"description": "x", "quantity": "1", "unit_price_cents": 1}])
    assert body.lead_id is None and body.customer.name == "Hana"


def test_a_price_cannot_stop_holding_before_the_quote_is_dated():
    with pytest.raises(ValidationError):
        draft(quote_date=date(2026, 11, 20), valid_until=date(2026, 11, 19))


def test_units_are_required_and_readable():
    with pytest.raises(ValidationError):
        draft(lines=[{"description": "x", "quantity": "1", "unit_price_cents": 1, "unit": "  "}])


# ------------------------------------------------------------------------------- lifecycle

def test_the_lifecycle_only_moves_forward():
    assert quotations.can_transition("draft", "reviewed")
    assert quotations.can_transition("reviewed", "sent")
    assert quotations.can_transition("sent", "accepted")
    assert quotations.can_transition("sent", "declined")
    assert quotations.can_transition("reviewed", "accepted")   # a verbal yes, recorded by the owner
    assert quotations.can_transition("accepted", "void")
    for illegal in [("draft", "accepted"), ("draft", "sent"), ("accepted", "draft"),
                    ("declined", "accepted"), ("void", "reviewed"), ("sent", "reviewed")]:
        assert not quotations.can_transition(*illegal), illegal


def test_unknown_statuses_are_never_allowed():
    assert not quotations.can_transition("draft", "paid")
    assert not quotations.can_transition("", "accepted")


# ------------------------------------------------------------------------------- the document

QUOTE = {
    "title": "Workshop clad", "currency": "NZD", "status": "sent", "reference": "PUKE-0012",
    "quote_date": date(2026, 11, 16), "valid_until": date(2026, 12, 16),
    "tax_basis_points": 1500, "discount_basis_points": 500,
    "lines": [
        {"description": "Cladding", "quantity": "42", "unit": "m2", "unit_price_cents": 18500,
         "line_discount_cents": 18500, "amount_cents": 758500},
        {"description": "Site visit", "quantity": "1", "unit": "each", "unit_price_cents": 25000,
         "line_discount_cents": 0, "amount_cents": 25000},
    ],
    "subtotal_cents": 783500, "discount_cents": 39175, "tax_cents": 111648,
    "total_cents": 855973, "notes": "Excludes scaffold.", "terms": "50% on order.",
    "contact": {"name": "Conrad", "company": "Conrad Builders", "email": "conrad@example.com"},
}
ISSUER = {"name": "Pukeko Construction", "address": "12 Main Rd", "phone": "09 123 4567",
          "gst_number": "123-456-789", "nzbn": "9429000000000", "terms": ""}
BRAND = {"name": "Pukeko Construction", "accent": "#c8f560"}


def render(quote=None, brand=None):
    return quotations.document_html(quote or QUOTE, ISSUER, brand or BRAND)


def test_the_document_shows_every_number_the_customer_needs():
    page = render()
    assert "PUKE-0012" in page
    assert "16 Nov 2026" in page and "16 Dec 2026" in page
    assert "Conrad Builders" in page
    assert "42 m2" in page
    assert "Discount (5.00%)" in page
    assert "GST 15%" in page
    assert "−" in page or "-" in page
    assert "Excludes scaffold." in page
    assert "50% on order." in page


def test_the_issuer_block_prints_gst_and_nzbn_only_when_they_exist():
    page = render()
    assert "GST 123-456-789" in page and "NZBN 9429000000000" in page
    bare = render(brand={"name": "Pukeko Construction"})
    assert "GST 123-456-789" in bare  # issuer still has them
    assert "NZBN" in bare


def test_a_zero_tax_quote_has_no_tax_row():
    page = render(quote={**QUOTE, "tax_cents": 0, "tax_basis_points": 0,
                         "total_cents": QUOTE["subtotal_cents"] - QUOTE["discount_cents"]})
    assert "GST 0%" not in page and "Tax 0%" not in page


def test_customer_text_is_escaped_not_executed():
    page = render(quote={**QUOTE, "contact": {"name": "<script>alert(1)</script>"}})
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_the_document_has_a_print_stylesheet_and_no_clickable_javascript():
    page = render()
    assert "@media print" in page
    assert "javascript:" not in page.lower()


def test_money_uses_the_right_symbol_and_never_a_wrong_one():
    assert quotations.money(123456, "NZD") == "$1,234.56"
    assert quotations.money(123456, "USD") == "US$1,234.56"
    assert quotations.money(123456, "SEK") == "1,234.56 SEK"
    assert quotations.money(0, "NZD") == "$0.00"


def test_quantities_print_without_trailing_zeros():
    assert quotations._q("12.000") == "12"
    assert quotations._q("12.500") == "12.5"
    assert quotations._q("<b>") == "&lt;b&gt;"


# ------------------------------------------------------------------------------- sending

class Row(dict):
    pass


class FakePool:
    def __init__(self, quote):
        self.quote = quote
        self.statements = []

    async def fetchrow(self, sql, *args):
        self.statements.append((sql, args))
        if sql.lstrip().startswith("UPDATE quotations"):
            self.quote = {**self.quote, "status": args[3], "version": self.quote["version"] + 1}
            return Row(self.quote)
        if "FROM quotations" in sql:
            return Row(self.quote)
        if "FROM tenants" in sql:
            return Row({"name": "Pukeko Construction", "quote_valid_days": 30})
        return None

    async def fetch(self, sql, *args):
        self.statements.append((sql, args))
        return []

    async def execute(self, sql, *args):
        self.statements.append((sql, args))
        return "UPDATE 1"


def wire(monkeypatch, pool):
    monkeypatch.setattr(quotations.db, "pool", lambda: pool)
    monkeypatch.setattr(quotations.owner_auth, "require_role", lambda *a, **k: None)


def sent_quote():
    return {"id": "q1", "tenant_id": TENANT, "lead_id": LEAD, "title": "Workshop clad",
            "currency": "NZD", "status": "reviewed", "version": 3, "public_token": "tok123",
            "valid_until": date.today() + timedelta(days=10), "lines": "[]", "contact":
            {"name": "Conrad", "email": "conrad@example.com"}, "subtotal_cents": 100,
            "discount_cents": 0, "tax_cents": 15, "total_cents": 115, "notes": "", "terms": ""}


def test_sending_marks_the_quote_sent_and_includes_the_owner_message(monkeypatch):
    quote = sent_quote()
    pool = FakePool(quote)
    wire(monkeypatch, pool)
    sent = {}

    async def capture(*args, **kwargs):
        sent.update(kwargs, body=args[4], to=args[3])
        return True

    monkeypatch.setattr(quotations.outbox, "enqueue", capture)
    asyncio_run = __import__("asyncio").run
    result = asyncio_run(quotations.send_quote(
        UUID("33333333-3333-4333-8333-333333333333"),
        quotations.SendRequest(subject="Your clad quote", message="Ring me if anything is unclear."),
        user={"tenant_id": TENANT, "role": "owner"}))
    assert result["status"] == "sent"
    assert sent["to"] == "conrad@example.com"
    assert "Ring me if anything is unclear." in sent["body"]
    assert "tok123" in sent["body"]
    updates = [s for s in pool.statements if "UPDATE quotations" in s[0]]
    assert updates and "status='sent'" in updates[0][0]


def test_a_draft_cannot_be_sent(monkeypatch):
    pool = FakePool({**sent_quote(), "status": "draft"})
    wire(monkeypatch, pool)
    with pytest.raises(fastapi.HTTPException) as exc:
        __import__("asyncio").run(quotations.send_quote(
            UUID("33333333-3333-4333-8333-333333333333"), None,
            user={"tenant_id": TENANT, "role": "owner"}))
    assert exc.value.status_code == 409


def test_an_expired_quote_cannot_be_sent(monkeypatch):
    pool = FakePool({**sent_quote(), "valid_until": date.today() - timedelta(days=1)})
    wire(monkeypatch, pool)
    with pytest.raises(fastapi.HTTPException) as exc:
        __import__("asyncio").run(quotations.send_quote(
            UUID("33333333-3333-4333-8333-333333333333"), None,
            user={"tenant_id": TENANT, "role": "owner"}))
    assert exc.value.status_code == 409


def test_the_totals_survive_a_json_round_trip():
    totals = quotations.calculate(draft(lines=[
        {"description": "Cladding", "quantity": "12.5", "unit_price_cents": 18500}]))
    stored = __import__("json").loads(__import__("json").dumps(totals.lines))
    assert stored[0]["quantity"] == "12.5"
    assert stored[0]["amount_cents"] == 231250
    assert stored[0]["unit"] == "each"
    assert Decimal(stored[0]["quantity"]) == Decimal("12.5")


class LifecyclePool:
    """Just enough database to exercise the two decisions that touch money."""

    def __init__(self, quote):
        self.quote = quote
        self.statements = []

    async def fetchrow(self, sql, *args):
        self.statements.append((sql, args))
        if sql.lstrip().startswith("UPDATE quotations"):
            self.quote = {**self.quote, "status": args[3], "version": self.quote["version"] + 1}
            return Row(self.quote)
        if "FROM quotations" in sql:
            return Row(self.quote)
        if "UPDATE tenants SET invoice_sequence" in sql:
            return Row({"invoice_sequence": 7, "initial": "P"})
        if "INSERT INTO invoices" in sql:
            return Row({"public_token": "inv1", "number": "P-0007"})
        if "FROM invoices" in sql:
            return None
        if "FROM tenants" in sql:
            return Row({"id": TENANT, "name": "Pukeko Construction", "deposit_percent": 50,
                        "allow_deposit": False, "invoice_payment_terms_days": 7,
                        "quote_valid_days": 30})
        return None

    async def fetch(self, sql, *args):
        self.statements.append((sql, args))
        return []

    async def execute(self, sql, *args):
        self.statements.append((sql, args))
        return "UPDATE 1"


def test_a_resend_is_not_swallowed_by_the_first_send(monkeypatch):
    pool = LifecyclePool({**sent_quote(), "status": "sent"})
    wire(monkeypatch, pool)
    monkeypatch.setattr(quotations.invoices.db, "pool", lambda: pool)
    keys = []

    async def capture(*args, **kwargs):
        keys.append(kwargs.get("dedupe_key"))
        return True

    monkeypatch.setattr(quotations.outbox, "enqueue", capture)
    __import__("asyncio").run(quotations.send_quote(
        UUID("33333333-3333-4333-8333-333333333333"), None,
        user={"tenant_id": TENANT, "role": "owner"}))
    assert keys and ":resend:" in keys[0]


def test_marking_a_quote_accepted_by_hand_still_issues_an_invoice(monkeypatch):
    pool = LifecyclePool({**sent_quote(), "status": "sent", "version": 4})
    wire(monkeypatch, pool)
    monkeypatch.setattr(quotations.invoices.db, "pool", lambda: pool)
    result = __import__("asyncio").run(quotations.change_status(
        UUID("33333333-3333-4333-8333-333333333333"),
        quotations.QuoteStatus(status="accepted", version=4, note="said yes on the phone"),
        user={"tenant_id": TENANT, "role": "owner", "email": "jo@example.com"}))
    inserts = [s for s in pool.statements if "INSERT INTO invoices" in s[0]]
    assert inserts, "an accepted quote with no invoice leaves the customer with nothing to pay"
    assert result["status"] == "accepted"
