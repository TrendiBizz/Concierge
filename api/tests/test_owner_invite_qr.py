"""An invitation has to be usable from the phone that scans it, not just the laptop that made it.

The token is a long URL. The owner page and Studio both turn it into a locally drawn QR code, so a
new team member can open it on a phone and install the workspace there. These tests pin the wiring:
the page loads the encoder, the invitation result draws the same link, and the asset is reachable
under the only prefix the public proxy forwards.
"""

import pathlib

from app import main

STATIC = pathlib.Path(main.__file__).resolve().parent.parent / "static"


def test_the_invitation_result_draws_a_qr_code_for_the_same_link():
    html = (STATIC / "owner.html").read_text()
    start = html.index('$("invite-form").addEventListener')
    block = html[start:html.index('function mediaData', start)]
    assert "inviteQrSvg(result.invitation_url)" in block
    assert "scan this with a phone camera" in block
    assert 'download="concierge-invitation-qr.svg"' in block


def test_the_qr_encoder_is_served_under_the_proxied_prefix():
    from fastapi.testclient import TestClient

    paths = {getattr(route, "path", "") for route in main.app.routes}
    assert "/owner/qrcode.js" in paths
    source = (STATIC / "qrcode.js").read_text()
    assert "QR Code Generator for JavaScript" in source
    assert "createSvgTag" in source
    response = TestClient(main.app).get("/owner/qrcode.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert "createSvgTag" in response.text


def test_the_page_loads_the_encoder_before_the_inline_script_that_uses_it():
    html = (STATIC / "owner.html").read_text()
    assert html.index('src="/owner/qrcode.js') < html.index("function inviteQrSvg")
    assert html.index('src="/owner/qrcode.js') < html.index('$("invite-form").addEventListener')
