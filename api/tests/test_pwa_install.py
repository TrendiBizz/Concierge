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
        name = icon["src"].split("?", 1)[0].rsplit("/", 1)[-1]
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
    source = (pathlib.Path(main.__file__).parent / "routers" / "public.py").read_text(encoding="utf-8")
    route = '@router.get("/studio/install", include_in_schema=False)'
    assert route in source, "the static install route is missing"
    assert source.index(route) < source.index('@router.get("/studio/{path:path}"'), \
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
    assert "const link = url || installUrl();" in source and "QrCode value={link}" in source
    assert "QrCode value={hosted}" not in source, \
        "the chat-page QR is back, and scanning it installs nothing"
    assert "chat-qr.svg" not in source


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


def test_an_installed_app_signs_in_with_a_code_not_a_pasted_link():
    """The emailed link opens in Safari, and a home-screen app has its own storage, so the app
    stayed signed out. Pasting a URL was the first attempt and was rightly rejected: the login
    screen now asks for a six-digit code instead, and defaults to it when installed."""
    app = (SRC / "App.tsx").read_text(encoding="utf-8")
    assert "/owner/auth/code" in app and "/owner/auth/code/verify" in app
    assert "Six-digit code" in app
    assert "Paste your sign-in link" not in app, "the paste-a-URL flow is back"
    assert "tokenFromPastedLink" not in app
    assert "isInstalled()" in app and "'code' : 'link'" in app, \
        "the installed app does not start on the code path"
    page = (PUBLIC / "install.html").read_text(encoding="utf-8")
    assert "six-digit code" in page, "the install page does not say how the installed app signs in"


# ------------------------------------------------- scan, install, open: already signed in

def test_the_icon_is_visible_on_a_dark_home_screen():
    """The icon was a near-black tile with a lime C: on a dark wallpaper (and under iOS's dark
    icon treatment) it read as a black blob (reported 2026-11-16). The tile is now the brand purple
    #7142d6 (mean channel 131), so the floor is 100: purple passes, a near-black tile (~16) fails."""
    for name in ("apple-touch-icon.png", "icon-192.png", "icon-512.png", "icon-maskable-512.png"):
        data = (PUBLIC / name).read_bytes()
        # corner pixel of an RGB PNG, via PIL: the tile colour must not be near-black
        from PIL import Image
        import io
        corner = Image.open(io.BytesIO(data)).convert("RGB").getpixel((2, 2))
        assert sum(corner) / 3 > 100, f"{name} corner {corner} is dark — invisible on a dark screen"


def test_the_manifest_route_carries_a_ticket_into_the_installed_apps_start_url(tmp_path, monkeypatch):
    import asyncio
    (tmp_path / "manifest.webmanifest").write_text((PUBLIC / "manifest.webmanifest").read_text())
    monkeypatch.setattr(main, "STUDIO_DIR", tmp_path)
    ticket = "A" * 43
    with_ticket = asyncio.run(main.studio_manifest(k=ticket))
    assert json.loads(with_ticket.body)["start_url"] == f"/studio/#invite={ticket}"
    assert json.loads(with_ticket.body)["id"] == "/studio/", "the app identity must not change"
    assert with_ticket.headers["cache-control"] == "no-store"
    for bad in ("", "short", "x" * 30 + "<script>", "../../etc/passwd" + "a" * 20):
        plain = asyncio.run(main.studio_manifest(k=bad))
        assert json.loads(plain.body)["start_url"] == "/studio/", f"{bad!r} must not reach start_url"


def test_the_install_page_hands_the_ticket_to_the_manifest_and_the_launched_app():
    page = (PUBLIC / "install.html").read_text(encoding="utf-8")
    assert "#k=" in page or "hash.match(/^#k=" in page
    assert "manifest.webmanifest?k=" in page
    assert "location.replace('/studio/'" in page and "'#invite=' + ticket" in page, \
        "an installed app landing here must go into the workspace with its ticket"
    assert page.index("location.replace('/studio/'") < page.index("function decide"), \
        "the standalone redirect must run before the page decides what to show"


def test_the_studio_qr_is_minted_per_signed_in_user_and_renewed():
    app = (SRC / "App.tsx").read_text(encoding="utf-8")
    assert "/owner/auth/install-ticket" in app and "<PhoneInstall token={token} />" in app
    assert "50 * 60 * 1000" in app, "the ticket lasts an hour and must be renewed before it lapses"
    assert "installUrl()" in app.split("function PhoneInstall")[1].split("function Setup")[0], \
        "if minting fails the QR must still open the install page"
    src = (pathlib.Path(main.__file__).parent / "routers" / "public.py").read_text(encoding="utf-8")
    router_src = (pathlib.Path(main.__file__).parent / "routers" / "owner_signin.py").read_text(encoding="utf-8")
    assert '@router.post("/owner/auth/install-ticket")' in router_src
    assert src.index('"/studio/manifest.webmanifest"') < src.index('"/studio/{path:path}"'), \
        "the manifest route must precede the static catch-all or it is never reached"


def test_iphone_chrome_firefox_edge_are_told_to_install_in_their_own_browser():
    """Reported 2026-11-19: iPhone Chrome users were sent to Safari. Since iOS 16.4 Chrome, Firefox
    and Edge add a web app to the Home Screen from their own Share menu, so only in-app browsers,
    the Google app and Opera are handed over to Safari."""
    page = (PUBLIC / "install.html").read_text(encoding="utf-8")
    assert "install from ' + own" in page
    assert "/^(Chrome|Firefox|Edge)$/.test(iosBrowser)" in page
    assert "no need to switch to Safari" in page
    assert 'id="ios-step1"' in page


