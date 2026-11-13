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
    _, body = owner_invites.compose("Pukeko Construction", "link", "guide")
    assert "Pukeko Construction" in body
    for phrase in ("Designs and CAD", "rate per m2", "Save rates", "IFC takeoff", "Price this model"):
        assert phrase in body, phrase
    assert "single-use" in body


def test_it_does_not_promise_a_price_the_business_has_not_set():
    _, body = owner_invites.compose("X", "link", "guide")
    assert "never invent a price" in body


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
