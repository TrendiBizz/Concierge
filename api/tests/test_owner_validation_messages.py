"""Owner portal validation errors read as sentences (the first invite showed "[object Object]")."""
import asyncio
import json
from types import SimpleNamespace

from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


def test_a_short_password_gets_a_readable_message_and_is_never_echoed():
    secret = "pw-Zq9!"
    response = client.post("/owner/auth/redeem", json={"token": "x" * 30, "password": secret})
    assert response.status_code == 422
    assert response.json() == {"detail": "Password must be at least 12 characters."}
    assert secret not in response.text


def test_a_broken_invitation_link_says_so():
    response = client.post("/owner/auth/redeem", json={"token": "abc", "password": "long-enough-password"})
    assert response.status_code == 422
    assert response.json()["detail"] == "The invitation link looks incomplete. Open it again from your email."


def test_a_missing_field_is_named():
    response = client.post("/owner/auth/redeem", json={"token": "x" * 30})
    assert response.status_code == 422
    assert response.json()["detail"] == "Password is required."


def test_the_message_is_always_a_string():
    response = client.post("/owner/auth/redeem", json={})
    assert isinstance(response.json()["detail"], str)


def _error(kind="missing", loc=("body", "name"), **ctx):
    return {"type": kind, "loc": loc, "msg": "Field required", "input": {"secret": "do-not-echo"}, "ctx": ctx}


def test_other_paths_keep_the_standard_list_format():
    exc = RequestValidationError([_error()])
    response = asyncio.run(main.owner_validation_errors(SimpleNamespace(url=SimpleNamespace(path="/api/v1/chat")), exc))
    body = json.loads(response.body)
    assert response.status_code == 422 and isinstance(body["detail"], list)


def test_owner_paths_get_a_sentence_from_the_handler():
    exc = RequestValidationError([_error("string_too_short", ("body", "password"), min_length=12)])
    response = asyncio.run(main.owner_validation_errors(SimpleNamespace(url=SimpleNamespace(path="/owner/auth/redeem")), exc))
    assert json.loads(response.body) == {"detail": "Password must be at least 12 characters."}
    assert response.headers["cache-control"] == "no-store"


def test_several_problems_are_joined_without_repeats():
    errors = [_error("missing", ("body", "email")), _error("missing", ("body", "email")),
              _error("string_too_long", ("body", "slug"), max_length=80)]
    assert main.plain_validation_message(errors) == "Email address is required. Business ID must be at most 80 characters."
