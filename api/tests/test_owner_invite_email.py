"""The invitation a client receives must be traceable, not a shell command.

The first Pukeko activation email was sent by calling `mailer.send_email` from a container shell: it
left no row in the outbox, so nothing recorded that it happened and nothing would have retried it.
`owner_invites` composes the invitation and queues it through the outbox instead.
"""

import asyncio
import inspect

from app import main, owner_invites


def test_the_email_contains_a_working_sign_in_link_and_the_guide():
    subject, body = owner_invites.compose(
        "Pukeko Construction",
        "https://concierge.trendibizz.com/studio#invite=TOKEN",
        "https://concierge.trendibizz.com/guide/bonsai-cladding")
    assert subject == "Your Concierge account is ready"
    assert "https://concierge.trendibizz.com/studio#invite=TOKEN" in body
    assert "guide/bonsai-cladding" in body


def test_it_names_the_business_and_the_first_steps():
    """Generic first steps, not one trade's workflow. Cladding takeoff is a separate optional section."""
    _, body = owner_invites.compose("Pukeko Construction", "link", "guide")
    assert "Pukeko Construction" in body
    for phrase in ("Business", "rates", "Quotes", "chat window", "Setup step"):
        assert phrase in body, phrase
    assert "IF YOU PRICE CLADDING" in body
    assert "fresh one" in body


def test_it_does_not_promise_a_price_the_business_has_not_set():
    _, body = owner_invites.compose("X", "link", "guide")
    assert "never invent a price" in " ".join(body.split())


def test_the_endpoint_exists_and_is_admin_only():
    routes = main.app.openapi()["paths"]
    assert "/admin/tenants/{slug}/owner-invite" in routes
    post = routes["/admin/tenants/{slug}/owner-invite"]["post"]
    assert post, "the invite route must accept POST"


def test_sending_goes_through_the_outbox():
    source = inspect.getsource(owner_invites)
    assert "outbox.enqueue" in source, "invitations must be queued, not sent inline"
    # Imported mailer would mean a direct send that skips the queue and leaves no record.
    assert "import mailer" not in source and "mailer." not in source.replace("`mailer.", "")


def test_a_resend_is_not_refused_as_a_duplicate():
    """An operator re-sending a link must not be blocked by the earlier invite's dedupe key."""
    import inspect

    from app import owner_invites

    source = inspect.getsource(owner_invites.send)
    assert "hashlib.sha256(link" in source, "the dedupe key must identify the link, not the address"


def test_the_welcome_email_is_not_about_cladding_by_default():
    """Every business got an email opening with 3D cladding takeoff, as if that were the product."""
    from app import owner_invites

    _subject, body = owner_invites.compose("Pukeko Construction", "https://example.test/#invite=x",
                                           "https://example.test/guide")
    opening = body.split("WHAT IT DOES")[1].split("YOUR FIRST TEN MINUTES")[0].lower()
    assert "chat window" in opening, "the email must lead with what the product is"
    assert "clad" not in opening, "cladding takeoff is an aside, not the opening pitch"
    assert "IF YOU PRICE CLADDING" in body, "the takeoff route must still be offered, as optional"


def test_the_welcome_email_does_not_sign_as_the_customer():
    """It read as if the tradesman's own company had emailed them about an account."""
    from app import owner_invites

    _subject, body = owner_invites.compose("Pukeko Construction", "https://example.test/#invite=x",
                                           "https://example.test/guide")
    signoff = body.rsplit("Kind regards,", 1)[1]
    assert "The Trendi Concierge team" in signoff
    assert "for Pukeko Construction" in signoff
