import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app import guard
from app.automation import fmt_local
from app.booking import day_slots
from app.chunking import chunk_text
from app.contact import contact_key, normalize_phone
from app.crawler import Robots, extract_links, extract_page, normalize
from app.outbox import next_allowed_send
from app.rag import build_system_prompt, tag_url
from app.security import RateLimiter
from app.sms import validate_signature
from app.tools import chat_tools, voice_tools
from app.voice import _extract_token, build_session

HOURS = {"mon": [["09:00", "12:00"]], "tue": [["09:00", "12:00"]], "wed": [], "thu": [], "fri": [], "sat": [], "sun": []}

TENANT = {
    "name": "Acme Forklifts",
    "persona": "Friendly and direct.",
    "incentive": "10% off when you book online",
    "voice": "eve",
    "timezone": "America/Chicago",
    "business_hours": HOURS,
    "slot_minutes": 30,
    "min_notice_hours": 2,
    "native_booking": False,
    "booking_url": None,
}
NATIVE = {**TENANT, "native_booking": True}


def test_chunk_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_respects_max_and_keeps_all_words():
    text = "\n\n".join(f"Paragraph {i}. " + ("word " * 60) for i in range(12))
    chunks = chunk_text(text, max_chars=500, overlap=80)
    assert len(chunks) > 1
    assert all(len(c) <= 500 + 80 + 2 for c in chunks)
    joined = " ".join(chunks)
    for i in range(12):
        assert f"Paragraph {i}." in joined


def test_chunk_splits_giant_unbroken_text():
    chunks = chunk_text("x" * 5000, max_chars=1000, overlap=0)
    assert len(chunks) == 5
    assert all(len(c) <= 1000 for c in chunks)


def test_normalize():
    assert normalize("https://Example.com/a/b?x=1#frag") == "https://example.com/a/b"
    assert normalize("/pricing", "https://example.com/about") == "https://example.com/pricing"
    assert normalize("mailto:a@b.com") is None
    assert normalize("https://example.com/file.pdf") is None
    assert normalize("javascript:alert(1)") is None


def test_extract_links():
    html = '<a href="/a">A</a><a href="https://other.com/x">X</a><a href="#top">T</a><a>none</a>'
    links = extract_links(html, "https://example.com/")
    assert "https://example.com/a" in links
    assert "https://other.com/x" in links


def test_extract_page_rejects_thin_pages():
    assert extract_page("https://example.com/", "<html><body><p>hi</p></body></html>") is None


def test_robots():
    robots = Robots("User-agent: *\nDisallow: /private\n")
    assert robots.allowed("https://example.com/public")
    assert not robots.allowed("https://example.com/private/page")
    assert Robots(None).allowed("https://example.com/anything")


def test_tag_url():
    tagged = tag_url("https://shop.example.com/part/1?color=red")
    assert "utm_source=ai_concierge" in tagged and "color=red" in tagged
    assert "utm_source=mine" in tag_url("https://x.com/?utm_source=mine")
    assert tag_url("manual:pricing") == "manual:pricing"


def test_rate_limiter():
    limiter = RateLimiter(2, 60)
    assert limiter.check("a") and limiter.check("a")
    assert not limiter.check("a")
    assert limiter.check("b")


def test_prompts():
    chat = build_system_prompt(TENANT, [{"url": "https://x.com/p", "title": "P", "content": "Hello"}], "chat")
    assert "Acme Forklifts" in chat and "<website_information>" in chat and "10% off" in chat
    assert "utm_source=ai_concierge" in chat
    voice = build_system_prompt(TENANT, None, "voice")
    assert "Never read a URL aloud" in voice and "<website_information>" not in voice
    sms = build_system_prompt(TENANT, [], "sms")
    assert "SMS" in sms and "300 characters" in sms
    booking = build_system_prompt(NATIVE, [], "chat")
    assert "check_availability" in booking and "confirmed=true" in booking and "Mon 09:00-12:00" in booking
    assert "Booking:" not in chat


def test_tools_depend_on_tenant():
    plain = {t["function"]["name"] for t in chat_tools(TENANT)}
    assert plain == {"capture_lead"}
    link = {t["function"]["name"] for t in chat_tools({**TENANT, "booking_url": "https://cal.example/x"})}
    assert link == {"capture_lead", "get_booking_link"}
    native = {t["function"]["name"] for t in chat_tools(NATIVE)}
    assert native == {"capture_lead", "check_availability", "book_appointment"}
    voice = {t["name"] for t in voice_tools(NATIVE)}
    assert voice == {"capture_lead", "check_availability", "book_appointment", "search_knowledge"}
    json.dumps(chat_tools(NATIVE) + voice_tools(NATIVE))


