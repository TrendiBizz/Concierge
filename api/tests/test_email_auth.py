import asyncio

from app import email_auth


def test_merge_prefers_verified_verdict():
    merged = email_auth.merge({"dmarc": "fail", "spf": "pass"},
                              {"dkim": "pass", "dmarc": "pass", "from": "a@example.com"})
    assert merged["dkim"] == "pass"
    assert merged["dmarc"] == "pass"
    assert merged["spf"] == "pass"
    assert merged["verified_from"] == "a@example.com"
    assert merged["verified_by"] == "email-auth"


def test_verify_disabled_without_url():
    settings = email_auth.get_settings()
    previous = settings.email_auth_url
    settings.email_auth_url = ""
    try:
        assert asyncio.run(email_auth.verify("abc")) is None
    finally:
        settings.email_auth_url = previous
