"""Guards for the Studio's look and the moments worth celebrating.

The product was a centred grey column with a flat list of links — accurate and completely
uninspiring for a tradesperson deciding whether to trust us with their enquiries. These checks
keep the rebuild from quietly regressing: the shell must own the full width, the navigation must
stay grouped the way trades CRMs group it, and finishing setup must actually celebrate.
"""

import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[2] / "web" / "portal" / "src"


def read(name):
    return (SRC / name).read_text()


def test_the_app_is_not_pinned_to_a_narrow_centred_column():
    """The Vite starter's `#root { width: 1126px; margin: 0 auto }` trapped the whole app."""
    css = read("index.css")
    root_rule = re.search(r"#root \{(.*?)\}", css, re.S).group(1)
    assert "1126px" not in root_rule, "the starter width came back"
    assert "width: 100%" in root_rule
    assert "text-align: left" in root_rule
    assert "margin: 0 auto" not in root_rule


def test_the_footer_link_cannot_be_clipped():
    """The first screenshot showed 'Privac' because of the pinned width."""
    app = read("App.tsx")
    assert ".c-brand-sub" in read("shell.css")
    assert "white-space: nowrap" in read("shell.css")
    assert "Powered by" in app and "/privacy" in app


def test_navigation_is_grouped_like_the_tools_our_customers_compare_us_to():
    """GoHighLevel, Jobber and Tradify group by job-to-cash, not by our database tables."""
    app = read("App.tsx")
    groups = re.search(r"const NAV.*?\n  \];", app, re.S).group(0)
    for group in ("Overview", "Customers", "Sales", "Marketing", "Insights", "Settings"):
        assert f"group: '{group}'" in groups, f"missing navigation group: {group}"
    # The words customers use, not our internal names.
    for label in ("Enquiries", "Contacts", "Bookings", "Quotes", "Products", "Reports"):
        assert f"label: '{label}'" in groups


def test_every_navigation_item_has_an_icon_and_a_colour():
    app = read("App.tsx")
    groups = re.search(r"const NAV.*?\n  \];", app, re.S).group(0)
    assert groups.count("glyph:") == groups.count("tab:"), "every item needs an icon"
    assert Icon_colour_used(app)
    icons = read("icons.tsx")
    for name in ("home", "chat", "users", "calendar", "quote", "box", "chart", "shield"):
        assert name in icons, f"missing icon: {name}"


def Icon_colour_used(app):
    return 'colour={group.colour}' in app


def test_finishing_setup_celebrates_and_the_burst_respects_reduced_motion():
    app = read("App.tsx")
    assert "celebrateOnce(brand.name)" in app, "finishing setup must fire the confetti"
    celebrate = read("celebrate.tsx")
    assert "prefers-reduced-motion" in celebrate, "a celebration must not make anyone motion-sick"
    assert "canvas.remove()" in celebrate, "the overlay must clean itself up"


def test_granting_permissions_celebrates_too():
    permissions = read("Permissions.tsx")
    assert "celebrate()" in permissions
    assert "CHANNELS.every" in permissions, "only celebrate once every channel is decided"


def test_greeting_is_taken_from_the_clock_not_a_hard_coded_string():
    app = read("App.tsx")
    assert "' — ' + greeting()" in app
    assert "good morning')" not in app


def test_a_customer_who_grants_nothing_still_gets_the_celebration():
    """Permissions are optional by design: many businesses will authorise none of them.

    The celebration must hang off pressing Continue, not off a full set of ticks. Before this,
    a customer who declined every permission finished onboarding with no confetti at all.
    """
    permissions = read("Permissions.tsx")
    finish = re.search(r"function finish\(\) \{(.*?)\n  \}", permissions, re.S).group(1)
    assert "celebrate()" in finish, "Continue must celebrate regardless of what was authorised"
    assert "CHANNELS.every" not in finish, "the celebration must not depend on granting everything"
    assert "onDone" in finish, "Continue should lead them into the workspace"
    assert 'label={done ? ' in permissions, "the button must say what it is doing"


def test_every_page_is_full_width_not_a_narrow_centred_column():
    """Pages carried their own `maxWidth: 1040, margin: 0 auto` wrappers after the shell was fixed."""
    offenders = []
    for page in SRC.glob("*.tsx"):
        source = page.read_text()
        if "maxWidth: 1040" in source:
            offenders.append(page.name)
    assert not offenders, f"pages still pinning themselves to a narrow column: {offenders}"