def test_the_share_hint_is_specific_to_the_browser_and_the_default_browser_is_explained():
    page = (PUBLIC / "install.html").read_text(encoding="utf-8")
    assert "if (safari) {" in page, "Safari never updates the share hint"
    assert "Safari puts Share under the <strong>⋯</strong> button" in page, "newer-iOS Share location is missing"
    assert "at the right end of the address bar. If it is missing, tap <strong>⋯</strong> then <strong>Share</strong>" in page
    assert 'id="ios-default-note"' in page
    assert "names the wrong browser" in page and "default browser is still that one" in page
    assert "in Safari’s bottom bar (top right on iPad).</span>" not in page
    # no leftover claim that only Safari can install on iPhone
    assert "must be done in Safari" not in page
    assert "Other browsers cannot add to the home screen" not in page
    assert "Open in Safari" in page and "Instagram" in page, "in-app browsers lost their Safari handover"


def test_root_apple_touch_icon_routes_exist_and_html_declares_180x180():
    """Reported on iPhone 2026-11-27: /apple-touch-icon.png and /apple-touch-icon-precomposed.png
    returned 404 at the root of concierge.trendibizz.com, so iOS fell back to a dark monochrome
    'C' monogram icon on the Home Screen instead of the coloured purple Concierge bell."""
    pub = (pathlib.Path(main.__file__).parent / "routers" / "public.py").read_text(encoding="utf-8")
    assert '@router.get("/apple-touch-icon.png"' in pub
    assert '@router.get("/apple-touch-icon-precomposed.png"' in pub
    assert 'sizes="180x180"' in (PORTAL / "index.html").read_text(encoding="utf-8")
    assert 'sizes="180x180"' in (PUBLIC / "install.html").read_text(encoding="utf-8")


def test_install_page_shows_iphone_steps_even_without_script_and_manifest_icons_are_full_bleed():
    """Reported 2026-11-27: on an iPhone the install page showed the intro but no install steps.
    The iPhone card must be visible by default (script failure / no JS), a failed decide() must not
    blank the page, and the manifest icons must be full-bleed (no baked white rounded corners that
    iOS dark mode turns into a dark tile)."""
    page = (PUBLIC / "install.html").read_text(encoding="utf-8")
    assert '<section class="card" id="ios">' in page, "iPhone steps are hidden until script runs"
    assert "try { decide(); }" in page, "a script error would blank the install page"
    assert "if (!document.querySelector('section.card:not([hidden])')) show('menu');" in page
    assert "Add to Home Screen" in page and "<strong>Share</strong>" in page

    import struct
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        raw = (PUBLIC / name).read_bytes()
        assert raw[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", raw[16:24]) == (size, size), name
    # corners must be the brand purple, not white: compare via the decoded first pixel
    from PIL import Image
    for name in ("icon-192.png", "icon-512.png", "apple-touch-icon.png"):
        im = Image.open(PUBLIC / name).convert("RGB")
        assert im.getpixel((0, 0)) == (0x71, 0x42, 0xD6), f"{name} corner is not full-bleed brand purple"


def test_webclip_profile_is_valid_and_carries_the_icon_and_start_url():
    import plistlib

    from app.routers.public import build_webclip_profile

    icon = (PUBLIC / "apple-touch-icon.png").read_bytes()
    profile = plistlib.loads(build_webclip_profile(icon))
    assert profile["PayloadType"] == "Configuration"
    clip = profile["PayloadContent"][0]
    assert clip["PayloadType"] == "com.apple.webClip.managed"
    assert clip["URL"] == "https://concierge.trendibizz.com/studio/"
    assert clip["Icon"] == icon and clip["FullScreen"] is True and clip["IsRemovable"] is True
    assert clip["PayloadUUID"] != profile["PayloadUUID"]
    assert build_webclip_profile(icon) == build_webclip_profile(icon), "fixed UUIDs: reinstall replaces, not duplicates"
    assert b"invite=" not in build_webclip_profile(icon), "no ticket unless one is passed"


def test_webclip_route_serves_the_apple_config_type_and_install_page_explains_steps(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    (tmp_path / "apple-touch-icon.png").write_bytes((PUBLIC / "apple-touch-icon.png").read_bytes())
    monkeypatch.setattr(main, "STUDIO_DIR", tmp_path)
    res = TestClient(main.app).get("/studio/concierge.mobileconfig")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/x-apple-aspen-config")
    assert "attachment" in res.headers["content-disposition"]
    page = (PUBLIC / "install.html").read_text()
    assert 'class="steps"' in page and "You should see:" in page
    assert "/studio/concierge.mobileconfig" in page and "Not Verified" in page


def test_iphone_card_leads_with_five_step_profile_install_and_keeps_share_route():
    page = (PUBLIC / "install.html").read_text()
    primary = page[page.index('id="ios-profile"'):page.index("<details")]
    assert primary.count("<b>") == 5 and "Profile Downloaded" in primary and "Install" in primary
    assert "/studio/concierge.mobileconfig" in primary and "Not Verified" in primary
    assert "Add to Home Screen" in page[page.index("<details"):]


def test_webclip_profile_opens_signed_in_only_with_a_well_formed_ticket():
    import plistlib

    from app.routers.public import build_webclip_profile

    icon = (PUBLIC / "apple-touch-icon.png").read_bytes()
    ticket = "A" * 43
    url = plistlib.loads(build_webclip_profile(icon, ticket))["PayloadContent"][0]["URL"]
    assert url == f"https://concierge.trendibizz.com/studio/#invite={ticket}"
    for bad in ("short", "x y" * 10, "<script>" * 5):
        assert "invite=" not in plistlib.loads(build_webclip_profile(icon, bad))["PayloadContent"][0]["URL"]
