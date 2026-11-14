"""The website reader proposes a brand; the owner still decides.

These tests pin the behaviour the onboarding redesign depends on: a proposal is
built from public page facts only, an SVG logo becomes a PNG within the brand
store's budget, the accent colour comes from the logo rather than the page
background, and a New Zealand site yields New Zealand defaults.
"""
import base64
import io

import pytest
from PIL import Image

from app import brand_from_site as bfs

# The real header logo from trendibizz.com (416 bytes), as measured on 13 Nov.
TRENDI_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 48"><title>Trendi</title>'
    '<text x="0" y="37" font-family="Arial,sans-serif" font-weight="800" font-size="43" '
    'letter-spacing="-2" fill="#302044">trendi</text>'
    '<rect x="139" y="5" width="38" height="38" rx="12" fill="#7142d6"/>'
    '<path d="M149 31l17-17m-13 0h13v13" fill="none" stroke="white" stroke-width="3.5" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
).encode()

PAGE = """<!doctype html><html><head>
<title>Trendi | Web design Auckland</title>
<meta property="og:site_name" content="Trendi">
<meta property="og:image" content="/og.jpg">
<meta name="generator" content="WordPress 7.1.4">
<meta name="theme-color" content="#f5f7fb">
<link rel="apple-touch-icon" href="/touch.png">
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"Organization","name":"Trendi Ltd","logo":{"@type":"ImageObject","url":"/brand/logo-refresh.svg"},
  "telephone":"+64 9 243 1347","email":"mailto:admin@trendibizz.com",
  "sameAs":["https://www.facebook.com/trendi","https://www.instagram.com/trendi"],
  "address":{"@type":"PostalAddress","addressCountry":"NZ"}}]}
</script></head><body>
<header><a href="/"><img src="/brand/logo-refresh.svg" alt="Trendi logo" class="site-logo"></a></header>
<img src="https://cdn.example.com/hero-photo.jpg" alt="banner">
<a href="mailto:admin@trendibizz.com">Email</a>
<a href="tel:+6492431347">Call</a>
<a href="https://www.tiktok.com/@trendi">TikTok</a>
<a href="https://twitter.com/intent/tweet?url=x">Share</a>
<p class="elementor-text">We design websites.</p>
</body></html>"""


