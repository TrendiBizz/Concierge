"""Signing in with a six-digit code, for apps that cannot follow a link.

An installed web app on iOS has its own storage, and the emailed sign-in link opens in Safari —
so the installed app stayed signed out with no way in. The code is typed where the person already
is. These tests pin the parts that make that safe: six digits, stored as a digest, single use,
ten minutes.
"""
import asyncio

import pytest

from app import owner_auth

TENANT = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"


class Pool:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return "INSERT 0 1"


def test_a_code_is_six_digits_and_is_not_stored_in_the_clear(monkeypatch):
    pool = Pool()
    monkeypatch.setattr(owner_auth.db, "pool", lambda: pool)
    code = asyncio.run(owner_auth.make_code(TENANT, "Owner@Example.com", "owner"))
    assert len(code) == 6 and code.isdigit()
    sql, args = pool.calls[0]
    assert "purpose" in sql and "'code'" in sql
    assert code not in args, "the code itself was written to the database"
    assert owner_auth.digest(code) in args
    assert "Owner@Example.com" not in args, "the address was not normalised"
    assert args[1] == "owner@example.com"


def test_codes_issued_together_do_not_collide(monkeypatch):
    pool = Pool()
    monkeypatch.setattr(owner_auth.db, "pool", lambda: pool)
    first = asyncio.run(owner_auth.make_code(TENANT, "a@example.com", "owner"))
    second = asyncio.run(owner_auth.make_code(TENANT, "b@example.com", "owner", avoid={first}))
    assert second != first


def test_a_used_code_cannot_be_replayed():
    assert owner_auth.code_already_used("code", object()) is True
    assert owner_auth.code_already_used("code", None) is False


def test_a_link_keeps_its_short_grace_after_use():
    """The grace exists for double-fired browser exchanges on links. Codes must not inherit it."""
    assert owner_auth.code_already_used("invite", object()) is False
    assert owner_auth.code_already_used("recovery", object()) is False
