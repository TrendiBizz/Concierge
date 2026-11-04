import json

from app.chunking import chunk_text
from app.crawler import Robots, extract_links, extract_page, normalize
from app.rag import build_system_prompt, tag_url
from app.security import RateLimiter
from app.tools import chat_tools, voice_tools
from app.voice import _extract_token, build_session

TENANT = {
    "name": "Acme Forklifts",
    "persona": "Friendly and direct.",
    "incentive": "10% off when you book online",
    "voice": "eve",
}


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
    # Existing UTM values are preserved.
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


def test_tool_formats():
    chat = chat_tools()
    voice = voice_tools()
    assert {t["function"]["name"] for t in chat} == {"capture_lead", "get_booking_link"}
    assert {t["name"] for t in voice} == {"capture_lead", "get_booking_link", "search_knowledge"}
    assert all(t["type"] == "function" for t in chat + voice)
    json.dumps(chat + voice)  # serialisable


def test_voice_session_shape():
    session = build_session({**TENANT, "voice": "eve"})
    assert session["turn_detection"] == {"type": "server_vad"}
    assert session["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert session["voice"] == "eve"
    assert session["tools"]


def test_extract_token_variants():
    assert _extract_token({"value": "abc"}) == "abc"
    assert _extract_token({"client_secret": {"value": "abc"}}) == "abc"
    assert _extract_token({"client_secret": "abc"}) == "abc"
    assert _extract_token({"token": "abc"}) == "abc"
    assert _extract_token({"nope": 1}) is None
