from pydantic import ValidationError
import pytest
from app.owner_onboarding import OwnerBusinessProfile
from app.tenants import CLONE_FIELDS, UPDATABLE_FIELDS


def test_owner_phone_requires_explicit_international_destination():
    assert OwnerBusinessProfile(notify_phone="+64211234567").notify_phone == "+64211234567"
    assert OwnerBusinessProfile(notify_phone="").notify_phone == ""
    # A number written the local way is accepted here and converted to international form, using the business's
    # own country, when the profile is saved (see test_owner_phone_input.py). Anything that could be dialled
    # wrongly or smuggle in other characters is still refused.
    assert OwnerBusinessProfile(notify_phone="0211234567").notify_phone == "0211234567"
    for value in ("+012345678", "+6421\n123456", "+64abc123456"):
        with pytest.raises(ValidationError):
            OwnerBusinessProfile(notify_phone=value)


def test_owner_destination_is_saved_but_never_cloned_to_another_business():
    assert "notify_phone" in UPDATABLE_FIELDS
    assert "notify_phone" not in CLONE_FIELDS
