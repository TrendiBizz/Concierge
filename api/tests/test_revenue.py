"""Item F — attributed revenue: the numbers, the deltas and the honesty of both."""
import asyncio

import pytest

from app import revenue


# ------------------------------------------------------------------ arithmetic

def test_percent_change_handles_no_basis_and_no_change():
    assert revenue.percent_change(10, 10) == 0
    assert revenue.percent_change(15, 10) == 50
    assert revenue.percent_change(5, 10) == -50
    # No previous period cannot be a percentage; it must not invent one.
    assert revenue.percent_change(0, 0) is None
    assert revenue.percent_change(7, 0) == 100


def test_per_enquiry_and_rates_never_divide_by_zero():
    assert revenue.per_enquiry(100000, 10) == 10000
    assert revenue.per_enquiry(100000, 0) == 0
    assert revenue.convert_rate(3, 4) == 75.0
    assert revenue.convert_rate(0, 0) == 0.0
    assert revenue.convert_rate(1, 3) == 33.3


# ------------------------------------------------------------------ shape

def test_the_report_puts_the_previous_period_beside_the_current_one():
    current = {"enquiries": 40, "by_channel": {"phone": 20, "email": 15, "chat": 5},
               "quotes_sent": 10, "quotes_accepted": 4, "accepted_cents": 400000,
               "paid_cents": 250000, "outstanding_cents": 150000, "currency": "NZD"}
    previous = {"enquiries": 20, "by_channel": {"phone": 10, "email": 10},
                "quotes_sent": 8, "quotes_accepted": 2, "accepted_cents": 200000}
    report = revenue.build(current, previous)
    assert report["enquiries"] == 40 and report["enquiries_previous"] == 20
    assert report["enquiries_change_percent"] == 100
    assert report["accepted_value"] == 4000.0
    assert report["accepted_previous_value"] == 2000.0
    assert report["accepted_change_percent"] == 100
    assert report["accept_rate_percent"] == 40.0
    assert report["paid_value"] == 2500.0 and report["outstanding_value"] == 1500.0
    assert report["value_per_enquiry"] == 100.0
    # Channel rows carry their own previous period, so a dip is visible without maths.
    assert report["by_channel"]["phone"] == {"enquiries": 20, "previous": 10,
                                             "change_percent": 100}
    assert report["by_channel"]["sms"] == {"enquiries": 0, "previous": 0,
                                           "change_percent": None}


def test_an_empty_tenant_produces_zeros_not_an_error():
    report = revenue.build({}, {})
    assert report["enquiries"] == 0 and report["accepted_value"] == 0
    assert report["value_per_enquiry"] == 0 and report["accept_rate_percent"] == 0.0
    assert report["enquiries_change_percent"] is None
    assert all(report["by_channel"][channel]["enquiries"] == 0 for channel in revenue.CHANNELS)


def test_paid_money_is_reported_separately_from_accepted_value():
    report = revenue.build(
        {"enquiries": 2, "quotes_accepted": 2, "accepted_cents": 500000,
         "paid_cents": 100000, "outstanding_cents": 400000, "currency": "NZD"}, {})
    assert report["accepted_value"] == 5000.0
    assert report["paid_value"] == 1000.0
    assert report["outstanding_value"] == 4000.0


# ------------------------------------------------------------------ queries

class FakePool:
    def __init__(self, leads, quotes):
        self.leads = leads
        self.quotes = quotes
        self.fetched = []

    async def fetch(self, sql, *args):
        self.fetched.append((" ".join(sql.split()), args))
        return self.leads

    async def fetchrow(self, sql, *args):
        return self.quotes


def _patch(monkeypatch, pool):
    monkeypatch.setattr(revenue.db, "pool", lambda: pool)


def test_the_report_scopes_every_query_to_the_tenant(monkeypatch):
    pool = FakePool([{"channel": "phone", "n": 3}], {"quotes_sent": 1, "currency": "NZD"})
    _patch(monkeypatch, pool)
    report = asyncio.run(revenue.report("t1", 30))
    assert report["enquiries"] == 3
    assert report["currency"] == "NZD"
    for sql, args in pool.fetched:
        assert "tenant_id = $1" in sql
        assert args[0] == "t1"
    # Current and previous period, each with its own window.
    assert len(pool.fetched) == 2


def test_the_window_is_clamped_so_a_typo_cannot_scan_history(monkeypatch):
    pool = FakePool([], {})
    _patch(monkeypatch, pool)
    assert asyncio.run(revenue.report("t1", 100000))["days"] == 365
    # 0 means "no choice given", so it falls back to the 30-day default rather than a 1-day window.
    assert asyncio.run(revenue.report("t1", 0))["days"] == 30
    assert asyncio.run(revenue.report("t1", -5))["days"] == 1


def test_the_report_says_what_the_number_means(monkeypatch):
    pool = FakePool([], {})
    _patch(monkeypatch, pool)
    report = asyncio.run(revenue.report("t1", 30))
    assert "accepted" in report["note"] and "confirmed money" in report["note"]
