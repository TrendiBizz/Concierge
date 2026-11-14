"""The media page uploads; it does not generate.

Operator decision, 2026-11-14: remove the generators entirely, including the "branded image"
templates and AI images, and keep an upload. The brand kit stays in Setup because invoices,
quotes and the chat widget read it — see the last test here.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = (ROOT / "api" / "app" / "media_studio.py").read_text()
PAGE = (ROOT / "web" / "portal" / "src" / "Engage.tsx").read_text()


def test_the_media_api_only_uploads_and_files():
    routes = __import__("re").findall(r'@router\.(get|post|put|delete)\("([^"]+)"', API)
    paths = {path for _, path in routes}
    assert paths == {"/brand", "/upload", "/usage", "/assets", "/assets/{asset_id}/to-social",
                     "/assets/{asset_id}/file", "/assets/delete", "/assets/{asset_id}"}, paths


def test_no_image_or_video_generation_is_offered_anywhere():
    for forbidden in ('"/image"', '"/video"', '"/ai-image"', '"/ai-video"', '"/templates"',
                      "ImageRequest", "VideoRequest", "AiRequest", "AiVideoRequest",
                      "media_render_url", "_render("):
        assert forbidden not in API, f"the API still generates media: {forbidden}"
    for forbidden in ("Branded image", "AI image", "Generate image", "Showcase —", "before_after",
                      "Generate AI", "/render/"):
        assert forbidden not in PAGE, f"the page still generates media: {forbidden}"
    assert not (ROOT / "services" / "media-render").exists(), "the renderer service should be gone"
    compose = (ROOT / "scripts" / "vps" / "compose.yml").read_text()
    assert "media-render:\n" not in compose, "compose should not start the renderer"
    assert "context: ../../services/media-render" not in compose


def test_the_page_uploads_the_customers_own_media():
    assert "Upload your media" in PAGE
    assert "We do not make images or video for you" in PAGE or "We do not generate" in PAGE
    assert "'/owner/media/upload'" in PAGE
    assert 'accept="image/*,video/*"' in PAGE


def test_upload_accepts_the_types_we_promise_and_nothing_else():
    assert '"video/mp4": "mp4"' in API and '"video/quicktime": "mov"' in API
    assert '"video/webm": "webm"' in API
    assert '"image/jpeg": "jpg"' in API and '"image/png": "png"' in API and '"image/webp": "webp"' in API
    assert "That file type is not supported" in API
    assert "UPLOAD_LIMIT = 200_000_000" in API


def test_the_brand_kit_survives_because_real_features_depend_on_it():
    """A cleanup that deleted media_brand would break invoices, quotes and the chat widget."""
    invoices = (ROOT / "api" / "app" / "invoices.py").read_text()
    quotations = (ROOT / "api" / "app" / "quotations.py").read_text()
    assert "media_brand" in invoices, "invoices print the brand name, accent and logo"
    assert "media_brand" in quotations, "quotes print the brand name, accent and logo"
    assert '@router.get("/brand")' in API and '@router.put("/brand")' in API
    setup = (ROOT / "web" / "portal" / "src" / "App.tsx").read_text()
    assert "/owner/media/brand" in setup, "Setup is where the brand kit is edited now"


def test_media_deletes_are_audit_logged():
    """Assets disappeared once and the container logs could not say who removed them.

    Every delete path must record tenant, caller and what went, so a disappearance is answerable.
    """
    assert 'log.info("media bulk delete tenant=%s by=%s count=%s ids=%s"' in API
    assert 'log.info("media delete tenant=%s by=%s id=%s path=%s"' in API
