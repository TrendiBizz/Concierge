"""Item E — getting paid on an accepted quotation, processor-free.

The state machine is the product here: a customer may say they paid, only the owner may say they
did. These tests pin that down, plus the URL safety on the payment link.
"""
import asyncio

from app import quote_payments


def quote(**over):
    base = {"id": "q1", "tenant_id": "t1", "status": "accepted", "payment_status": "unpaid",
            "total_cents": 150000, "currency": "NZD", "title": "Driveway", "payment_reference": ""}
    base.update(over)
    return base


# ------------------------------------------------------------------ state machine

def test_only_an_accepted_unpaid_quote_can_be_declared():
    assert quote_payments.can_declare(quote()) is True
    assert quote_payments.can_declare(quote(status="reviewed")) is False
    assert quote_payments.can_declare(quote(payment_status="declared")) is False
    assert quote_payments.can_declare(quote(payment_status="paid")) is False


def test_a_declaration_is_never_a_payment():
    # The customer can declare; only the owner can confirm. Both states must be reachable for the
    # same quote, and 'declared' must not be treated as money.
    assert quote_payments.can_confirm(quote(payment_status="declared")) is True
    assert quote_payments.can_declare(quote(payment_status="declared")) is False
    assert quote_payments.can_confirm(quote(payment_status="paid")) is False
    assert quote_payments.can_confirm(quote(status="draft")) is False


def test_an_unknown_stored_state_is_treated_as_unpaid():
    assert quote_payments.state_of(quote(payment_status="refunded-ish")) == "unpaid"
    assert quote_payments.state_of({}) == "unpaid"
    assert quote_payments.state_of(quote(payment_status="PAID")) == "paid"


def test_the_customer_message_matches_the_state():
    tenant = {"payment_instructions": "Bank 12-3456"}
    assert quote_payments.customer_message(quote(payment_status="paid"), tenant) == \
        "Payment received. Thank you."
    assert "not accepted" in quote_payments.customer_message(quote(status="draft"), tenant)
    assert quote_payments.customer_message(quote(payment_status="waived"), tenant) == \
        "No payment is required on this quotation."
    assert "will confirm" in quote_payments.customer_message(quote(payment_status="declared"), tenant)
    assert quote_payments.customer_message(quote(), tenant) == ""


# ------------------------------------------------------------------ payment details

def test_payment_details_are_optional_and_reported_honestly():
    assert quote_payments.instructions_for({})["available"] is False
    assert quote_payments.instructions_for({"payment_instructions": "  "})["available"] is False
    both = quote_payments.instructions_for(
        {"payment_instructions": "Bank 12-3456", "payment_url": "https://pay.example/x"})
    assert both["available"] is True and both["url"].startswith("https://")


def test_a_dangerous_or_relative_url_is_never_offered():
    for url in ("javascript:alert(1)", "/relative", "data:text/html,x", "ftp://x"):
        assert quote_payments.instructions_for({"payment_url": url})["url"] == ""
    assert quote_payments.instructions_for({"payment_url": "http://pay.example"})["url"]


# ------------------------------------------------------------------ database effects

class FakePool:
    def __init__(self, update_returns=None):
        self.update_returns = update_returns
        self.executed = []
        self.fetchrow_calls = []

    async def fetchrow(self, sql, *args):
        self.fetchrow_calls.append((" ".join(sql.split()), args))
        if "UPDATE quotations" in sql:
            return self.update_returns
        return None

    async def execute(self, sql, *args):
        self.executed.append((" ".join(sql.split()), args))
        return "INSERT 0 1"


def _patch(monkeypatch, pool):
    monkeypatch.setattr(quote_payments.db, "pool", lambda: pool)


def test_declare_records_an_event_and_keeps_the_status_declared(monkeypatch):
    pool = FakePool(update_returns={"id": "q1", "payment_status": "declared"})
    _patch(monkeypatch, pool)
    result = asyncio.run(quote_payments.declare(quote(), reference="REF-9"))
    assert result == {"ok": True, "payment_status": "declared"}
    kinds = [row[1][2] for row in pool.executed if "INSERT INTO quote_payments" in row[0]]
    assert kinds == ["declared"]
    args = [row for row in pool.executed if "INSERT INTO quote_payments" in row[0]][0][1]
    assert args[3] == 150000  # amount recorded, so revenue can be reported
    assert args[4] == "REF-9"


def test_declaring_twice_is_idempotent(monkeypatch):
    pool = FakePool(update_returns=None)  # the guarded UPDATE matched nothing
    _patch(monkeypatch, pool)
    result = asyncio.run(quote_payments.declare(quote()))
    assert result["ok"] is False
    assert [row for row in pool.executed if "INSERT INTO quote_payments" in row[0]] == []


def test_confirming_moves_to_paid_and_records_who(monkeypatch):
    pool = FakePool(update_returns={"id": "q1", "payment_status": "paid"})
    _patch(monkeypatch, pool)
    result = asyncio.run(quote_payments.confirm(quote(payment_status="declared"), by="owner@x.test"))
    assert result == {"ok": True, "payment_status": "paid"}
    event = [row for row in pool.executed if "INSERT INTO quote_payments" in row[0]][0][1]
    assert event[2] == "paid"
    assert event[5] == "owner@x.test"


def test_a_waiver_is_recorded_as_a_waiver(monkeypatch):
    pool = FakePool(update_returns={"id": "q1", "payment_status": "waived"})
    _patch(monkeypatch, pool)
    assert asyncio.run(quote_payments.confirm(quote(), waive=True))["payment_status"] == "waived"
    event = [row for row in pool.executed if "INSERT INTO quote_payments" in row[0]][0][1]
    assert event[2] == "waived"


def test_an_unaccepted_quote_cannot_be_declared_or_confirmed(monkeypatch):
    pool = FakePool()
    _patch(monkeypatch, pool)
    assert asyncio.run(quote_payments.declare(quote(status="reviewed")))["ok"] is False
    assert asyncio.run(quote_payments.confirm(quote(status="reviewed")))["ok"] is False
    assert pool.fetchrow_calls == []  # no database write was even attempted


def test_the_owner_is_told_when_a_customer_claims_payment(monkeypatch):
    sent = {}

    class Pool(FakePool):
        async def fetchrow(self, sql, *args):
            if "FROM tenants" in sql:
                return {"id": "t1", "name": "Pukeko", "slug": "pukeko", "notify_email": ""}
            return None

    pool = Pool()
    _patch(monkeypatch, pool)

    async def queue(tenant, subject, body, dedupe, **kw):
        sent.update(subject=subject, body=body, dedupe=dedupe)

    monkeypatch.setattr(quote_payments.owner_notifications, "queue", queue)
    asyncio.run(quote_payments.notify_declared(quote(), "REF-9"))
    assert "Payment claimed" in sent["subject"]
    assert "1,500.00" in sent["body"] and "REF-9" in sent["body"]
    assert sent["dedupe"].startswith("payment-declared:")


def test_the_money_summary_is_integers_never_none(monkeypatch):
    class Pool(FakePool):
        async def fetchrow(self, sql, *args):
            return {"paid_cents": None, "declared_cents": 500, "outstanding_cents": None,
                    "declared_count": 1, "paid_count": None}

    _patch(monkeypatch, Pool())
    summary = asyncio.run(quote_payments.summary("t1"))
    assert summary["paid_cents"] == 0 and summary["declared_cents"] == 500
    assert all(isinstance(value, int) for value in summary.values())
