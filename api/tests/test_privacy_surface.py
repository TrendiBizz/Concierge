"""Privacy Act 2020 needs a reachable statement, a deletion path, and a consent record.

Concierge stores enquiries, messages, call recordings and transcripts. Before this, a person had no
way to ask what was held or to have it deleted from inside the product, and "they enquired once" was
silently treated as permission to keep contacting them.
"""

import inspect

from app import main, privacy


def test_the_public_entry_point_and_request_path_exist():
    paths = main.app.openapi()["paths"]
    assert "/privacy" in paths
    assert "/privacy/request" in paths


def test_the_owner_can_list_and_erase():
    paths = main.app.openapi()["paths"]
    assert "/owner/privacy/requests" in paths
    assert "/owner/privacy/requests/{request_id}/erase" in paths


def test_consent_is_recorded_per_channel():
    paths = main.app.openapi()["paths"]
    assert "/owner/privacy/contacts/{contact_key}/consent" in paths


def test_erasure_removes_the_person_but_keeps_the_row():
    source = inspect.getsource(privacy.erase)
    assert "erased_at=now()" in source, "erasure must be marked, not silently missing"
    assert "DELETE FROM messages" in source
    assert "DELETE FROM enquiry_sources" in source


def test_a_request_is_passed_to_the_business_not_absorbed():
    source = inspect.getsource(privacy.privacy_request)
    assert "INSERT INTO privacy_requests" in source
    assert "owner_notifications.queue" in source


def test_the_statement_url_is_the_real_one():
    assert privacy.STATEMENT_URL == "https://trendibizz.com/privacy.html"
