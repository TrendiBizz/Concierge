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
    assert plain == {"request_enquiry_acknowledgement", "capture_lead"}
    link = {t["function"]["name"] for t in chat_tools({**TENANT, "booking_url": "https://cal.example/x"})}
    assert link == {"request_enquiry_acknowledgement", "capture_lead", "get_booking_link"}
    native = {t["function"]["name"] for t in chat_tools(NATIVE)}
    assert native == {"request_enquiry_acknowledgement", "capture_lead", "check_availability", "book_appointment"}
    voice = {t["name"] for t in voice_tools(NATIVE)}
    assert voice == {"request_enquiry_acknowledgement", "capture_lead", "check_availability", "book_appointment", "search_knowledge"}
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


# ---- SMS providers (Twilio / self-hosted Android gateway) --------------------
def test_smsgate_signature_roundtrip():
    import hashlib, hmac
    from app.sms import validate_smsgate_signature
    key, body, ts = "k", b'{"event":"sms:received"}', "1800000000"
    good = hmac.new(key.encode(), body + ts.encode(), hashlib.sha256).hexdigest()
    assert validate_smsgate_signature(key, body, ts, good, now=1800000100)
    assert validate_smsgate_signature(key, body, ts, good.upper(), now=1800000100)
    assert not validate_smsgate_signature(key, body + b" ", ts, good, now=1800000100)   # tampered body
    assert not validate_smsgate_signature("other", body, ts, good, now=1800000100)      # wrong key
    assert not validate_smsgate_signature(key, body, ts, good, now=1800001000)          # stale timestamp
    assert not validate_smsgate_signature(key, body, "abc", good, now=1800000100)       # bad timestamp
    assert not validate_smsgate_signature("", body, ts, good, now=1800000100)           # no key set


def test_smsgate_payload_shape():
    from app.sms import smsgate_payload
    assert smsgate_payload("+64211234567", "hi") == {"textMessage": {"text": "hi"}, "phoneNumbers": ["+64211234567"]}
    assert smsgate_payload("+64211234567", "hi", 2)["simNumber"] == 2
    assert "simNumber" not in smsgate_payload("+64211234567", "hi", 0)
    assert len(smsgate_payload("+64211234567", "x" * 5000)["textMessage"]["text"]) == 1500


def _settings(monkeypatch, **kw):
    from app import sms
    from app.config import Settings
    monkeypatch.setattr(sms, "get_settings", lambda: Settings(_env_file=None, **kw))


def test_sender_ready_per_provider(monkeypatch):
    from app import sms
    _settings(monkeypatch, sms_provider="none")
    assert not sms.sender_ready({})
    _settings(monkeypatch, sms_provider="twilio", twilio_account_sid="a", twilio_auth_token="b")
    assert not sms.sender_ready({})                              # no sender yet
    assert sms.sender_ready({"sms_from": "+6421000000"})         # per-client number
    _settings(monkeypatch, sms_provider="twilio", twilio_account_sid="a", twilio_auth_token="b",
              twilio_messaging_service_sid="MG1")
    assert sms.sender_ready({})                                  # short code / pool via messaging service
    _settings(monkeypatch, sms_provider="smsgate", smsgate_base_url="https://gw", smsgate_username="u")
    assert not sms.sender_ready({})                              # password missing
    _settings(monkeypatch, sms_provider="smsgate", smsgate_base_url="https://gw",
              smsgate_username="u", smsgate_password="p")
    assert sms.sender_ready({})


