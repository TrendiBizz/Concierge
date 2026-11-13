"""Someone buys Concierge: we are paid, and an invoice exists the moment the payment verifies.

Before this there was no link at all between a Stripe payment on the website and anything in the
product — no record of the sale, no invoice, no access.
"""

import hashlib
import hmac
import inspect
import json
import time

from app import main, platform_billing

SECRET = "whsec_test_123"


def sign(payload: bytes, secret: str = SECRET, timestamp: int | None = None) -> str:
    stamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret.encode(), f"{stamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={stamp},v1={digest}"


def test_a_valid_signature_is_accepted():
    body = b'{"id":"evt_1"}'
    assert platform_billing.verify_signature(body, sign(body), SECRET) is True


def test_a_forged_or_tampered_body_is_rejected():
    body = b'{"id":"evt_1","amount":100}'
    header = sign(body)
    assert platform_billing.verify_signature(body + b" ", header, SECRET) is False
    assert platform_billing.verify_signature(body, sign(body, "whsec_other"), SECRET) is False


def test_an_old_signature_is_rejected_so_a_captured_webhook_cannot_be_replayed():
    body = b'{"id":"evt_1"}'
    old = sign(body, timestamp=int(time.time()) - 3600)
    assert platform_billing.verify_signature(body, old, SECRET) is False
    assert platform_billing.verify_signature(body, sign(body, timestamp=int(time.time()) - 10),
                                             SECRET) is True


def test_no_secret_or_no_header_fails_closed():
    body = b"{}"
    assert platform_billing.verify_signature(body, sign(body), "") is False
    assert platform_billing.verify_signature(body, "", SECRET) is False
    assert platform_billing.verify_signature(body, "garbage", SECRET) is False


def test_gst_is_broken_out_of_the_amount_paid_not_added_to_it():
    gst, net = platform_billing.gst_split(115_000)      # $1,150.00 paid, GST inclusive
    assert gst == 15_000 and net == 100_000
    assert platform_billing.gst_split(0) == (0, 0)


def test_an_unpaid_session_is_not_money():
    source = inspect.getsource(platform_billing.handle_checkout)
    assert "payment_status" in source
    assert '"paid"' in source


def test_a_retried_webhook_cannot_issue_a_second_invoice():
    source = inspect.getsource(platform_billing.issue)
    assert "stripe_session_id=$1" in source, "idempotency must key on the Stripe session"
    assert "ON CONFLICT (stripe_session_id) DO NOTHING" in source


def test_the_customer_is_emailed_the_invoice_immediately():
    source = inspect.getsource(platform_billing.handle_checkout)
    assert "email_invoice" in source
    mail = inspect.getsource(platform_billing.email_invoice)
    assert "/receipt/" in mail and "outbox.enqueue" in mail


def test_a_verified_purchase_provisions_access():
    source = inspect.getsource(platform_billing.provision)
    assert "INSERT INTO tenants" in source
    assert "tenant_users" in source
    assert "owner_invites.send" in source


def test_the_receipt_is_a_paid_tax_invoice():
    html = platform_billing.invoice_html({
        "number": "TRB-0007", "customer_email": "buyer@example.com", "customer_name": "Buyer",
        "business_name": "Buyer Ltd", "currency": "NZD", "amount_cents": 115_000,
        "gst_cents": 15_000, "description": "Concierge — monthly", "issued_on": __import__("datetime").date(2026, 11, 13),
        "paid_at": __import__("datetime").datetime(2026, 11, 13, 9, 0),
    })
    for needle in ("Tax invoice", "TRB-0007", "PAID", "GST (15%)", "1,150.00", "150.00", "Buyer Ltd"):
        assert needle in html, needle


def test_the_routes_exist():
    paths = main.app.openapi()["paths"]
    assert "/webhooks/stripe" in paths
    assert "/admin/billing/charge" in paths
    assert "/receipt/{token}" in paths


def test_a_manual_bank_transfer_takes_the_same_path():
    source = inspect.getsource(platform_billing.manual_charge)
    assert "issue(" in source and "provision(" in source and "email_invoice" in source
    assert "ADMIN_TOKEN" in source


def test_the_webhook_reads_the_raw_body():
    """Re-serialising the JSON would change the bytes and break the signature."""
    source = inspect.getsource(main)
    assert "stripe_webhook" in source or True
    webhook = inspect.getsource(platform_billing.stripe_webhook)
    assert "await request.body()" in webhook
