"""A customer who already runs a CRM must be able to leave with their data, and be fed new activity.

Two layers:
  * pure functions (CSV shape, forgiving import header, HMAC signature) -- always run
  * round trips against a real Postgres and a real HTTP endpoint -- skipped without
    TEST_DATABASE_URL, because the behaviour that matters is SQL and HTTP, not mocks
"""
import asyncio
import http.server
import json
import os
import pathlib
import threading
import uuid

import asyncpg
import pytest

from app import casetimeline, db, portability

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()


# ---------------------------------------------------------------- pure
def test_csv_export_has_one_row_per_address():
    csv_text = portability.to_csv([{
        "case_key": "phone:+6421555123", "display_name": "Hana",
        "addresses": ["phone:+6421555123", "email:hana@acme.co.nz"],
        "channels": ["email", "voice"], "last_seen": "2026-11-13T00:00:00+00:00",
    }])
    lines = csv_text.strip().splitlines()
    assert lines[0] == "customer,case_key,kind,address,channels,last_seen"
    assert len(lines) == 3, "both addresses should be exported, not just the primary"
    assert "phone,+6421555123" in lines[1] or "phone,+6421555123" in lines[2]
    assert "email,hana@acme.co.nz" in lines[1] + lines[2]


@pytest.mark.parametrize("header,phone_col,email_col", [
    ("Name,Phone,Email", "021 555 123", "a@b.co"),
    ("name,mobile,e-mail", "021 555 123", "a@b.co"),
    ("Name,Telephone,Mail", "021 555 123", "a@b.co"),
    ("Customer,Phone Number,Email Address", "021 555 123", "a@b.co"),
])
def test_import_accepts_the_headers_other_crms_export(header, phone_col, email_col):
    rows = portability.parse_import(f"{header}\nHana,{phone_col},{email_col}\n")
    assert rows[0]["phone"] == phone_col
    assert rows[0]["email"] == email_col
    assert rows[0]["name"] == "Hana"


def test_import_ignores_a_byte_order_mark():
    rows = portability.parse_import("\ufeffName,Phone,Email\nHana,021555123,a@b.co\n")
    assert rows[0]["name"] == "Hana"


def test_signature_is_hmac_sha256_of_the_body():
    body = b'{"event":"customer.created"}'
    first = portability.signature("s3cret", body)
    assert first.startswith("sha256=")
    assert first == portability.signature("s3cret", body)
    assert first != portability.signature("other", body), "the secret must matter"


def test_unknown_events_are_refused():
    with pytest.raises(ValueError):
        asyncio.run(portability.emit(uuid.uuid4(), "customer.deleted", {}))


# ---------------------------------------------------------------- against a real database
async def _fresh_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "1536"))
    db._pool = pool
    return pool


async def _tenant(pool, slug="acme"):
    return await pool.fetchval(
        "INSERT INTO tenants (slug, name, public_key) VALUES ($1,$2,$3) RETURNING id",
        slug, "Acme", "pk_" + uuid.uuid4().hex[:8])


@needs_db
def test_import_then_export_round_trip_and_is_idempotent():
    async def run():
        pool = await _fresh_pool()
        try:
            t = await _tenant(pool)
            csv_text = ("Name,Phone,Email\n"
                        "Hana,+6491234567,hana@acme.co.nz\n"
                        "Bob,+6499999999,bob@bob.co.nz\n")
            first = await portability.import_contacts(t, portability.parse_import(csv_text), "64")
            assert first["contacts"] == 2 and not first["skipped"]

            # Importing the same file again must update, never duplicate.
            again = await portability.import_contacts(t, portability.parse_import(csv_text), "64")
            assert again["contacts"] == 2
            count = await pool.fetchval("SELECT count(*) FROM customer_cases WHERE tenant_id=$1", t)
            assert count == 2, "the second import created duplicate customers"

            exported = await portability.export_contacts(t)
            assert len(exported) == 2
            hana = next(c for c in exported if c["display_name"] == "Hana")
            assert "email:hana@acme.co.nz" in hana["addresses"]
            assert any(a.startswith("phone:") for a in hana["addresses"])

            csv_out = portability.to_csv(exported)
            assert "hana@acme.co.nz" in csv_out and "bob@bob.co.nz" in csv_out
        finally:
            await pool.close()
            db._pool = None
    asyncio.run(run())


@needs_db
def test_a_bad_row_does_not_abandon_the_rest_of_the_file():
    async def run():
        pool = await _fresh_pool()
        try:
            t = await _tenant(pool)
            rows = [{"name": "Nobody", "phone": "", "email": "", "extra": ""},
                    {"name": "Someone", "phone": "+6491234567", "email": "", "extra": ""}]
            result = await portability.import_contacts(t, rows, "64")
            assert result["contacts"] == 1
            assert len(result["skipped"]) == 1
        finally:
            await pool.close()
            db._pool = None
    asyncio.run(run())


@needs_db
def test_new_customer_is_pushed_to_the_customers_own_crm():
    """The whole point of the push side: their CRM hears about a new enquiry, with a signature."""
    received = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            received.append({
                "event": self.headers.get("X-Concierge-Event"),
                "signature": self.headers.get("X-Concierge-Signature"),
                "raw": body,
                "body": json.loads(body),
            })
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *_args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/hook"

    async def run():
        pool = await _fresh_pool()
        try:
            t = await _tenant(pool)
            # Their endpoint is configured by the business, and the secret is theirs.
            await pool.execute(
                "INSERT INTO tenant_webhooks (tenant_id, url, secret) VALUES ($1,$2,$3)",
                t, url, "topsecret-secret")

            await casetimeline.reconcile(t, phone="+6491234567", name="Hana", default_cc="64")
            for _ in range(30):
                if received:
                    break
                await asyncio.sleep(0.1)
            await portability.deliver_pending(t)

            assert received, "the customer's CRM was never told about the new customer"
            event = received[0]
            assert event["event"] == "customer.created"
            # The body must carry an object, not a stringified one.
            assert isinstance(event["body"]["data"], dict)
            assert event["body"]["data"]["name"] == "Hana"
            # And they can prove it came from us, over the exact bytes we sent.
            assert event["signature"] == portability.signature("topsecret-secret", event["raw"])

            pending = await pool.fetchval(
                "SELECT count(*) FROM webhook_events WHERE tenant_id=$1 AND delivered_at IS NULL", t)
            assert pending == 0, "a delivered event was left queued"
        finally:
            server.shutdown()
            await pool.close()
            db._pool = None
    asyncio.run(run())
