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


def test_media_rendering_finishes_before_the_edge_gives_up():
    """Cloudflare abandons an origin at ~100s; waiting 200s handed customers its error page."""
    media = (pathlib.Path(__file__).resolve().parents[1] / "app" / "media_studio.py").read_text()
    assert "RENDER_TIMEOUT_SECONDS = 85" in media
    assert "httpx.TimeoutException" in media


def test_a_branded_poster_without_a_photo_is_still_designed():
    """Reported as "nothing generated": the template drew a black rectangle with a headline.

    Without a photo the poster must be a finished-looking accent colour field, not an empty canvas.
    """
    renderer = (pathlib.Path(__file__).resolve().parents[2] / "services" / "media-render" / "server.js").read_text()
    showcase = re.search(r"function showcase\(.*?\n\}", renderer, re.S).group(0)
    assert "accentTint" in showcase, "the no-photo poster needs the accent field"
    assert "radial-gradient" in showcase
    # It is not enough to compute the field: it has to be drawn. Removing the node while leaving
    # the gradient string behind was a real regression path this check must catch.
    assert "\n    fallback,\n" in showcase, "the accent field must be drawn, not just computed"
    assert "fontsSize" not in showcase
    assert "justifyContent: 'center'" in showcase, "type should be centred when there is no photo"


def test_the_media_page_shows_what_it_made():
    """"Nothing generated" was also a UI problem: cards listed a filename and a button."""
    media = read("Engage.tsx")
    assert "function AssetPreview" in media, "the asset needs a real preview"
    assert "<video" in media and "<img" in media
    assert "Image made" in media and "Video made" in media, "the status must say what happened"
    assert "Also added to your social composer" in media, "only claim the composer add when it worked"
    assert "Not added to the composer" in media


def test_all_four_templates_are_reachable_and_before_after_asks_for_two_photos():
    media = read("Engage.tsx")
    for template in ("showcase", "before_after", "quote", "service"):
        assert f'value="{template}"' in media, f"{template} is not offered"
    assert "Before / after needs two photos" in media


def test_generated_media_can_be_used_in_a_post():
    """The Media page promises generated work reaches the social composer. It must be pickable.

    The first attempt at this shipped a picker with an empty list: the state existed and was read,
    but nothing ever set it (a type-error fix removed the setter). Silent, and invisible until
    someone clicked. So the check demands the loader call, not just the markup.
    """
    media = read("Engage.tsx")
    assert "async function attachAsset" in media
    assert "Use this in the post" in media
    assert "[...(uploaded || []), ...attachedRefs]" in media, "attached media must reach the draft"
    assert "setLibrary(" in media, "the library must actually be filled, not just declared"
    assert "api('/owner/media/assets')" in media
