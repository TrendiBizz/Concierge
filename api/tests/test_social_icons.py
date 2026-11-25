"""The social marks are real brand icons, on both surfaces, and they stay accessible.

The Studio's Social page offered a row of text buttons — "Connect facebook", "Connect linkedin
organization" — which read like a form and made the connections the least scannable part of the
page. The public site's footer printed the network names as text beside a dot. Both now use the
official in-colour marks, and both keep a real text name for screen readers and crawlers: an
icon-only link with no accessible name is a link nobody can describe.
"""

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
SITE = REPO / "website"
PORTAL = REPO / "web" / "portal"

NETWORKS = ["linkedin", "facebook", "instagram", "youtube", "tiktok"]


def footer_pages() -> list[pathlib.Path]:
    return [p for p in sorted(SITE.glob("*.html")) if "footer-social" in p.read_text(encoding="utf-8")]


def test_every_page_carries_the_icon_footer():
    pages = footer_pages()
    assert len(pages) == 49, f"{len(pages)} pages carry a footer social block"
    for page in pages:
        html = page.read_text(encoding="utf-8")
        block = html[html.index('class="fine footer-social"'):]
        block = block[:block.index("</p>")]
        for network in NETWORKS:
            assert f"/brand/social-logos/{network}.svg" in block, f"{page.name} has no {network} mark"
        assert 'class="sr-only"' in block, f"{page.name} lost the accessible names"
        # The literal text link is gone; the name now lives in sr-only text.
        assert ">LinkedIn</a>" not in block


def test_every_declared_mark_exists_and_is_an_svg():
    for network in NETWORKS:
        path = SITE / "brand" / "social-logos" / f"{network}.svg"
        assert path.is_file(), f"{network}.svg is missing"
        head = path.read_text(encoding="utf-8")[:200]
        assert "<svg" in head, f"{network}.svg is not an SVG"


def test_the_footer_row_is_styled_as_marks_not_a_sentence():
    css = (SITE / "refresh.css").read_text(encoding="utf-8")
    assert ".footer-social{display:flex" in css
    assert ".footer-social img{width:20px;height:20px" in css
    assert "focus-visible" in css[css.index(".footer-social"):]


def test_the_studio_builds_the_connections_from_brand_marks():
    engage = (PORTAL / "src" / "Engage.tsx").read_text(encoding="utf-8")
    assert "SOCIAL_NETWORKS" in engage and "SocialIcon" in engage
    assert "'Connect ' + provider" not in engage, "the text-only connect buttons are back"
    assert "social-connect-card" in engage


def test_the_studio_ships_each_mark_it_names():
    icons = (PORTAL / "src" / "SocialIcon.tsx").read_text(encoding="utf-8")
    files = set(re.findall(r"file: '([^']+)'", icons))
    assert {"facebook.svg", "instagram.svg", "linkedin.svg", "x.svg", "tiktok.svg",
            "google-business.svg"} <= files
    for name in files:
        assert (PORTAL / "public" / "social" / name).is_file(), f"{name} is not shipped"


def test_the_marks_are_decorative_because_the_name_is_beside_them():
    icons = (PORTAL / "src" / "SocialIcon.tsx").read_text(encoding="utf-8")
    assert 'alt=""' in icons, "an icon repeated its adjacent label to a screen reader"
    assert "networkLabel" in icons


# ---------------------------------------------------------------- the floating controls on a phone

def test_the_chat_launcher_is_a_mark_on_a_phone_not_a_half_screen_bar():
    widget = (REPO / "api" / "static" / "widget.js").read_text(encoding="utf-8")
    assert "@media (max-width:600px){.launcher{width:56px;height:56px" in widget
    assert ".launcher span:last-child{display:none}" in widget


def test_the_language_pill_collapses_to_its_icon_on_a_phone():
    css = (SITE / "site-i18n.css").read_text(encoding="utf-8")
    phone = css[css.index("@media (max-width:600px)"):]
    assert "#trendi-lang>button span{display:none}" in phone
    assert "width:44px" in phone


def test_the_changed_stylesheets_are_cache_busted():
    """A new rule behind an unchanged ?v= is a rule nobody sees for a week."""
    for page in footer_pages()[:5]:
        html = page.read_text(encoding="utf-8")
        assert "refresh.css?v=20261124" in html, f"{page.name} still asks for the old CSS"
        assert "site-i18n.css?v=20261116a" in html, f"{page.name} still asks for the old CSS"


def test_the_closing_call_to_action_is_not_white_on_white():
    """Measured live 2026-11-16: `.btn:not(.ghost){color:#fff}` was declared after
    `.cta-band .btn{color:#6540aa}` at the same specificity, so the label on every closing CTA
    disappeared into its own white pill. The repair has to come after the rule that beat it."""
    css = (SITE / "refresh.css").read_text(encoding="utf-8")
    white_text = css.index(".btn:not(.ghost){color:#fff}")
    repair = css.index(".cta-band .btn,.cta-band .btn.lime,.cta-card .btn{background:#fff;color:#5b2fa8")
    assert repair > white_text, "the button colour repair is declared before the rule it must beat"
    assert ".cta-band .eyebrow,.cta-card .eyebrow,.pricing.featured .eyebrow{color:#efe6ff}" in css, \
        "the eyebrow is purple on purple above every closing CTA again"
