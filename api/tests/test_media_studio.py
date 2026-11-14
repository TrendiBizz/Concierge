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


def test_we_do_not_offer_to_make_video_any_more():
    """Operator decision, 2026-11-14: "remove any verbiage allowing the making of ai videos".

    The safest product is one that never claims what our stack cannot do: we take a video the
    customer already made and post it. Guards against the generators creeping back.
    """
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    api = (root / "api" / "app" / "media_studio.py").read_text()
    renderer = (root / "services" / "media-render" / "server.js").read_text()
    page = (root / "web" / "portal" / "src" / "Engage.tsx").read_text()

    for forbidden in ('@router.post("/video"', '@router.post("/ai-video"', "class VideoRequest",
                      "class AiVideoRequest", "/render/video", "/render/ai-video"):
        assert forbidden not in api, f"the API still offers video generation: {forbidden}"
    for forbidden in ("renderVideo", "renderAiVideo", "render/video", "zoompan", "xfade"):
        assert forbidden not in renderer, f"the renderer still makes video: {forbidden}"
    for forbidden in ("Generate AI clip", "Generate AI video", "AAI video", "Making your AI clip"):
        assert forbidden not in page, f"the page still offers to make video: {forbidden}"


def test_a_video_the_customer_made_can_be_uploaded_for_socials():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    api = (root / "api" / "app" / "media_studio.py").read_text()
    page = (root / "web" / "portal" / "src" / "Engage.tsx").read_text()
    assert '@router.post("/upload"' in api
    assert '"video/mp4": "mp4"' in api and '"video/quicktime": "mov"' in api
    assert 'async function uploadVideo' in page
    assert "'/owner/media/upload'" in page
    assert "We do not generate video." in page