def test_voice_session_shape():
    session = build_session({**NATIVE, "voice": "eve"})
    assert session["turn_detection"] == {"type": "server_vad"}
    assert session["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert session["voice"] == "eve"
    assert any(t["name"] == "book_appointment" for t in session["tools"])


def test_extract_token_variants():
    assert _extract_token({"value": "abc"}) == "abc"
    assert _extract_token({"client_secret": {"value": "abc"}}) == "abc"
    assert _extract_token({"client_secret": "abc"}) == "abc"
    assert _extract_token({"token": "abc"}) == "abc"
    assert _extract_token({"nope": 1}) is None


# ---- quote-guard -----------------------------------------------------------
def test_guard_allows_backed_prices_and_flags_invented_ones():
    evidence = "A new 6,000 lb electric forklift starts at $34,500. Rentals are $650.00 weekly."
    assert guard.unknown_amounts("It starts at $34,500.", evidence) == set()
    assert guard.unknown_amounts("Weekly rental is $650.", evidence) == set()
    assert guard.unknown_amounts("It costs $99,999.", evidence) == {Decimal("99999")}
    assert guard.unknown_amounts("Call us for a quote.", evidence) == set()
    assert guard.unknown_amounts("Budget $34500 or $12.50", evidence) == {Decimal("12.5")}


# ---- contacts / SMS --------------------------------------------------------
def test_normalize_phone():
    assert normalize_phone("214-555-0100") == "+12145550100"
    assert normalize_phone("(214) 555-0100") == "+12145550100"
    assert normalize_phone("1 214 555 0100") == "+12145550100"
    assert normalize_phone("+44 7700 900123") == "+447700900123"
    assert normalize_phone("123") is None and normalize_phone("") is None
    assert contact_key("Pat@Example.COM") == "pat@example.com"
    assert contact_key("214-555-0100") == "+12145550100"


def test_twilio_signature_roundtrip():
    import base64, hashlib, hmac
    token, url, params = "secret", "https://api.example.com/api/v1/sms/pk_x", {"From": "+1214", "Body": "hi"}
    data = url + "Body" + "hi" + "From" + "+1214"
    good = base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()
    assert validate_signature(token, url, params, good)
    assert not validate_signature(token, url, params, "bad")
    assert not validate_signature("other", url, params, good)


# ---- booking ---------------------------------------------------------------
def test_day_slots_basic_and_conflicts():
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)  # a Sunday
    monday = date(2026, 11, 2)
    tz = ZoneInfo("America/Chicago")
    slots = day_slots(NATIVE, monday, now, [])
    assert [s.astimezone(tz).strftime("%H:%M") for s in slots] == ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30"]
    # A booking 10:00-10:30 removes exactly that slot.
    booked = [(slots[2], slots[2] + timedelta(minutes=30))]
    left = [s.astimezone(tz).strftime("%H:%M") for s in day_slots(NATIVE, monday, now, booked)]
    assert "10:00" not in left and len(left) == 5
    assert day_slots(NATIVE, date(2026, 11, 4), now, []) == []  # Wednesday closed


def test_day_slots_min_notice():
    tz = ZoneInfo("America/Chicago")
    now = datetime(2026, 11, 2, 9, 40, tzinfo=tz).astimezone(timezone.utc)  # Monday 09:40 local
    slots = day_slots(NATIVE, date(2026, 11, 2), now, [])
    assert [s.astimezone(tz).strftime("%H:%M") for s in slots] == []  # needs 2h notice: earliest 11:40 -> no slot fits
    now = datetime(2026, 11, 2, 8, 0, tzinfo=tz).astimezone(timezone.utc)
    first = day_slots(NATIVE, date(2026, 11, 2), now, [])[0].astimezone(tz).strftime("%H:%M")
    assert first == "10:00"


def test_fmt_local():
    moment = datetime(2026, 11, 5, 20, 30, tzinfo=timezone.utc)  # 14:30 CST
    assert fmt_local(NATIVE, moment) == "Thursday, November 5 at 2:30 PM CST"


# ---- quiet hours -----------------------------------------------------------
def test_next_allowed_send():
    tz = ZoneInfo("America/Chicago")
    noon = datetime(2026, 11, 2, 12, 0, tzinfo=tz).astimezone(timezone.utc)
    assert next_allowed_send(tz, noon) == noon
    late = datetime(2026, 11, 2, 22, 30, tzinfo=tz).astimezone(timezone.utc)
    assert next_allowed_send(tz, late).astimezone(tz) == datetime(2026, 11, 3, 8, 0, tzinfo=tz)
    early = datetime(2026, 11, 2, 5, 0, tzinfo=tz).astimezone(timezone.utc)
    assert next_allowed_send(tz, early).astimezone(tz) == datetime(2026, 11, 2, 8, 0, tzinfo=tz)
