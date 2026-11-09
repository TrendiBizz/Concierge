from pydantic import ValidationError
import pytest
from app.owner_onboarding import OwnerBusinessProfile
from app.tenants import CLONE_FIELDS, UPDATABLE_FIELDS


def test_owner_phone_requires_explicit_international_destination():
    assert OwnerBusinessProfile(notify_phone="+64211234567").notify_phone == "+64211234567"
    assert OwnerBusinessProfile(notify_phone="").notify_phone == ""
    for value in ("0211234567", "+012345678", "+6421\n123456", "+64abc123456"):
        with pytest.raises(ValidationError):
            OwnerBusinessProfile(notify_phone=value)


def test_owner_destination_is_saved_but_never_cloned_to_another_business():
    assert "notify_phone" in UPDATABLE_FIELDS
    assert "notify_phone" not in CLONE_FIELDS
