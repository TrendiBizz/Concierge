"""Owners can type their number the normal way; it is stored in international form using THEIR country."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app import main, owner_onboarding as ob


def _profile(**kw):
    return ob.OwnerBusinessProfile(**kw)


@pytest.mark.parametrize("typed", ["0278817368", "027 881 7368", "+64 27 881 7368", "(027) 881-7368", "027.881.7368"])
def test_the_usual_ways_of_writing_a_number_are_accepted(typed):
    assert _profile(notify_phone=typed).notify_phone == typed.strip()


@pytest.mark.parametrize("typed", ["abc", "12", "+64abc", "027 881 73x8", "ring me"])
def test_things_that_are_not_numbers_are_refused_with_an_example(typed):
    with pytest.raises(ValidationError) as caught:
        _profile(notify_phone=typed)
    assert "for example 027 123 4567" in str(caught.value)


def test_country_comes_from_the_business_not_the_global_default(monkeypatch):
    monkeypatch.setattr("app.config.get_settings", lambda: SimpleNamespace(default_country_code="1"))
    assert ob.country_code_for({"default_country_code": "61"}) == "61"
    assert ob.country_code_for({"timezone": "Pacific/Auckland"}) == "64"
    assert ob.country_code_for({"timezone": "Australia/Sydney"}) == "61"
    assert ob.country_code_for({"timezone": "America/Chicago"}) == "1"
    assert ob.country_code_for(None) == "1"


def _save(monkeypatch, current, **profile):
    saved = {}

    async def fake_update(slug, changed):
        saved.update(changed)
        return {"name": "Trendi Support", **changed}

    monkeypatch.setattr(ob.tenants, "get_by_slug", AsyncMock(return_value=current))
    monkeypatch.setattr(ob.tenants, "update", fake_update)
    asyncio.run(ob.update_profile("trendi-support", _profile(**profile)))
    return saved


@pytest.mark.parametrize("typed", ["0278817368", "027 881 7368", "+64 27 881 7368", "64278817368", "(027) 881-7368"])
def test_a_new_zealand_business_gets_the_international_form(monkeypatch, typed):
    saved = _save(monkeypatch, {"timezone": "Pacific/Auckland"}, notify_phone=typed)
    assert saved["notify_phone"] == "+64278817368"


def test_the_timezone_in_the_same_request_is_used(monkeypatch):
    saved = _save(monkeypatch, {"timezone": "America/Chicago"}, notify_phone="0278817368", timezone="Pacific/Auckland")
    assert saved["notify_phone"] == "+64278817368"


def test_a_number_that_cannot_be_dialled_is_refused_not_guessed(monkeypatch):
    monkeypatch.setattr(ob.tenants, "get_by_slug", AsyncMock(return_value={"timezone": "Pacific/Auckland"}))
    monkeypatch.setattr(ob.tenants, "update", AsyncMock())
    with pytest.raises(ValueError) as caught:
        asyncio.run(ob.update_profile("trendi-support", _profile(notify_phone="0123456")))
    assert "does not look right" in str(caught.value) and "027 123 4567" in str(caught.value)
    ob.tenants.update.assert_not_called()


def test_other_fields_are_untouched_when_no_phone_is_sent(monkeypatch):
    monkeypatch.setattr(ob.tenants, "get_by_slug", AsyncMock(side_effect=AssertionError("must not look up")))
    saved = {}

    async def fake_update(slug, changed):
        saved.update(changed)
        return {"name": "Trendi Support", **changed}

    monkeypatch.setattr(ob.tenants, "update", fake_update)
    asyncio.run(ob.update_profile("trendi-support", _profile(name="Trendi Support")))
    assert saved == {"name": "Trendi Support"}


def test_validator_messages_written_for_people_are_kept_by_the_error_formatter():
    errors = [{"type": "value_error", "loc": ("body", "notify_phone"),
               "msg": "Value error, Enter your mobile number, for example 027 123 4567.", "input": "ring me", "ctx": {}}]
    text = main.plain_validation_message(errors)
    assert text == "Enter your mobile number, for example 027 123 4567."
    assert "ring me" not in text


def test_a_message_without_a_full_stop_gets_one():
    errors = [{"type": "value_error", "loc": ("body", "site_url"),
               "msg": "Value error, Enter a public HTTPS website address", "input": "x", "ctx": {}}]
    assert main.plain_validation_message(errors) == "Enter a public HTTPS website address."