def _png(colour=(113, 66, 214, 255), size=(64, 64)) -> bytes:
    picture = Image.new("RGBA", size, (255, 255, 255, 255))
    for x in range(size[0] // 2, size[0]):
        for y in range(size[1]):
            picture.putpixel((x, y), colour)
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    return buffer.getvalue()


# -- input ---------------------------------------------------------------


def test_free_form_website_becomes_a_url_to_read():
    assert bfs.normalise_site("trendibizz.com") == "https://trendibizz.com/"
    assert bfs.normalise_site("https://www.Trendibizz.com/about") == "https://trendibizz.com/about"
    assert bfs.normalise_site("  yourbusiness.nz  ") == "https://yourbusiness.nz/"


@pytest.mark.parametrize("value", ["", "   ", "not_a_site", "ftp://x.com",
                                   "https://user:pass@x.com", "https://x.com:8080"])
def test_unusable_website_address_is_a_readable_refusal(value):
    with pytest.raises(ValueError) as caught:
        bfs.normalise_site(value)
    assert "website address" in str(caught.value)


# -- reading the page ----------------------------------------------------


def test_scan_reads_name_contacts_socials_and_structured_data():
    page = bfs.scan(PAGE, "https://trendibizz.com/")
    assert page.title == "Trendi | Web design Auckland"
    assert page.metas["og:site_name"] == "Trendi"
    assert "admin@trendibizz.com" in page.emails
    assert "+6492431347" in page.phones
    assert page.socials["facebook"].endswith("/trendi")
    assert page.socials["instagram"].endswith("/trendi")
    assert page.socials["tiktok"].endswith("@trendi")
    # a share-intent link is not an account
    assert "x" not in page.socials
    assert any(image.url == "/brand/logo-refresh.svg" for image in page.images)


def test_malformed_html_still_yields_what_it_can():
    page = bfs.scan("<html><head><title>Broken | Co</title><body><img src=x", "https://broken.nz/")
    assert page.title == "Broken | Co"


def test_logo_candidates_prefer_structured_data_then_header_and_drop_off_site():
    page = bfs.scan(PAGE, "https://trendibizz.com/")
    candidates = bfs.logo_candidates(page, "trendibizz.com")
    assert candidates, "a logo should be found"
    assert candidates[0].url == "/brand/logo-refresh.svg"
    assert all("cdn.example.com" not in candidate.url for candidate in candidates)


def test_share_links_and_off_site_icons_are_never_candidates():
    html = ('<html><head><link rel="apple-touch-icon" href="https://cdn.other.com/i.png"></head>'
            '<body><img src="https://cdn.other.com/logo.png"></body></html>')
    page = bfs.scan(html, "https://mine.nz/")
    assert bfs.logo_candidates(page, "mine.nz") == []


# -- SVG -> PNG ----------------------------------------------------------


def test_svg_text_is_detected_so_the_review_screen_can_warn():
    assert bfs._svg_has_text(TRENDI_SVG.decode())
    assert not bfs._svg_has_text('<svg><rect width="4" height="4" fill="#000"/></svg>')


def test_the_real_text_logo_has_no_accent_from_its_dark_text_but_keeps_its_purple():
    # The wordmark is #302044 (dark) and the tile is #7142d6; purple must win.
    assert bfs.accent_from_svg(TRENDI_SVG.decode()) == "#7142d6"


def test_neutral_only_svg_has_no_accent_to_claim():
    assert bfs.accent_from_svg('<svg><rect fill="#ffffff"/><rect fill="#000000"/></svg>') is None


def test_a_rendered_logo_gives_up_its_accent_colour():
    accent = bfs.accent_from_png(_png())
    assert accent is not None and len(accent) == 7
    red, green, blue = (int(accent[index:index + 2], 16) for index in (1, 3, 5))
    assert abs(red - 113) <= 20 and abs(green - 66) <= 20 and abs(blue - 214) <= 20


def test_a_white_logo_card_yields_no_accent_rather_than_white():
    assert bfs.accent_from_png(_png(colour=(255, 255, 255, 255))) is None


def test_rasterised_logo_fits_the_brand_store_budget():
    wide = Image.new("RGBA", (1600, 400), (113, 66, 214, 255))
    buffer = io.BytesIO()
    wide.save(buffer, format="PNG")
    png = bfs.rasterise_image(buffer.getvalue(), limit=20_000)
    assert png is not None and len(png) <= 20_000
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_svg_rendering_is_optional_and_never_raises(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_resvg(name, *args, **kwargs):
        if name == "resvg_py":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_resvg)
    assert bfs.rasterise_svg(TRENDI_SVG.decode()) is None


def test_data_uri_logo_is_decoded_without_fetching():
    uri = "data:image/png;base64," + base64.b64encode(_png()).decode()
    assert bfs._decode_data_uri(uri) == _png()
    assert bfs._decode_data_uri("data:image/png,notbase64") is None


# -- platform and geography ---------------------------------------------


def test_wordpress_with_elementor_is_recognised_for_the_install_step():
    page = bfs.scan(PAGE, "https://trendibizz.com/")
    platform = bfs.detect_platform(page, PAGE)
    assert platform["kind"] == "wordpress"
    assert platform["elementor"] is True
    assert platform["install_hint"] == "Install on my site"


def test_an_unrecognised_platform_offers_to_do_it_for_them():
    """The hint must never send a tradesman looking for a web person."""
    page = bfs.scan("<html><head></head><body>hello</body></html>", "https://a.nz/")
    assert bfs.detect_platform(page, "")["install_hint"] == "We can add it for you"


def test_a_nz_site_yields_nz_defaults_not_america_chicago():
    html = PAGE.replace('"addressCountry":"NZ"', '"addressCountry":""')
    page = bfs.scan(html, "https://pukeko.nz/")
    geo = bfs.infer_geo(page, html)
    assert geo["country_code"] == "64"
    assert geo["timezone"] == "Pacific/Auckland"


def test_a_structured_address_beats_the_domain():
    page = bfs.scan(PAGE, "https://trendibizz.com/")
    geo = bfs.infer_geo(page, PAGE)
    assert (geo["country_code"], geo["timezone"]) == ("64", "Pacific/Auckland")
    assert geo["source"] == "address"


def test_an_unknown_domain_is_admitted_rather_than_guessed():
    page = bfs.scan("<html><head></head></html>", "https://example.tld/")
    geo = bfs.infer_geo(page, "")
    assert geo["timezone"] == "" and geo["country_code"] == ""


# -- the whole proposal --------------------------------------------------


def test_proposal_composes_name_logo_accent_platform_and_contact(monkeypatch):
    png = _png()

    async def fake_read(url):
        assert url == "https://trendibizz.com/"
        return PAGE, "trendibizz.com", [("/brand/logo-refresh.svg", TRENDI_SVG),
                                        ("/touch.png", png)]

    monkeypatch.setattr(bfs, "_read_site", fake_read)
    monkeypatch.setattr(bfs, "rasterise_svg", lambda text, pixels=512, **kwargs: png)

    import asyncio

    result = asyncio.run(bfs.suggest("trendibizz.com"))
    assert result["name"] == "Trendi"          # og:site_name wins over the title
    assert result["accent"] == "#7142d6"        # the logo's purple, not theme-color #f5f7fb
    assert result["accent_source"] == "logo"
    assert result["logo"]["data"].startswith("data:image/png;base64,")
    assert result["logo"]["rendered_from_svg"] is True
    assert result["logo"]["text_font_risk"] is True
    assert result["contact"]["phone"] == "+6492431347"
    assert result["contact"]["email"] == "admin@trendibizz.com"
    assert result["platform"]["kind"] == "wordpress"
    assert (result["country_code"], result["timezone"]) == ("64", "Pacific/Auckland")
    assert result["socials"]["facebook"].endswith("/trendi")
    assert any("missing its words" in note for note in result["notes"])


def test_proposal_says_so_when_it_can_find_no_logo(monkeypatch):
    async def fake_read(url):
        return "<html><head><title>Solo | Co</title></head><body>hi</body></html>", "solo.nz", []

    monkeypatch.setattr(bfs, "_read_site", fake_read)
    import asyncio

    result = asyncio.run(bfs.suggest("solo.nz"))
    assert result["logo"] is None
    assert any("could not find a logo" in note for note in result["notes"])
    assert result["accent"] == bfs.DEFAULT_ACCENT
    assert result["accent_source"] == "default"


def test_the_suggestion_endpoint_only_reads():
    """A proposal must never be able to write a tenant field or a consent."""
    from app.main import app

    route = next(r for r in app.routes
                 if getattr(r, "path", "") == "/owner/onboarding/brand-suggestion")
    assert route.methods == {"GET"}


def test_no_accent_is_claimed_from_a_logo_that_never_rendered(monkeypatch):
    """A failed render must not hand the owner a colour as if it were the brand's."""
    async def fake_read(url):
        return "<html><head></head><body>hi</body></html>", "x.nz", [("/a.svg", TRENDI_SVG)]

    monkeypatch.setattr(bfs, "_read_site", fake_read)
    monkeypatch.setattr(bfs, "rasterise_svg", lambda text, pixels=512, **kwargs: None)
    import asyncio

    result = asyncio.run(bfs.suggest("x.nz"))
    assert result["logo"] is None
    assert result["accent"] != "#7142d6"
    assert result["accent_source"] == "default"
    assert any("found a logo on your site but could not" in note for note in result["notes"])


def test_new_zealand_wording_on_a_dot_com_still_yields_nz_defaults():
    html = "<html><head><title>Smith Builders</title></head><body><p>Servicing Auckland and Northland.</p></body></html>"
    page = bfs.scan(html, "https://smithbuilders.com/")
    geo = bfs.infer_geo(page, html)
    assert (geo["country_code"], geo["timezone"]) == ("64", "Pacific/Auckland")
    assert geo["source"] == "page wording"


def test_a_plus_64_phone_is_enough_to_place_the_business():
    html = '<html><body><a href="tel:+6492431347">Ring us</a></body></html>'
    page = bfs.scan(html, "https://anywhere.com/")
    geo = bfs.infer_geo(page, html)
    assert (geo["country_code"], geo["timezone"]) == ("64", "Pacific/Auckland")


def _blank_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (8, 8), (0, 0, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_font_family_is_pointed_at_the_bundled_family():
    """resvg does not fall back: an Arial logo renders with no wordmark unless renamed."""
    rewritten = bfs.substitute_fonts(TRENDI_SVG.decode())
    assert '"Liberation Sans"' in rewritten
    assert "Arial" not in rewritten
    assert bfs._svg_has_text(rewritten)          # the words are still text to be drawn
    css = "<svg><style>.a{font-family: Poppins, sans-serif}</style><rect/></svg>"
    assert '"Liberation Sans"' in bfs.substitute_fonts(css)


def test_a_blank_render_loses_to_the_substituted_one(monkeypatch):
    good = _png()

    def fake(text, pixels=512, **kwargs):
        return _blank_png() if "Liberation Sans" not in text else good

    monkeypatch.setattr(bfs, "rasterise_svg", fake)
    png, text_state = bfs.render_logo_svg(TRENDI_SVG.decode())
    assert text_state == "substituted"
    assert png == good


def test_a_logo_already_drawn_as_paths_is_never_rewritten(monkeypatch):
    """Text converted to paths is exact; substitution would only be lossy."""
    seen = []

    def fake(text, pixels=512, **kwargs):
        seen.append(text)
        return _png()

    monkeypatch.setattr(bfs, "rasterise_svg", fake)
    path_only = '<svg><path d="M0 0h10v10z" fill="#7142d6"/></svg>'
    png, text_state = bfs.render_logo_svg(path_only)
    assert text_state == ""
    assert len(seen) == 1


# -- install check -------------------------------------------------------


def _fake_client(html):
    """A stand-in for the public client that returns one page."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def client(url):
        yield None

    async def fetch(_client, _url):
        return html

    return client, fetch


def test_install_check_finds_the_widget_carrying_this_business_key(monkeypatch):
    client, fetch = _fake_client(
        '<script src="https://chat.trendibizz.com/widget.js" data-key="pk_abc" defer></script>')
    monkeypatch.setattr(bfs, "_public_client", client)
    monkeypatch.setattr(bfs, "_fetch_page", fetch)

    import asyncio

    result = asyncio.run(bfs.check_install("trendibizz.com", "pk_abc"))
    assert result["found"] is True
    assert result["script"] is True and result["key"] is True
    assert "installed on this page" in result["detail"]


def test_a_snippet_for_another_business_is_not_a_success(monkeypatch):
    client, fetch = _fake_client(
        '<script src="/widget.js" data-key="pk_someone_else" defer></script>')
    monkeypatch.setattr(bfs, "_public_client", client)
    monkeypatch.setattr(bfs, "_fetch_page", fetch)

    import asyncio

    result = asyncio.run(bfs.check_install("trendibizz.com", "pk_abc"))
    assert result["found"] is False
    assert result["script"] is True and result["key"] is False
    assert "another business" in result["detail"]


def test_a_site_without_the_snippet_says_so_plainly(monkeypatch):
    client, fetch = _fake_client("<html><body>no chat here</body></html>")
    monkeypatch.setattr(bfs, "_public_client", client)
    monkeypatch.setattr(bfs, "_fetch_page", fetch)

    import asyncio

    result = asyncio.run(bfs.check_install("trendibizz.com", "pk_abc"))
    assert result["found"] is False
    assert "could not find the chat script" in result["detail"]


def test_a_business_without_a_chat_key_is_refused(monkeypatch):
    import asyncio

    with pytest.raises(ValueError):
        asyncio.run(bfs.check_install("trendibizz.com", ""))


def test_the_install_check_endpoint_only_reads():
    from app.main import app

    route = next(r for r in app.routes
                 if getattr(r, "path", "") == "/owner/onboarding/install-check")
    assert route.methods == {"GET"}
