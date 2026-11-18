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


# --- the endpoint must not claim a code was emailed when nothing went out ---------------------------

def _post_code(monkeypatch, accounts, make_code, send_email):
    from fastapi.testclient import TestClient

    from app import main as app_main

    async def allow(*_a, **_k):
        return True

    async def found(_email):
        return accounts

    monkeypatch.setattr(app_main.owner_auth, "allow_login_attempt", allow)
    monkeypatch.setattr(app_main.owner_auth, "account_emails", found)
    monkeypatch.setattr(app_main.owner_auth, "make_code", make_code)
    monkeypatch.setattr(app_main.mailer, "send_email", send_email)
    return TestClient(app_main.app, raise_server_exceptions=False).post(
        "/owner/auth/code", json={"email": "owner@example.com"})


ACCOUNT = {"tenant_id": TENANT, "role": "owner", "slug": "acme", "name": "Acme"}


async def _ok_code(*_a, **_k):
    return "123456"


async def _ok_send(*_a, **_k):
    return None


async def _bad_send(*_a, **_k):
    raise RuntimeError("smtp down for owner@example.com")


async def _bad_code(*_a, **_k):
    raise RuntimeError("db constraint")


def test_unknown_email_still_answers_200(monkeypatch):
    response = _post_code(monkeypatch, [], _ok_code, _ok_send)
    assert response.status_code == 200 and response.json() == {"ok": True}


def test_known_account_and_sent_answers_200(monkeypatch):
    response = _post_code(monkeypatch, [ACCOUNT], _ok_code, _ok_send)
    assert response.status_code == 200 and response.json() == {"ok": True}


@pytest.mark.parametrize("make_code,send_email", [(_ok_code, _bad_send), (_bad_code, _ok_send)])
def test_known_account_where_nothing_went_out_is_an_error(monkeypatch, make_code, send_email):
    response = _post_code(monkeypatch, [ACCOUNT], make_code, send_email)
    assert response.status_code == 503
    text = response.text
    assert "could not be sent" in text
    assert "owner@example.com" not in text and "acme" not in text and "smtp" not in text


def test_one_sibling_failing_does_not_fail_the_request(monkeypatch):
    calls = {"n": 0}

    async def flaky(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first failed")

    second = dict(ACCOUNT, slug="beta")
    response = _post_code(monkeypatch, [ACCOUNT, second], _ok_code, flaky)
    assert response.status_code == 200


DSN = __import__("os").environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
def test_schema_accepts_a_code_row_and_is_idempotent():
    import pathlib

    import asyncpg

    schema = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()

    async def run():
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute(schema.replace("__DIM__", "1536"))
            await conn.execute(schema.replace("__DIM__", "1536"))  # restart re-applies it
            tenant = await conn.fetchval(
                "INSERT INTO tenants (slug,name,public_key) VALUES ('c','C','pk_c') RETURNING id")
            await conn.execute(
                "INSERT INTO tenant_invites(tenant_id,email,role,purpose,token_hash,expires_at) "
                "VALUES($1,'a@b.c','owner','code','h',now()+interval '10 minutes')", tenant)
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "INSERT INTO tenant_invites(tenant_id,email,role,purpose,token_hash,expires_at) "
                    "VALUES($1,'a@b.c','owner','bogus','h2',now()+interval '10 minutes')", tenant)
        finally:
            await conn.close()

    asyncio.run(run())