def test_pages_say_something_encouraging_when_there_is_nothing_yet():
    for page, phrase in {
        "Products.tsx": "No products yet",
        "CrmQuotes.tsx": "that is normal on day one",
        "Engage.tsx": "No drafts yet",
        "Designs.tsx": "No enquiries yet",
    }.items():
        source = read(page)
        assert "c-empty" in source, f"{page} has a bare empty state"
        assert phrase in source, f"{page} lost its friendly empty-state copy"


def test_a_stale_build_shows_a_message_not_a_blank_page():
    """A deploy replaces hashed chunks; a window opened before it must not go blank.

    Reported on the Social tab: clicking it left an empty dark page with no explanation.
    """
    main = read("main.tsx")
    assert "vite:preloadError" in main, "a stale chunk must trigger one reload"
    assert "sessionStorage" in main, "and must not reload in a loop"
    boundary = read("ErrorBoundary.tsx")
    assert "getDerivedStateFromError" in boundary
    assert "Reload the page" in boundary


def test_assets_are_cacheable_and_old_chunks_are_not_deleted():
    """Two halves of the same bug: no cache headers, and rsync --delete removing live chunks."""
    api = pathlib.Path(__file__).resolve().parents[1] / "app" / "main.py"
    source = api.read_text()
    assert "immutable" in source, "hashed assets should be cached hard"
    deploy = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "vps" / "redeploy-api.sh"
    assert deploy.exists(), "the deploy path must be a script, not a remembered command"
    text = deploy.read_text()
    assert "--force-recreate api social" in text, "social shares api's namespace and must be recreated with it"
    assert "social reachable" in text, "the script must prove social answers before it exits"


def test_no_page_reimplements_the_api_helper():
    """Five copies of the fetch helper is how Cloudflare's error page got printed at a customer."""
    offenders = []
    for page in SRC.glob("*.tsx"):
        source = page.read_text()
        if 'Request failed' in source and page.name != 'api.ts':
            offenders.append(page.name)
    assert not offenders, f"pages with their own error handling: {offenders}"
    shared = read("api.ts")
    for status in ("520", "524"):
        assert status in shared
    assert "Nothing was lost" in shared


def test_one_page_heading_each():
    """The hero names the page; a second H1 repeating it looked like a rendering bug."""
    for page in SRC.glob("*.tsx"):
        source = page.read_text()
        for title in ("Social", "Marketing media", "Reports", "Bookings", "Team", "Quotations"):
            assert f"<Heading level={{1}}>{title}</Heading>" not in source, f"{page.name} repeats {title}"


def test_only_the_button_you_pressed_says_it_is_working():
    """Reported: pressing Generate AI image made every other generator look busy too.

    One shared boolean drove all three labels. Each button must key off its own action.
    """
    media = read("Engage.tsx")
    assert "busy ? 'Working…'" not in media, "a shared busy flag is back"
    # Each label must be gated on its own action, not the shared flag. One button has two
    # wordings, so check the gate and the wording separately.
    for kind in ("upload", "delete"):
        assert f"busy === '{kind}'" in media, f"{kind} has no scoped gate"
    for wording in ("Uploading", "Deleting"):
        assert wording in media, f"missing {wording}"


def test_media_can_be_deleted_from_the_page():
    """The API could delete and the page could not, so pictures were undeletable in practice."""
    media = read("Engage.tsx")
    assert "async function removeAsset" in media
    assert "'/owner/media/assets/' + asset.id, 'DELETE'" in media
    assert "label={busy === 'delete' ? 'Deleting…' : 'Delete'}" in media
    assert "window.confirm(" in media, "deleting should ask first"


def test_the_media_page_is_an_upload_page_not_a_generator():
    """Reported decision: no branded images, no AI images, no generated video. Upload only."""
    media = read("Engage.tsx")
    assert "Upload your media" in media
    assert "we post what you bring" in media
    # "Template" alone is a CSS property here (gridTemplateColumns), so match generator wording.
    for forbidden in ("Branded image", "AI image", "Generate image", "Showcase —", "Subline",
                      "Before / after"):
        assert forbidden not in media, f"generator wording is back: {forbidden}"


def test_an_uploaded_asset_says_what_it_is():
    media = read("Engage.tsx")
    assert "<strong>{asset.kind === 'video' ? 'Video' : 'Image'}</strong>" in media
    assert "Uploaded — it is in Your media below" in media
