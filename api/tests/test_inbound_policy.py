import pytest

from app import inbound_policy


def test_normalize_accepts_address_and_domain():
    assert inbound_policy.normalize("  Bob@Example.com ") == "bob@example.com"
    assert inbound_policy.normalize("@Example.com") == "@example.com"


def test_normalize_rejects_other_shapes():
    with pytest.raises(ValueError):
        inbound_policy.normalize("example.com")
    with pytest.raises(ValueError):
        inbound_policy.normalize("bob@")
    with pytest.raises(ValueError):
        inbound_policy.normalize("")


def test_matches_exact_and_domain():
    assert inbound_policy.matches("bob@example.com", "Bob@Example.com")
    assert not inbound_policy.matches("bob@example.com", "eve@example.com")
    assert inbound_policy.matches("@example.com", "anyone@example.com")
    assert not inbound_policy.matches("@example.com", "anyone@other.test")


def test_defang_makes_links_inert():
    text = "see https://evil.test/a and http://x.test/b"
    out = inbound_policy.defang(text)
    assert "https://" not in out and "http://" not in out
    assert "hxxps://evil.test/a" in out and "hxxp://x.test/b" in out
