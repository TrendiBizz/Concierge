import pytest
from fastapi import HTTPException

from app import voice_internal
from app.config import get_settings


def test_internal_token_gate():
    settings = get_settings()
    previous = settings.internal_token
    try:
        settings.internal_token = ""
        with pytest.raises(HTTPException) as disabled:
            voice_internal._authorize("anything")
        assert disabled.value.status_code == 503

        settings.internal_token = "secret"
        for token in (None, "", "wrong"):
            with pytest.raises(HTTPException) as denied:
                voice_internal._authorize(token)
            assert denied.value.status_code == 401
        voice_internal._authorize("secret")
    finally:
        settings.internal_token = previous
