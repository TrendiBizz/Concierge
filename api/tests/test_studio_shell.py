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
