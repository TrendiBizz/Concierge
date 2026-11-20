"""The owner's notification must never be a stylesheet. Seen live on 2026-11-15: an Ahrefs crawl
alert reached the inbox as several hundred lines of CSS, quoted-printable escapes and blank lines."""
from app.inbound_text import clean_inbound_text

AHREFS = """New crawl for Trendibizz

/* -------------------------------------
RESPONSIVE AND MOBILE FRIENDLY STYLES
------------------------------------- */

:root {
color-scheme: light only;
}

@media only screen and (max-width: 600px) {
table[class=3Dbody] h1 {
font-size: 28px !important;
margin-bottom: 10px !important;
}
}

47 internal URLs were analyzed. Health Score 100 =C2=B7 Errors 0 =C2=B7 Warnings 44 (+40)
New crawl for Trendibizz"""


def test_a_real_crawl_notification_becomes_readable_text():
    out = clean_inbound_text(AHREFS)
    assert "New crawl for Trendibizz" in out
    assert "47 internal URLs were analyzed" in out
    assert "Health Score 100 · Errors 0 · Warnings 44 (+40)" in out
    # nothing left of the stylesheet or the transfer encoding
    for junk in ("color-scheme", "!important", "@media", "max-width", "=C2", "=3D", "/*", "*/",
                 "font-size"):
        assert junk not in out, junk
    assert "{ }" not in out and "{}" not in out


def test_the_cleaned_message_is_much_shorter_than_the_raw_one():
    out = clean_inbound_text(AHREFS)
    assert len(out) < len(AHREFS) / 2


def test_ordinary_mail_is_left_alone():
    mail = ("Hi, can you quote a fence for Saturday?\n\n"
            "Budget is around $2,000 incl. gst, 12 metres long.\n\nConrad")
    assert clean_inbound_text(mail) == mail


def test_an_equals_sign_in_normal_mail_is_not_mangled():
    mail = "Hi, 2 + 2 = 4 and my code is abc=def, thanks."
    assert clean_inbound_text(mail) == mail


def test_html_only_mail_loses_tags_and_entities():
    out = clean_inbound_text("<p>Hello&nbsp;<b>Sam</b></p><p>Quote&nbsp;please</p>")
    assert "Sam" in out and "Quote" in out
    assert "<" not in out and "&nbsp;" not in out


def test_a_truncated_style_block_is_dropped_whole():
    out = clean_inbound_text("Hi there<style> body { color: red; } tail")
    assert out.startswith("Hi there")
    assert "color" not in out


def test_the_cap_is_enforced():
    assert len(clean_inbound_text("x" * 50000)) == 20000


def test_cleaning_is_wired_into_the_inbound_path_and_the_enquiry():
    """A helper nobody calls fixes nothing: the ingest, the stored draft and the enquiry all use it."""
    import pathlib
    app = pathlib.Path(__file__).resolve().parents[1] / "app"
    inbound = (app / "cloudflare_inbound.py").read_text()
    # limit=20001 so the 413 size check that follows can still see an oversized body
    assert 'payload["text"] = inbound_text.clean_inbound_text(payload["text"], limit=20001)' in inbound
    stored = (app / "inbound_email.py").read_text()
    assert "text_body = inbound_text.clean_inbound_text(text_body)" in stored
    # an automated message must not be presented as a customer enquiry
    assert "(Automated message — not a customer enquiry.)" in stored
    assert 'if "automated_sender" in (flags or [])' in stored
