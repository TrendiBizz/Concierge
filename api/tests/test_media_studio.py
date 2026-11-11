import pytest
from fastapi import HTTPException

from app import media_studio


def test_photos_require_image_data_uris():
    with pytest.raises(HTTPException):
        media_studio._photos(["https://example.com/photo.jpg"])
    with pytest.raises(HTTPException):
        media_studio._photos(["data:text/plain;base64,aGk="])


def test_brand_payload_defaults():
    payload = media_studio._brand_payload({})
    assert payload == {"name": "", "accent": "#c8f560", "contact": "", "logo": ""}
    payload = media_studio._brand_payload({"name": "Pukeko", "accent": "#c8f560", "contact": "pukeko.nz", "logo_data": "data:image/png;base64,AA"})
    assert payload["logo"].startswith("data:image/png")


def test_templates_are_available():
    ids = {t["id"] for t in media_studio.TEMPLATES}
    assert {"showcase", "before_after", "quote", "service"} <= ids
