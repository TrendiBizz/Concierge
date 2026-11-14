"""A configured business must not be greeted with its own setup wizard again.

ACME Ltd was already running — website, notifications, channels — and Studio still opened on
"1. Welcome / How Concierge works", which reads as "your setup did not save". The Permissions page
had the same problem in reverse: it explained the inbound email delivery chain to an owner who
has no way to act on it, so it is now a disclosure that opens itself only when a step is failing.
"""
from pathlib import Path

PORTAL = Path(__file__).resolve().parents[2] / "web" / "portal" / "src"


def test_setup_detects_an_already_configured_business():
    source = (PORTAL / "App.tsx").read_text()
    assert "const alreadySetUp = Boolean(business.name.trim() && business.site_url.trim());" in source
    # the welcome step is the thing that must not appear; editing must stay reachable
    assert "{step === 1 && !alreadySetUp ? (" in source
    assert "is set up</Heading>" in source
    assert 'label="Edit business details"' in source


def test_permissions_keep_the_delivery_chain_behind_a_disclosure():
    source = (PORTAL / "Permissions.tsx").read_text()
    assert "const inboundFailing = Object.keys(CHECK_LABELS)" in source
    assert "<details" in source and "Show the delivery-chain checks" in source
    # owners see the count, not the list
    assert "step(s) of the delivery chain are not working" in source


def test_an_edge_error_never_reaches_the_owner_verbatim():
    """The banner in the screenshot was Cloudflare's own words, printed at the owner."""
    source = (PORTAL / "api.ts").read_text()
    assert "const trusted = detail && status < 500" in source
    assert "!detail.includes('<')" in source
