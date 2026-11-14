"""Owner SMS inbox: pure rules plus the routes being wired and owner-authenticated."""
from app import sms_inbox


def test_phone_comes_from_the_sms_session_key():
    assert sms_inbox.phone_of("sms64215550123") == "+64215550123"
    assert sms_inbox.phone_of("sms123") == ""


def test_owner_replies_are_marked_apart_from_the_assistant():
    assert sms_inbox.author_of("user", None) == "customer"
    assert sms_inbox.author_of("assistant", None) == "ai"
    assert sms_inbox.author_of("assistant", "owner") == "owner"


def test_routes_exist_and_refuse_without_an_owner_session():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    cid = "00000000-0000-0000-0000-000000000000"
    for method, path in (("get", "/owner/sms/inbox"), ("get", "/owner/sms/conversations/" + cid),
                         ("post", "/owner/sms/conversations/" + cid + "/takeover"),
                         ("post", "/owner/sms/conversations/" + cid + "/reply")):
        response = getattr(client, method)(path)
        assert response.status_code == 401, (path, response.status_code)
