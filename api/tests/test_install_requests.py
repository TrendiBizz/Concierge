"""A customer must be able to get the chat onto their site without touching code.

The Setup step used to end with a `<script>` tag and "send this to your web person". For most
tradespeople that is where installation stops: they have never edited their site, and many have
nobody to send it to.
"""

import inspect

from app import install_requests, main


def test_the_request_records_what_the_operator_needs():
    source = inspect.getsource(install_requests.create)
    assert "INSERT INTO install_requests" in source
    for field in ("website", "platform", "contact_name", "contact_phone"):
        assert field in source


def test_the_operator_is_emailed_the_request():
    source = inspect.getsource(install_requests._tell_the_operator)
    assert "owner_alert" in source
    assert "trendi-support" in source, "the alert must go to the operator, not the customer"


def test_the_customer_can_file_it_and_read_it_back():
    paths = main.app.openapi()["paths"]
    assert "/owner/install-request" in paths
    assert "/owner/install-requests" in paths
    assert "/admin/install-requests" in paths


def test_filing_a_request_requires_the_owner_not_a_stranger():
    """OpenAPI does not describe the header-based owner session, so inspect the handler."""
    source = inspect.getsource(main.owner_install_request)
    assert "owner_auth.current_user" in source, "an anonymous caller must not queue work"
    assert "Depends(" in source


def test_an_unknown_platform_is_stored_as_unsure():
    assert "unsure" in install_requests.PLATFORMS
    source = inspect.getsource(install_requests.create)
    assert 'if platform in PLATFORMS else "unsure"' in source


def test_the_setup_step_does_not_tell_the_customer_to_find_a_web_person():
    page = (__import__("pathlib").Path(__file__).resolve().parents[2]
            / "web" / "portal" / "src" / "App.tsx").read_text()
    for phrase in ("send it to whoever does", "Email this to my web person",
                   "Send this line to whoever looks after your website"):
        assert phrase not in page, f"still asking the customer to find help: {phrase!r}"
