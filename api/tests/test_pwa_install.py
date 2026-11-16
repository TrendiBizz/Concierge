"""A QR code that installs Concierge — the manifest, the install page, and the QR's target.

Measured live 2026-11-16: the Studio had a manifest and a service worker, but the shell never
linked the manifest. Chrome therefore never met the install criteria, the captured
`beforeinstallprompt` never fired, and the only QR in the setup flow encoded the hosted chat page
(`chat.trendibizz.com/demo/…`). Scanning it opened a chat window and installed nothing.

These checks pin the whole chain: the shell advertises the manifest, the manifest is installable,
the icons are the size they claim, the install page is reachable without signing in, and the QR
points at that page rather than at the chat widget.
"""

import json
import pathlib
import struct

from app import main

PORTAL = pathlib.Path(__file__).resolve().parents[2] / "web" / "portal"
SRC = PORTAL / "src"
PUBLIC = PORTAL / "public"


def png_size(path: pathlib.Path) -> tuple[int, int]:
    """Read a PNG's width and height from its IHDR — no image library, no trust in the filename."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


# ------------------------------------------------------------------ the shell advertises the app

def test_the_shell_links_the_manifest_without_which_nothing_is_installable():
    html = (PORTAL / "index.html").read_text()
    assert 'rel="manifest"' in html, "Chrome will not offer Install without a linked manifest"
    assert "/studio/manifest.webmanifest" in html
    assert "/studio/apple-touch-icon.png" in html, "iOS uses the touch icon for the home screen"
    assert 'name="theme-color"' in html
    assert 'name="apple-mobile-web-app-title"' in html
    assert "<title>Concierge</title>" in html, "the shell still says 'portal'"
    assert "<title>portal</title>" not in html


def test_the_manifest_meets_the_install_criteria():
    manifest = json.loads((PUBLIC / "manifest.webmanifest").read_text())
    assert manifest["name"] and manifest["short_name"]
    assert manifest["start_url"] == "/studio/"
    assert manifest["scope"] == "/studio/"
    assert manifest["display"] == "standalone"
    assert manifest["id"] == "/studio/"
    assert manifest["prefer_related_applications"] is False
    purposes = {(icon["sizes"], icon.get("purpose")) for icon in manifest["icons"]}
    assert ("192x192", "any") in purposes
    assert ("512x512", "any") in purposes
    assert ("512x512", "maskable") in purposes


def test_the_declared_icons_exist_at_the_size_they_claim():
    manifest = json.loads((PUBLIC / "manifest.webmanifest").read_text())
    for icon in manifest["icons"]:
        name = icon["src"].rsplit("/", 1)[-1]
        path = PUBLIC / name
        assert path.is_file(), f"{name} is declared but missing"
        declared = icon["sizes"].split("x")
        assert png_size(path) == (int(declared[0]), int(declared[1])), f"{name} is not {icon['sizes']}"
    apple = PUBLIC / "apple-touch-icon.png"
    assert apple.is_file() and png_size(apple) == (180, 180)


# ------------------------------------------------------------------ the install page is public

def test_the_install_page_is_reachable_without_signing_in():
    source = (SRC / "App.tsx").read_text()
    branch = "location.pathname.replace(/\\/+$/, '') === '/studio/install'"
    assert branch in source, "nothing routes /studio/install to the install page"
    # The branch has to come before the shell's signed-out return, or the page asks for a login.
    signed_out = source.index("if (!token) {\n    return (\n      <Theme theme={theme}>")
    assert source.index(branch) < signed_out
    assert "<InstallApp />" in source


def test_the_server_falls_back_to_the_shell_for_the_install_path(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<!doctype html><title>Concierge</title>")
    monkeypatch.setattr(main, "STUDIO_DIR", tmp_path)
    response = __import__("asyncio").run(main.studio_file("install"))
    assert str(response.path).endswith("index.html")


def test_the_install_prompt_is_captured_before_react_mounts():
    main_tsx = (SRC / "main.tsx").read_text()
    assert "initInstallCapture()" in main_tsx
    assert main_tsx.index("initInstallCapture()") < main_tsx.index("createRoot("), \
        "the install offer fires before mount; listening later loses it"


def test_the_install_page_tells_the_truth_for_iphone_and_android():
    page = (SRC / "Install.tsx").read_text()
    assert "Add to Home Screen" in page, "iPhone users need the real gesture"
    assert "Install Concierge" in page
    assert "cannot put an icon" in page.lower() or "cannot add itself" in page.lower(), \
        "the page must not claim a QR installs by itself"
    assert "installUrl()" in page


# ------------------------------------------------------------------ the QR points at the right place

def test_the_install_url_is_the_install_page():
    module = (SRC / "installPrompt.ts").read_text()
    assert "return origin + '/studio/install'" in module


def test_the_setup_qr_encodes_the_install_page_not_the_chat_widget():
    source = (SRC / "App.tsx").read_text()
    assert "QrCode value={installUrl()}" in source
    assert "QrCode value={hosted}" not in source, \
        "the chat-page QR is back, and scanning it installs nothing"
    assert "chat-qr.svg" not in source
    assert "concierge-install-qr.svg" in source


def test_the_chat_page_is_still_offered_as_a_link_but_not_as_an_app():
    source = (SRC / "App.tsx").read_text()
    assert "{hosted ? (" in source, "the hosted chat page is still a real feature"
    assert "it is not the Concierge app" in source


def test_the_old_chat_qr_label_is_gone():
    source = (SRC / "App.tsx").read_text()
    assert 'label="QR code for your chat page"' not in source
    assert "print the QR code for your van" not in source, \
        "the copy that made a chat QR look like an app QR is back"
