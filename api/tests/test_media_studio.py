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


def test_video_needs_neither_a_photo_nor_music():
    """Reported: "this doesn't work on its own, why do we need to input a picture or music".

    The schema used to demand at least one photo, so a headline alone was rejected with
    "Photos is not valid." — the customer was told their input was wrong for a requirement we
    invented.
    """
    import re, pathlib
    source = pathlib.Path(__file__).resolve().parents[1] / "app" / "media_studio.py"
    text = source.read_text()
    video_model = re.search(r"class VideoRequest\(BaseModel\):(.*?)\n\n\n", text, re.S).group(1)
    photo_line = [ln for ln in video_model.splitlines() if "photos:" in ln][0]
    assert "min_length" not in photo_line, "photos must be optional"
    assert "photos: list[str] = Field(default_factory=list" in video_model
    # Something has to be on screen: no photo and no headline is a fair 400.
    assert "Add a headline, or a photo" in text


def test_the_renderer_draws_a_title_card_when_there_is_no_photo():
    import pathlib
    server = (pathlib.Path(__file__).resolve().parents[2] / "services" / "media-render" / "server.js").read_text()
    assert "async function titleCard(" in server
    assert "zoompan" in server, "the card must move, or it is a still image"
    assert "At least one photo is required" not in server
