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

def test_the_install_page_is_its_own_document_not_a_route_inside_the_app():
    """Reported from a phone 2026-11-16: scanning the install QR landed on the sign-in screen and
    asked for an email address. The page was a route inside the SPA, so a stored session or a stale
    bundle could win. A standalone document cannot fall through to login."""
    page = (PUBLIC / "install.html").read_text(encoding="utf-8")
    assert "<title>Install Concierge</title>" in page
    assert "/studio/manifest.webmanifest" in page, "the install page must still advertise the app"
    assert "beforeinstallprompt" in page, "the page cannot offer the install without listening"
    assert "Add to Home Screen" in page
    assert "install-qr.svg" in page
    # No auth, no router: nothing in this document can ask for an email address.
    assert "type=\"email\"" not in page and "Email" not in page
    assert "location.pathname" not in page
    # And the SPA route is gone, so there is only one implementation to keep right.
    app = (SRC / "App.tsx").read_text()
    assert "InstallApp" not in app, "the SPA install route is back"
    assert "=== '/studio/install'" not in app, "the SPA is routing the install path again"


def test_the_server_serves_the_install_document_before_the_spa_catch_all():
    source = (pathlib.Path(main.__file__)).read_text(encoding="utf-8")
    route = '@app.get("/studio/install", include_in_schema=False)'
    assert route in source, "the static install route is missing"
    assert source.index(route) < source.index('@app.get("/studio/{path:path}"'), \
        "the catch-all is declared first and would answer /studio/install with the shell"


def test_the_server_falls_back_to_the_shell_when_the_document_is_missing(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<!doctype html><title>Concierge</title>")
    monkeypatch.setattr(main, "STUDIO_DIR", tmp_path)
    response = __import__("asyncio").run(main.studio_install())
    assert str(response.path).endswith("index.html")


def test_the_install_prompt_is_captured_before_react_mounts():
    main_tsx = (SRC / "main.tsx").read_text()
    assert "initInstallCapture()" in main_tsx
    assert main_tsx.index("initInstallCapture()") < main_tsx.index("createRoot("), \
        "the install offer fires before mount; listening later loses it"


def test_the_install_page_tells_the_truth_for_iphone_and_android():
    page = (PUBLIC / "install.html").read_text(encoding="utf-8")
    assert "Add to Home Screen" in page, "iPhone users need the real gesture"
    assert "Install Concierge" in page
    assert "cannot put an icon" in page.lower() or "cannot add itself" in page.lower(), \
        "the page must not claim a QR installs by itself"


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


def test_a_phone_without_an_install_prompt_is_not_told_to_scan_a_qr_with_itself():
    """Every phone without Chrome's install offer was shown the desktop block — "scan this with
    the phone you want it on" — on the phone it was already on. The menu route is the honest one."""
    page = (PUBLIC / "install.html").read_text(encoding="utf-8")
    assert "var mobile" in page
    assert "if (!mobile) {" in page, "the desktop branch is gone"
    assert page.index("if (!mobile) {") < page.index("if (deferred) {"), \
        "a computer must be shown the QR even when its own browser offers an install"
    assert "show('menu')" in page, "phones without an install offer lost the browser-menu route"
    assert "Install app” or “Add to Home screen" in page
    assert "Install from the browser menu" in page
    assert "Add to Home screen" in page


def test_an_iphone_browser_other_than_safari_is_told_why_it_cannot_install():
    """Reported 2026-11-16: the QR in Chrome on an iPhone said "use Safari" and read as a broken
    page. Apple only exposes Add to Home Screen in Safari; Chrome, Firefox and Edge on iOS cannot
    install a web app at all, and no page can force the switch. Name the browser and hand over the
    link instead of a bare instruction."""
    page = (PUBLIC / "install.html").read_text(encoding="utf-8")
    for token in ("CriOS", "FxiOS", "EdgiOS", "OPiOS", "GSA"):
        assert token in page, f"the page does not recognise {token} on iOS"
    assert "Apple only allows Safari" in page
    assert "copy-ios" in page, "the iPhone path has no way to move the link into Safari"
    # In Safari the copy card must be hidden — it was the only thing some people noticed.
    assert "if (copyBtn) copyBtn.hidden = true" in page
    assert "safari-https://" not in page, "an untested URL scheme is being offered as a button"


def test_the_iphone_page_shows_the_button_it_is_talking_about():
    """Reported 2026-11-16 from an iPhone: "I do not get an up arrow". The instruction said
    "Share" and the person had nothing to match it to — the icon is now drawn on the page, with
    the places it hides (in-app browsers, a collapsed Safari bar, a hidden Edit Actions row)."""
    page = (PUBLIC / "install.html").read_text(encoding="utf-8")
    assert "aria-label=\"Safari Share button" in page, "the share icon is not drawn for the reader"
    assert 'role="img"' in page[page.index('class="sharebar"'):][:400], \
        "the diagram is decoration nobody can describe"
    assert "Edit Actions" in page, "the hidden 'Add to Home Screen' action has no recovery route"
    assert "Open in Safari" in page
    for app in ("Instagram", "WhatsApp", "LinkedInApp", "TikTok"):
        assert app in page, f"the page does not recognise the {app} in-app browser"
    assert "swipe up" in page.lower(), "a collapsed Safari bar has no instruction"
    assert "navigator.share" not in page, \
        "the Web Share sheet does not carry Safari's Add to Home Screen; offering it is a dead end"


def test_an_installed_app_can_finish_signing_in_without_leaving_it():
    """The emailed link opens in Safari, and a home-screen app has its own storage: signing in
    there leaves the app signed out, with no route back. Reported 2026-11-16 as "this doesn't work
    on my iphone". The login screen now accepts the pasted link and redeems it inside the app."""
    app = (SRC / "App.tsx").read_text(encoding="utf-8")
    assert "tokenFromPastedLink" in app
    assert "#invite=" in app, "a pasted link is not understood"
    assert "Paste your sign-in link" in app
    assert "isInstalled()" in app, "the paste route is offered outside an installed app too"
    assert "/owner/auth/invite" in app
    page = (PUBLIC / "install.html").read_text(encoding="utf-8")
    assert "Sign in first, then add it" in page, "the install page does not warn about the second sign-in"