def _mock_client(monkeypatch, handler):
    import httpx
    from app import sms
    real = httpx.AsyncClient
    monkeypatch.setattr(sms.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def test_send_smsgate_posts_expected_request(monkeypatch):
    import asyncio, httpx
    from app import sms
    seen = {}

    def handler(request):
        seen["url"], seen["auth"] = str(request.url), request.headers["authorization"]
        seen["json"] = json.loads(request.content)
        return httpx.Response(202, json={"id": "abc"})

    _mock_client(monkeypatch, handler)
    _settings(monkeypatch, sms_provider="smsgate", smsgate_base_url="https://gw.example.com/",
              smsgate_username="u", smsgate_password="p")
    assert asyncio.run(sms.send_sms("+64211234567", "hello")) == "abc"
    assert seen["url"] == "https://gw.example.com/3rdparty/v1/messages"
    assert seen["json"] == {"textMessage": {"text": "hello"}, "phoneNumbers": ["+64211234567"]}
    assert seen["auth"].startswith("Basic ")


def test_send_twilio_uses_messaging_service_when_set(monkeypatch):
    import asyncio, httpx
    from urllib.parse import parse_qs
    from app import sms
    seen = {}

    def handler(request):
        seen["form"] = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        return httpx.Response(201, json={"sid": "SM1"})

    _mock_client(monkeypatch, handler)
    _settings(monkeypatch, sms_provider="twilio", twilio_account_sid="a", twilio_auth_token="b",
              twilio_messaging_service_sid="MG1", twilio_from_number="+6421000000")
    assert asyncio.run(sms.send_sms("+64211234567", "hi")) == "SM1"
    assert seen["form"]["MessagingServiceSid"] == "MG1" and "From" not in seen["form"]


def test_send_sms_refuses_when_provider_is_none(monkeypatch):
    import asyncio
    import pytest
    from app import sms
    _settings(monkeypatch, sms_provider="none")
    with pytest.raises(sms.SmsNotConfigured):
        asyncio.run(sms.send_sms("+64211234567", "hi"))


# ---- lead scoring -----------------------------------------------------------
def _lead(**kw):
    base = {"name": "", "email": "", "phone": "", "message": "", "channel": "chat",
            "page_url": None, "consent_contact": False}
    base.update(kw)
    return base


def test_scoring_hot_lead():
    from app.scoring import assess
    r = assess(_lead(name="Pat Lee", phone="+6421000000", email="pat@example.com", consent_contact=True,
                     message="Hi, how much is a full service and can I book for tomorrow morning?",
                     page_url="https://acme.nz/pricing"), user_turns=4)
    assert r["label"] == "hot" and r["score"] >= 70
    assert any("phone" in x for x in r["reasons"]) and any("price, booking" in x for x in r["reasons"])


def test_scoring_cold_lead_and_floor():
    from app.scoring import assess
    r = assess(_lead(email="a@b.co"))
    assert r["label"] == "cold" and r["score"] == 10
    assert assess(_lead(message="see http://spam.example"))["score"] == 0   # clamped at 0, never negative


def test_scoring_spam_link_costs_points():
    from app.scoring import assess
    clean = assess(_lead(phone="+6421000000", message="quote please"))["score"]
    spam = assess(_lead(phone="+6421000000", message="quote please http://x.example"))["score"]
    assert spam == clean - 25


def test_scoring_booked_is_strong_and_skips_message_intent():
    from app.scoring import assess
    r = assess(_lead(name="Sam", phone="+6421000000", message="Booked appointment for Monday at 9 AM"), booked=True)
    assert any("Booked an appointment" in x for x in r["reasons"])
    assert not any("price, booking" in x for x in r["reasons"])         # no double count
    assert r["label"] == "warm" or r["label"] == "hot"
    assert r["score"] == 25 + 5 + 30


def test_scoring_caps_at_100_and_thresholds():
    from app.scoring import assess, label_for
    top = assess(_lead(name="Pat", phone="+6421000000", email="p@e.co", consent_contact=True, channel="sms",
                       message="price quote book today asap please I need this " * 3,
                       page_url="/book"), user_turns=9, booked=False)
    assert top["score"] == 100
    assert [label_for(x) for x in (0, 39, 40, 69, 70, 100)] == ["cold", "cold", "warm", "warm", "hot", "hot"]


def test_scoring_intent_words_capped_and_deterministic():
    from app.scoring import assess
    lead = _lead(message="price cost quote book appointment urgent")
    a, b = assess(lead), assess(lead)
    assert a == b
    assert sum(1 for x in a["reasons"] if "price, booking" in x) == 1
    assert a["reasons"][0].startswith("+20")                            # capped at two intent hits


def test_scoring_reasons_of_parses_db_values():
    from app.scoring import reasons_of
    assert reasons_of({"score_reasons": '["+25 Gave a phone number"]'}) == ["+25 Gave a phone number"]
    assert reasons_of({"score_reasons": ["x"]}) == ["x"]
    assert reasons_of({"score_reasons": "not json"}) == []
    assert reasons_of({}) == []


def test_lead_view_carries_score():
    from datetime import datetime, timezone
    from app.events import lead_view
    lead = {"id": "1", "name": "A", "email": "", "phone": "+6421000000", "message": "hi", "channel": "chat",
            "page_url": None, "utm": "{}", "created_at": datetime(2026, 11, 6, tzinfo=timezone.utc),
            "score": 55, "score_label": "warm", "score_reasons": '["+25 Gave a phone number"]'}
    v = lead_view(lead)
    assert v["score"] == 55 and v["score_label"] == "warm" and v["score_reasons"] == ["+25 Gave a phone number"]


# ---- reactivation campaigns ---------------------------------------------------
def _unsub_settings(monkeypatch, **kw):
    from app import unsub
    from app.config import Settings
    monkeypatch.setattr(unsub, "get_settings", lambda: Settings(_env_file=None, **kw))


def test_unsub_token_roundtrip(monkeypatch):
    from app import unsub
    _unsub_settings(monkeypatch, unsubscribe_secret="s3cret")
    tok = unsub.make_token("11111111-1111-1111-1111-111111111111", "pat@example.com")
    assert unsub.read_token(tok) == ("11111111-1111-1111-1111-111111111111", "pat@example.com")
    payload, sig = tok.split(".")
    assert unsub.read_token(payload + "." + "0" * len(sig)) is None          # bad signature
    other = unsub.make_token("22222222-2222-2222-2222-222222222222", "pat@example.com")
    assert unsub.read_token(other.split(".")[0] + "." + sig) is None          # payload swapped, signature kept
    assert unsub.read_token("") is None and unsub.read_token("nodot") is None
    _unsub_settings(monkeypatch, unsubscribe_secret="different")
    assert unsub.read_token(tok) is None                                       # wrong secret


def test_unsub_needs_a_secret(monkeypatch):
    import pytest
    from app import unsub
    _unsub_settings(monkeypatch)
    assert not unsub.available() and unsub.read_token("a.b") is None
    with pytest.raises(RuntimeError):
        unsub.make_token("t", "c")
    _unsub_settings(monkeypatch, admin_token="admin-fallback")
    assert unsub.available()                                                   # falls back to ADMIN_TOKEN


def test_campaign_template_validation_and_render():
    import pytest
    from app.campaigns import CampaignError, render, validate_template
    validate_template("Hi {first}, it's been a while since {business} saw you.")
    for bad in ("", "   ", "Hi {name}", "Hi {first.__class__}", "Hi {0}", "Hi {first", "x" * 601):
        with pytest.raises(CampaignError):
            validate_template(bad)
    out = render("Hi {first} from {business}", {"name": "Pat Lee"}, {"name": "Acme"})
    assert out == "Hi Pat from Acme"
    assert render("Hi {first}", {"name": ""}, {"name": "Acme"}) == "Hi there"


def test_campaign_send_times_are_spread():
    from datetime import datetime, timedelta, timezone
    from app.campaigns import send_times
    start = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
    times = send_times(start, 4, 20)                                           # 20 an hour = every 3 minutes
    assert times[0] == start and times[1] - times[0] == timedelta(minutes=3) and len(times) == 4
    assert send_times(start, 0, 20) == []
    assert send_times(start, 2, 0)[1] - start == timedelta(hours=1)           # never divides by zero


def test_campaign_filters_are_validated_and_capped():
    import pytest
    from app.campaigns import CampaignError, clean_filters
    f = clean_filters({})
    assert f["statuses"] == ["new", "contacted", "lost"] and f["older_than_days"] == 30 and f["max_recipients"] == 200
    assert clean_filters({"max_recipients": 99999})["max_recipients"] == 200   # server cap wins
    for bad in ({"statuses": ["nope"]}, {"older_than_days": -1}, {"min_score": 101}, {"max_recipients": 0}):
        with pytest.raises(CampaignError):
            clean_filters(bad)


def test_campaign_readiness_rules(monkeypatch):
    from app import campaigns, unsub
    from app.config import Settings
    s = Settings(_env_file=None, smtp_host="smtp.example.com", smtp_from="hi@example.com", unsubscribe_secret="k")
    monkeypatch.setattr(campaigns, "get_settings", lambda: s)
    monkeypatch.setattr(unsub, "get_settings", lambda: s)
    assert campaigns.readiness({"campaigns_enabled": True}, "email") == []
    assert any("switched off" in p for p in campaigns.readiness({"campaigns_enabled": False}, "email"))
    s2 = Settings(_env_file=None, smtp_host="smtp.example.com", smtp_from="hi@example.com")
    monkeypatch.setattr(campaigns, "get_settings", lambda: s2)
    monkeypatch.setattr(unsub, "get_settings", lambda: s2)
    assert any("UNSUBSCRIBE_SECRET" in p for p in campaigns.readiness({"campaigns_enabled": True}, "email"))
    sms_problems = campaigns.readiness({"campaigns_enabled": True, "sms_enabled": False}, "sms")
    assert any("sms_enabled" in p for p in sms_problems) and any("provider" in p for p in sms_problems)


def test_campaign_mask_hides_contact_details():
    from app.campaigns import mask
    assert mask("pat@example.com") == "p***@example.com"
    assert mask("+6421123456") == "+64*****456" and "1123" not in mask("+6421123456")


# ---- per-client scoring weights and response-time alerts -----------------------
def test_scoring_validate_overrides():
    import pytest
    from app.scoring import validate_overrides
    assert validate_overrides({}) == {}
    assert validate_overrides({"phone": 40, "hot_at": 80, "spam_link": -50}) == {"phone": 40, "hot_at": 80, "spam_link": -50}
    for bad in ({"nope": 1}, {"phone": True}, {"phone": 5.5}, {"phone": "9"}, {"phone": 51}, {"phone": -51},
                {"intent_cap": 6}, {"hot_at": 0}, {"hot_at": 101}, {"warm_at": 70}, {"hot_at": 40},
                {"warm_at": 90}, ["phone"], "phone"):
        with pytest.raises(ValueError):
            validate_overrides(bad)


def test_scoring_weights_change_the_result():
    from app.scoring import assess, weights_for
    lead = _lead(name="Pat", phone="+6421000000", email="p@e.co")
    base = assess(lead)
    assert base["score"] == 25 + 10 + 5
    assert assess(lead, weights={"phone": 0})["score"] == 10 + 5
    assert not any("phone" in r for r in assess(lead, weights={"phone": 0})["reasons"])   # zero-weight rules are not listed
    assert assess(lead, weights={"phone": 50})["score"] == 50 + 10 + 5
    assert assess(lead)["label"] == "warm" and assess(lead, weights={"warm_at": 45})["label"] == "cold"
    assert assess(lead, weights={"hot_at": 45, "warm_at": 20})["label"] == "warm"
    assert assess(lead, weights={"hot_at": 40, "warm_at": 20})["label"] == "hot"
    assert weights_for({"scoring": {"phone": 1}})["phone"] == 1 and weights_for({"scoring": {"phone": 1}})["email"] == 10
    assert weights_for({"scoring": '{"phone": 2}'})["phone"] == 2                          # jsonb arrives as a string
    assert weights_for({"scoring": "garbage"})["phone"] == 25 and weights_for(None)["phone"] == 25


def test_scoring_intent_weights():
    from app.scoring import assess
    lead = _lead(message="price cost quote book appointment")
    assert assess(lead)["score"] == 20                                                     # default cap of 2 words
    assert assess(lead, weights={"intent_cap": 4})["score"] == 40
    assert assess(lead, weights={"intent_each": 5})["score"] == 10
    assert assess(lead, weights={"intent_cap": 0})["score"] == 0


def test_scoring_describe_lists_every_weight():
    from app.scoring import DEFAULT_WEIGHTS, describe
    rows = describe({"scoring": {"phone": 30}})
    assert {r["key"] for r in rows} == set(DEFAULT_WEIGHTS)
    phone = next(r for r in rows if r["key"] == "phone")
    assert phone["default"] == 25 and phone["value"] == 30 and phone["label"] and phone["kind"] == "points"


def test_sla_alert_text():
    from app.sla import _alert_text
    tenant = {"name": "Acme", "sla_minutes": 15}
    lead = {"name": "Pat Lee", "phone": "+6421000000", "email": "", "channel": "chat", "message": "need a quote",
            "score": 82, "score_label": "hot", "minutes_waiting": 31}
    subject, body = _alert_text(tenant, lead)
    assert subject == "[ACTION] HOT lead waiting 31 min: Pat Lee"
    assert "31 minutes" in body and "target is 15" in body and "need a quote" in body and "contacted" in body
    anon = _alert_text(tenant, {**lead, "name": "", "phone": "", "email": ""})[0]
    assert anon.endswith("a visitor")


# ---- to-dos, sales pipeline, calendar feed ------------------------------------
def test_follow_up_due_hot_and_cold():
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    from app.tasks import default_follow_up_due
    tenant = {"timezone": "Pacific/Auckland"}
    now = datetime(2026, 11, 6, 18, 0, tzinfo=timezone.utc)                      # 07:00 on 7 Nov in Auckland
    assert default_follow_up_due(tenant, {"score_label": "hot"}, now) == now + timedelta(minutes=60)
    assert default_follow_up_due({**tenant, "sla_minutes": 15}, {"score_label": "hot"}, now) == now + timedelta(minutes=15)
    early = default_follow_up_due(tenant, {"score_label": "cold"}, now)             # before 9am: same morning
    assert early == datetime(2026, 11, 7, 9, 0, tzinfo=ZoneInfo("Pacific/Auckland")).astimezone(timezone.utc)
    late_now = datetime(2026, 11, 6, 21, 0, tzinfo=timezone.utc)                    # 10:00 local: tomorrow 9am
    late = default_follow_up_due(tenant, {"score_label": "warm"}, late_now)
    assert late == datetime(2026, 11, 8, 9, 0, tzinfo=ZoneInfo("Pacific/Auckland")).astimezone(timezone.utc)
    assert late.astimezone(ZoneInfo("Pacific/Auckland")).hour == 9


def test_task_title_rules():
    import pytest
    from app.tasks import TaskError, clean_title
    assert clean_title("  Call Pat  ") == "Call Pat"
    for bad in ("", "   ", "x" * 201):
        with pytest.raises(TaskError):
            clean_title(bad)


def test_sales_forecast_math():
    from app.sales import STAGE_ODDS, effective_value, forecast
    avg = 50_000                                                                    # $500 average lead value
    leads = [
        {"id": 1, "status": "new", "value_cents": 0},                               # uses the average: 500
        {"id": 2, "status": "contacted", "value_cents": 100_000},                   # own value: 1000
        {"id": 3, "status": "booked", "value_cents": 200_000},                      # own value: 2000
        {"id": 4, "status": "won", "value_cents": 300_000},
        {"id": 5, "status": "lost", "value_cents": 999_999},
        {"id": 6, "status": "weird-status", "value_cents": 0},                      # unknown counts as new
    ]
    f = forecast(leads, avg)
    assert {s: f["stages"][s]["count"] for s in f["stages"]} == {"new": 2, "contacted": 1, "booked": 1, "won": 1, "lost": 1}
    assert f["stages"]["new"]["value_cents"] == 100_000
    assert f["open_value_cents"] == 100_000 + 100_000 + 200_000
    assert f["weighted_value_cents"] == round(100_000 * 0.10 + 100_000 * 0.25 + 200_000 * 0.60)
    assert f["won_value_cents"] == 300_000 and f["stages"]["lost"]["value_cents"] == 999_999
    assert f["odds"] == STAGE_ODDS and STAGE_ODDS["won"] == 1.0 and STAGE_ODDS["lost"] == 0.0
    assert effective_value({"value_cents": 0}, 0) == 0 and effective_value({"value_cents": 7}, 50_000) == 7
    capped = forecast(leads, avg, per_stage=1)
    assert len(capped["stages"]["new"]["leads"]) == 1 and capped["stages"]["new"]["count"] == 2   # totals unaffected by the cap
    assert forecast([], 0)["open_value_cents"] == 0


def test_digest_timing_and_text():
    from datetime import datetime
    from app.sales import digest_is_due, digest_text
    assert datetime(2026, 11, 9).weekday() == 0
    assert digest_is_due(datetime(2026, 11, 9, 9, 0)) and digest_is_due(datetime(2026, 11, 9, 20, 59))
    assert not digest_is_due(datetime(2026, 11, 9, 7, 59)) and not digest_is_due(datetime(2026, 11, 9, 21, 0))
    assert not digest_is_due(datetime(2026, 11, 10, 10, 0))                          # Tuesday
    s = {"days": 7, "new_leads": 4, "contacted": 3, "booked": 1, "won": 2, "won_value_cents": 250_000, "lost": 1,
         "open_value_cents": 400_000, "weighted_value_cents": 90_000, "overdue_todos": 2, "leads_waiting": 1}
    subject, body = digest_text({"name": "Acme"}, s)
    assert subject == "Your week at Acme: 4 new lead(s), 2 won"
    assert "$2,500" in body and "$4,000" in body and "$900" in body and "waiting for a reply: 1" in body
    assert "waiting for a reply" not in digest_text({"name": "Acme"}, {**s, "leads_waiting": None})[1]


def test_ical_escape_and_fold():
    from app.ical import esc, fold
    assert esc("a,b;c\\d\nline2") == "a\\,b\\;c\\\\d\\nline2"
    short = "SUMMARY:short"
    assert fold(short) == short
    long_line = "DESCRIPTION:" + "word " * 40
    folded = fold(long_line)
    parts = folded.split("\r\n ")
    assert len(parts) > 1 and all(len(p.encode()) <= 75 for p in parts) and "".join(parts) == long_line
    accented = "SUMMARY:" + "\u0101" * 60                                           # multi-byte characters never split
    out = fold(accented).split("\r\n ")
    assert all(len(p.encode()) <= 75 for p in out) and "".join(out) == accented


def test_ical_build_feed():
    from datetime import datetime, timezone
    from app.ical import build
    tenant = {"name": "Acme, Ltd"}
    appts = [
        {"id": "a1", "starts_at": datetime(2026, 11, 9, 21, 0, tzinfo=timezone.utc), "ends_at": datetime(2026, 11, 9, 21, 30, tzinfo=timezone.utc),
         "name": "Pat Lee", "phone": "+6421000000", "email": "p@e.co", "notes": "Bring photos; boiler, old", "status": "booked"},
        {"id": "a2", "starts_at": datetime(2026, 11, 10, 1, 0, tzinfo=timezone.utc), "ends_at": datetime(2026, 11, 10, 1, 30, tzinfo=timezone.utc),
         "name": "", "phone": "", "email": "", "notes": "", "status": "cancelled"},
    ]
    feed = build(tenant, appts, now=datetime(2026, 11, 6, 1, 2, 3, tzinfo=timezone.utc))
    assert feed.startswith("BEGIN:VCALENDAR\r\n") and feed.endswith("END:VCALENDAR\r\n")
    assert feed.count("BEGIN:VEVENT") == 2 and feed.count("END:VEVENT") == 2
    assert "DTSTART:20261109T210000Z" in feed and "DTEND:20261109T213000Z" in feed and "DTSTAMP:20261106T010203Z" in feed
    assert "UID:appt-a1@concierge" in feed and "X-WR-CALNAME:Acme\\, Ltd appointments" in feed
    assert "Phone: +6421000000\\nEmail: p@e.co\\nBring photos\\; boiler\\, old" in feed.replace("\r\n ", "")
    assert feed.count("STATUS:CONFIRMED") == 1 and feed.count("STATUS:CANCELLED") == 1
    assert "SUMMARY:Appointment - Acme\\, Ltd" in feed                                  # blank name falls back
    assert all(len(line.encode()) <= 75 for line in feed.split("\r\n"))
